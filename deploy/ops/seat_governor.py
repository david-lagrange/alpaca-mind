#!/usr/bin/env python3
"""seat_governor — shapes launches from the seat's meters. Operator-side,
root-only, one tick per timer run.

The agents never hear of the seat. This script reads its meters through
gauge.py and acts in exactly two ways, neither of which is a word to an
agent:

  * THE ALIAS TABLE (aliases.json beside the engine config). While the
    deepest tier's weekly meter is spent, the alias the agents ask for
    runs as the next tier at its deepest effort, and their subagents
    follow. The table says only what an alias runs as right now. The
    agents may read it and will find a model choice, nothing more.

  * HOLDS. When a window is nearly spent, both agents' HALT files are
    placed carrying a marker, and a sidecar records the reason and when
    to lift. At the reset (plus a buffer) the files are removed, the
    trader is woken with a plain operator fact unless one of its own
    sensors already has a wake pending, and the manager is asked to
    run. A session already running when a hold lands simply continues.

A HALT the owner placed by hand outranks everything: the governor never
places or lifts a hold while one exists. An unreadable gauge keeps the
last policy, lifts holds by time only, and raises an ALERT file after a
grace period. Every tick appends a telemetry row to seat.jsonl (readable
by the manager's group, for the owner-login pages only).

Thresholds come from the environment (the unit's EnvironmentFile), so
the numbers are operator config and never live in the engine.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gauge  # noqa: E402

MARKER = "operator-hold"

RESUME_REASON = ("OPERATOR HOLD LIFTED: the operator held all sessions from "
                 "{a} to {b}. Nothing of yours changed. Verify your book and "
                 "triggers, then continue.")


def load_config(env=None) -> dict:
    env = os.environ if env is None else env

    def num(key, default):
        try:
            return float(env.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    ops = Path(env.get("OPS_DIR", "/var/lib/alpaca-mind/ops"))
    engine_cfg = Path(env.get("ENGINE_CONFIG_DIR",
                              "/opt/alpaca-mind/engine/config"))
    return {
        "fable_fallback_pct": num("FABLE_FALLBACK_PCT", 90),
        "five_hour_hold_pct": num("FIVE_HOUR_HOLD_PCT", 88),
        "weekly_hold_pct": num("WEEKLY_HOLD_PCT", 97),
        "hold_buffer_s": num("HOLD_BUFFER_S", 120),
        "gauge_stale_s": num("GAUGE_STALE_S", 1800),
        # Hysteresis: a policy flips back only once the meter has moved
        # clearly away from the threshold, so a meter hovering at the
        # line cannot flap launches between tiers or holds between ticks.
        "fallback_release_margin": num("FALLBACK_RELEASE_MARGIN", 5),
        "hold_release_margin": num("HOLD_RELEASE_MARGIN", 10),
        "fallback_alias": env.get("FALLBACK_ALIAS", "fable"),
        "fallback_model": env.get("FALLBACK_MODEL", "claude-opus-5"),
        "fallback_effort": env.get("FALLBACK_EFFORT", "max"),
        "resume_model": env.get("RESUME_MODEL", "fable"),
        "resume_effort": env.get("RESUME_EFFORT", "xhigh"),
        "ssm_prefix": env.get("SSM_PREFIX") or env.get("SAVED_SSM_PREFIX")
        or "/alpaca-mind",
        "aws_region": env.get("AWS_REGION") or env.get("SAVED_AWS_REGION")
        or None,
        "ops_dir": ops,
        "gauge_path": ops / "gauge-credentials.json",
        "hold_path": ops / "hold.json",
        "state_path": ops / "governor-state.json",
        "telemetry_path": ops / "seat.jsonl",
        "alert_path": ops / "ALERT",
        "alias_table": engine_cfg / "aliases.json",
        "halts": {
            "mind": Path(env.get("MIND_HALT",
                                 "/srv/mind/workspace/state/HALT")),
            "ui": Path(env.get("UI_HALT", "/srv/ui/workspace/state/HALT")),
        },
        "wake_request": Path(env.get(
            "MIND_WAKE_REQUEST", "/srv/mind/workspace/state/wake_request.json")),
        "ui_env": Path(env.get("UI_ENV", "/srv/ui/.env")),
        "redirect_env": Path(env.get("REDIRECT_ENV",
                                     "/etc/default/alpaca-mind-redirect")),
        "telemetry_group": env.get("TELEMETRY_GROUP", "ui"),
    }


def fallback_table(cfg: dict) -> dict:
    return {"aliases": {cfg["fallback_alias"]: {
        "model": cfg["fallback_model"], "effort": cfg["fallback_effort"]}},
        "subagent_model": cfg["fallback_model"]}


def is_pass_through(table: dict) -> bool:
    return not (isinstance(table, dict) and table.get("aliases"))


def iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def when(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# -- the decision core ---------------------------------------------------------
# Pure with respect to the machine: every observation and every action goes
# through the io object, so the whole state machine runs under test with
# injected meters and a clock.

def tick(io, cfg: dict) -> dict | None:
    now = io.now()
    st = io.read_state()
    hold = io.read_hold()
    halts = io.halt_state()
    table = io.read_table()
    events: list[str] = []

    # 1. The owner's own hand outranks the governor. A HALT that does not
    #    carry the marker, or a marker with no sidecar to vouch for it,
    #    is theirs: nothing is placed and nothing is lifted.
    manual = any(v == "manual" for v in halts.values()) or (
        hold is None and any(v == "marker" for v in halts.values()))

    if not io.gauge_present():
        # No credential on this deployment: there is nothing to shape.
        # A hold left behind by an earlier credential still lifts on time.
        if hold and not manual and now >= float(hold["until"]):
            _lift(io, cfg, st, hold, now, "time")
        io.log("no_gauge")
        io.write_state(st)
        return None

    meters, err = io.read_meters()

    # 2. Unreadable gauge: keep the policy, lift by time only, alert once
    #    the outage is longer than the grace period.
    if meters is None:
        since = float(st.get("unreadable_since") or now)
        st["unreadable_since"] = since
        st["last_error"] = err
        if hold and not manual and now >= float(hold["until"]):
            hold = _lift(io, cfg, st, hold, now, "time")
            events.append("hold_lifted")
        stale = now - since >= cfg["gauge_stale_s"]
        if stale:
            io.alert(f"gauge unreadable since {iso(since)}: {err}")
        state = "gauge_stale" if stale else _state(manual, hold, table)
        row = _row(now, None, err, state, table, hold, events)
        io.log("gauge_unreadable", error=err, since=iso(since), state=state)
        io.write_state(st)
        io.telemetry(row)
        return row

    st["unreadable_since"] = None
    st["last_error"] = None
    st["last_ok_at"] = now
    io.alert(None)

    if not manual:
        # 3–4. Holds. The weekly pool outranks the five-hour window.
        hold, placed = _ensure_holds(io, cfg, st, hold, meters, now)
        events += placed
        # 5. Lift by time, or by a meter that has clearly fallen back.
        if hold:
            kind = hold["kind"]
            meter = meters["weekly_all"] if kind == "weekly" else meters["five_hour"]
            thr = cfg["weekly_hold_pct"] if kind == "weekly" else cfg["five_hour_hold_pct"]
            if now >= float(hold["until"]):
                hold = _lift(io, cfg, st, hold, now, "time")
                events.append("hold_lifted")
            elif meter is not None and meter < thr - cfg["hold_release_margin"]:
                hold = _lift(io, cfg, st, hold, now, "meter")
                events.append("hold_lifted")

    # 6. The alias table follows the deepest tier's own weekly meter,
    #    hold or no hold, owner's hand or not: it only shapes launches,
    #    and the first launch after any hold should already be right.
    table, changed = _follow_fable(io, cfg, table, meters)
    if changed:
        events.append(changed)

    state = _state(manual, hold, table)
    row = _row(now, meters, None, state, table, hold, events)
    io.log("tick", state=state, five_hour=meters["five_hour"],
           weekly_all=meters["weekly_all"], weekly_fable=meters["weekly_fable"],
           table=row["table"], hold=(hold or {}).get("kind"), events=events)
    io.write_state(st)
    io.telemetry(row)
    return row


def _ensure_holds(io, cfg, st, hold, m, now):
    events = []
    weekly_due = m["weekly_all"] is not None and m["weekly_all"] >= cfg["weekly_hold_pct"]
    five_due = m["five_hour"] is not None and m["five_hour"] >= cfg["five_hour_hold_pct"]

    def until_for(reset_iso, label):
        # A hold with no lift time would be forever; a reset already in
        # the past is a stale read of a window that has rolled — in both
        # cases no hold is placed and the next read decides.
        reset = gauge.to_epoch(reset_iso)
        if reset is None:
            io.log("hold_skipped", kind=label, why="no_reset_time")
            return None
        until = reset + cfg["hold_buffer_s"]
        if until <= now:
            io.log("hold_skipped", kind=label, why="reset_in_past",
                   resets_at=reset_iso)
            return None
        return until

    if weekly_due:
        until = until_for(m["weekly_resets_at"], "weekly")
        if until is not None:
            if hold is None:
                hold = _place(io, st, "weekly", until, now, m)
                events.append("hold_placed")
            elif hold["kind"] != "weekly":
                hold = dict(hold, kind="weekly", until=until)
                io.write_hold(hold)
                io.log("hold_raised", kind="weekly", until=iso(until))
                events.append("hold_raised")
            elif abs(float(hold["until"]) - until) > 1:
                hold = dict(hold, until=until)
                io.write_hold(hold)
                io.log("hold_moved", kind="weekly", until=iso(until))
            return hold, events

    if five_due:
        until = until_for(m["five_hour_resets_at"], "five_hour")
        if until is not None:
            if hold is None:
                hold = _place(io, st, "five_hour", until, now, m)
                events.append("hold_placed")
            elif hold["kind"] == "five_hour" and abs(float(hold["until"]) - until) > 1:
                hold = dict(hold, until=until)
                io.write_hold(hold)
                io.log("hold_moved", kind="five_hour", until=iso(until))
    return hold, events


def _place(io, st, kind, until, now, m):
    hold = {"kind": kind, "placed_at": now, "until": until,
            "placed_by": "governor",
            "meters": {"five_hour": m["five_hour"],
                       "weekly_all": m["weekly_all"],
                       "weekly_fable": m["weekly_fable"]}}
    # Sidecar first: a marker file without its sidecar reads as the
    # owner's hand, and a crash between the two writes must fail toward
    # standing aside, never toward an orphaned hold nobody will lift.
    io.write_hold(hold)
    io.place_halts()
    st["last_hold_at"] = now
    io.log("hold_placed", kind=kind, until=iso(until))
    return hold


def _lift(io, cfg, st, hold, now, why):
    io.remove_halts()
    io.remove_hold()
    if io.wake_request_pending():
        # A sensor's request already waits in the single slot: it wakes
        # the trader on a real fact, and the gap is visible in its ledger.
        io.log("resume_wake_deferred", why="sensor_request_pending")
    else:
        io.file_resume_wake(float(hold["placed_at"]), now)
    io.manager_run_now()
    st["last_lift_at"] = now
    io.log("hold_lifted", kind=hold["kind"], why=why,
           held_s=round(now - float(hold["placed_at"])))
    return None


def _follow_fable(io, cfg, table, m):
    f = m["weekly_fable"]
    if f is None:
        return table, None   # no meter: the table stays as it is
    if f >= cfg["fable_fallback_pct"]:
        desired = fallback_table(cfg)
    elif f < cfg["fable_fallback_pct"] - cfg["fallback_release_margin"]:
        desired = {"aliases": {}}
    else:
        return table, None   # inside the hysteresis band
    current = {k: table.get(k) for k in ("aliases", "subagent_model")
               if table.get(k)} if isinstance(table, dict) else {}
    wanted = {k: v for k, v in desired.items() if v}
    if current == wanted:
        return table, None
    io.write_table(desired)
    kind = "table_pass_through" if is_pass_through(desired) else "table_fallback"
    io.log(kind, weekly_fable=f)
    return desired, kind


def _state(manual, hold, table):
    if manual:
        return "manual_hold"
    if hold:
        return "hold_" + hold["kind"]
    return "normal" if is_pass_through(table) else "fallback"


def _row(now, m, err, state, table, hold, events):
    m = m or {}
    return {
        "ts": iso(now),
        "gauge": "ok" if err is None else f"unreadable: {err}",
        "five_hour": m.get("five_hour"),
        "weekly_all": m.get("weekly_all"),
        "weekly_fable": m.get("weekly_fable"),
        "weekly_opus": m.get("weekly_opus"),
        "five_hour_resets_at": m.get("five_hour_resets_at"),
        "weekly_resets_at": m.get("weekly_resets_at"),
        "fable_resets_at": m.get("fable_resets_at"),
        "state": state,
        "table": "pass-through" if is_pass_through(table) else "fallback",
        "hold": ({"kind": hold["kind"], "placed_at": iso(float(hold["placed_at"])),
                  "until": iso(float(hold["until"]))} if hold else None),
        "events": events,
    }


# -- the machine ---------------------------------------------------------------

class BoxIO:
    """Every observation of, and action on, the real box."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._ids = {}
        try:
            import pwd
            for user in ("mind", self.cfg["telemetry_group"]):
                pw = pwd.getpwnam(user)
                self._ids[user] = (pw.pw_uid, pw.pw_gid)
        except (ImportError, KeyError):
            pass

    # observations ----------------------------------------------------------

    def now(self) -> float:
        return time.time()

    def gauge_present(self) -> bool:
        p = self.cfg["gauge_path"]
        if p.exists():
            return True
        return gauge.bootstrap(p, f"{self.cfg['ssm_prefix']}/GAUGE_CREDENTIALS",
                               self.cfg["aws_region"])

    def read_meters(self):
        try:
            return gauge.meters(self.cfg["gauge_path"]), None
        except (gauge.GaugeError, OSError, ValueError, KeyError) as e:
            return None, f"{type(e).__name__}: {e}"[:200]

    def halt_state(self) -> dict:
        out = {}
        for agent, p in self.cfg["halts"].items():
            if not p.exists():
                out[agent] = "absent"
                continue
            try:
                body = p.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                body = "?"
            out[agent] = "marker" if body == MARKER else "manual"
        return out

    def read_hold(self):
        return self._read_json(self.cfg["hold_path"])

    def read_table(self) -> dict:
        return self._read_json(self.cfg["alias_table"]) or {}

    def read_state(self) -> dict:
        return self._read_json(self.cfg["state_path"]) or {}

    def wake_request_pending(self) -> bool:
        return self.cfg["wake_request"].exists()

    # actions ---------------------------------------------------------------

    def write_table(self, table: dict) -> None:
        body = {"written_at": iso(self.now())}
        body["aliases"] = table.get("aliases") or {}
        if table.get("subagent_model"):
            body["subagent_model"] = table["subagent_model"]
        self._write_atomic(self.cfg["alias_table"], json.dumps(body, indent=2),
                           0o644)

    def place_halts(self) -> None:
        for agent, p in self.cfg["halts"].items():
            if p.exists():
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            self._write_atomic(p, MARKER + "\n", 0o644, owner=agent)

    def remove_halts(self) -> None:
        for p in self.cfg["halts"].values():
            try:
                if p.exists() and p.read_text(encoding="utf-8").strip() == MARKER:
                    p.unlink()
            except OSError as e:
                self.log("halt_remove_failed", path=str(p), error=repr(e))

    def write_hold(self, hold: dict) -> None:
        self._write_atomic(self.cfg["hold_path"], json.dumps(hold, indent=2),
                           0o600)

    def remove_hold(self) -> None:
        self.cfg["hold_path"].unlink(missing_ok=True)

    def file_resume_wake(self, placed_at: float, lifted_at: float) -> None:
        body = {
            "requested_at": iso(lifted_at),
            "reason": RESUME_REASON.format(a=when(placed_at), b=when(lifted_at)),
            "context": {"source": "operator"},
            "protective": False,
            "wake_as": {"model": self.cfg["resume_model"],
                        "effort": self.cfg["resume_effort"]},
        }
        p = self.cfg["wake_request"]
        p.parent.mkdir(parents=True, exist_ok=True)
        self._write_atomic(p, json.dumps(body, indent=2), 0o644, owner="mind")
        self.log("resume_wake_filed", path=str(p))

    def manager_run_now(self) -> None:
        password = self._env_value(self.cfg["ui_env"], "UI_PASSWORD")
        port = self._env_value(self.cfg["redirect_env"], "APP_PORT") or "3000"
        if not password:
            self.log("manager_run_now_skipped", why="no_ui_password")
            return
        auth = base64.b64encode(f"owner:{password}".encode()).decode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/run-now", data=b"", method="POST",
            headers={"Authorization": "Basic " + auth,
                     "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                self.log("manager_run_now", status=r.status)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            self.log("manager_run_now_failed", error=type(e).__name__)

    def write_state(self, st: dict) -> None:
        self._write_atomic(self.cfg["state_path"], json.dumps(st, indent=2),
                           0o600)

    def alert(self, text: str | None) -> None:
        p = self.cfg["alert_path"]
        if text is None:
            if p.exists():
                p.unlink()
                self.log("alert_cleared")
            return
        if not p.exists():
            self.log("alert_raised", text=text)
        self._write_atomic(p, text + "\n", 0o640, group=self.cfg["telemetry_group"])

    def telemetry(self, row: dict) -> None:
        p = self.cfg["telemetry_path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        self._perms(p, 0o640, group=self.cfg["telemetry_group"])

    def log(self, event: str, **kv) -> None:
        rec = {"ts": iso(time.time()), "component": "seat_governor",
               "event": event}
        rec.update({k: v for k, v in kv.items() if v is not None})
        print(json.dumps(rec), flush=True)

    # helpers ---------------------------------------------------------------

    def _read_json(self, p: Path):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            self.log("file_unreadable", path=str(p), error=repr(e))
            return None
        return d if isinstance(d, dict) else None

    def _write_atomic(self, p: Path, text: str, mode: int,
                      owner: str | None = None, group: str | None = None):
        tmp = p.with_name(p.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        self._perms(tmp, mode, owner=owner, group=group)
        os.replace(tmp, p)

    def _perms(self, p: Path, mode: int, owner: str | None = None,
               group: str | None = None) -> None:
        try:
            os.chmod(p, mode)
            if owner and owner in self._ids:
                os.chown(p, *self._ids[owner])
            elif group and group in self._ids:
                os.chown(p, 0, self._ids[group][1])
        except (OSError, AttributeError):
            pass

    @staticmethod
    def _env_value(p: Path, key: str) -> str | None:
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.startswith(key + "="):
                    return line[len(key) + 1:].strip().strip("'\"")
        except OSError:
            return None
        return None


class DryRunIO(BoxIO):
    """Observes the real box; every action becomes a log line instead."""

    def _say(self, action, **kv):
        self.log("dry_run", action=action, **kv)

    def write_table(self, table):
        self._say("write_table", table=table)

    def place_halts(self):
        self._say("place_halts")

    def remove_halts(self):
        self._say("remove_halts")

    def write_hold(self, hold):
        self._say("write_hold", hold=hold)

    def remove_hold(self):
        self._say("remove_hold")

    def file_resume_wake(self, placed_at, lifted_at):
        self._say("file_resume_wake")

    def manager_run_now(self):
        self._say("manager_run_now")

    def write_state(self, st):
        self._say("write_state")

    def alert(self, text):
        self._say("alert", text=text)

    def telemetry(self, row):
        self._say("telemetry", row=row)


def main() -> int:
    ap = argparse.ArgumentParser(description="one seat-governor tick")
    ap.add_argument("--dry-run", action="store_true",
                    help="observe the box; log the actions instead of taking them")
    args = ap.parse_args()
    cfg = load_config()
    cfg["ops_dir"].mkdir(parents=True, exist_ok=True)
    io = DryRunIO(cfg) if args.dry_run else BoxIO(cfg)
    try:
        tick(io, cfg)
    except Exception as e:  # noqa: BLE001 — a timer tick must say why it died
        io.log("tick_failed", error=repr(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
