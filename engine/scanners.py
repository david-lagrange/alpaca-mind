"""scanners — agent-authored autonomous senses.

The agent writes arbitrary Python into workspace/scanners/ and registers
it in workspace/scanners/manifest.json; the sentinel runs each scanner on
its cadence in an ISOLATED subprocess while the agent sleeps. A scanner's
only power is to REQUEST A WAKE — no order path, no credentials beyond
the market-data keys it needs, hard resource limits. This closes the
research loop end to end: study -> algorithm -> DEPLOYED SENSOR, with no
human in the middle.

manifest.json:
{
  "scanners": [
    {"id": "premarket-watch", "script": "premarket_watch.py",
     "cadence_minutes": 15, "timeout_seconds": 60, "max_wakes_per_day": 2,
     "enabled": true, "note": "why this exists",
     "not_before": "...", "not_after": "..."}     # optional ISO windows
  ]
}

Contract for the script: run, print ONE JSON line as the LAST line of
stdout, exit 0:
  {"wake": true|false, "reason": "<why, for the wake context>",
   "protective": false, "payload": {...}}         # payload optional
A run that is structurally unable to fire (market closed, data source
dark) may return {"noop": true} — it counts as a run but does not
consume shadow validation. Persistent state dir per scanner in
$SCANNER_STATE_DIR.

Engine rails (all engine-enforced):
  * SHADOW MODE: a new or edited script's first N runs (default 8,
    min 3) log scanner_shadow_fire events instead of waking. Any edit
    (content-hash change) re-enters shadow — code that runs unattended
    earns trust by showing its record first.
  * WAKE BUDGETS: per-scanner max_wakes_per_day (clamped) + a global
    daily budget + the supervisor's min-wake debounce. Wake storms are
    structurally impossible.
  * QUARANTINE: 3 consecutive failures (crash / timeout / bad output)
    -> scanner disabled + ONE author-wake ("INERT SCANNER"). A broken
    sensor announces itself to its author; the worst failure a sensing
    layer can have is being silently dead while looking armed.
  * ISOLATION: own process group, CPU/memory rlimits, timeout kill,
    stdout to a file (a chatty scanner cannot deadlock the pipe),
    scrubbed env (market-data keys only), non-blocking launch/reap.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")

# Keys a scanner may inherit; everything else is scrubbed. The venue
# data keys pass through (scanners sense the market); auth tokens for
# the agent runtime never do — a scanner has no business near them.
_SAFE_EXACT = {"PATH", "HOME", "LANG", "TZ", "PYTHONUTF8"}
_SAFE_PREFIXES = ("ALPACA_",)


def _now_utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _sha(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return ""


def _parse_iso(s):
    try:
        return datetime.fromisoformat(
            str(s).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


class ScannerRunner:
    """Owned by the sentinel; tick() is called every poll loop and NEVER
    raises or blocks (launch is Popen, reap is poll)."""

    def __init__(self, cfg: dict, ledger, request_wake, log):
        self.cfg = cfg
        self.ledger = ledger
        self.request_wake = request_wake
        self.log = log
        s = cfg.get("scanners") or {}
        self.workspace = Path(cfg["paths"]["workspace"])
        self.dir = self.workspace / "scanners"
        self.state_file = Path(cfg["paths"]["state"]) / ".scanner_health.json"
        self.max_concurrent = int(s.get("max_concurrent", 2))
        self.global_budget = int(s.get("global_wake_budget_day", 8))
        self.per_scanner_cap = int(s.get("max_wakes_per_day_cap", 4))
        self.shadow_min = 3
        # The agent's own lab interpreter when it exists (it may install
        # its own packages there); the system python otherwise.
        lab = self.workspace.parent / "lab" / "bin" / "python3"
        self.python = s.get("python") or (
            str(lab) if lab.exists() else sys.executable)
        self.health: dict = self._load_health()
        self.running: dict[str, dict] = {}
        self.warned_manifest: str | None = None

    # -- persistence -----------------------------------------------------

    def _load_health(self) -> dict:
        try:
            return json.loads(self.state_file.read_text())
        except (OSError, json.JSONDecodeError, ValueError):
            return {"day": _now_utc_day(), "global_wakes_today": 0,
                    "scanners": {}}

    def _save_health(self) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.health, indent=2))
        tmp.replace(self.state_file)

    # -- manifest --------------------------------------------------------

    def load_manifest(self) -> list[dict]:
        f = self.dir / "manifest.json"
        if not f.exists():
            return []
        try:
            raw = json.loads(f.read_text())
            entries = raw.get("scanners") or []
            assert isinstance(entries, list)
        except (json.JSONDecodeError, ValueError, AssertionError,
                OSError) as e:
            h = _sha(f)
            if self.warned_manifest != h:
                self.warned_manifest = h
                self.ledger.record_event("sentinel",
                                         "scanner_manifest_error",
                                         {"error": repr(e)})
                self.log(f"scanner manifest unreadable ({e!r}) — ALL "
                         "scanners inert until fixed")
            return []
        out = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            sid, script = e.get("id"), e.get("script")
            if not (sid and script and _ID_RE.match(str(sid))):
                continue
            # basename only — the script must live inside scanners/
            p = (self.dir / Path(str(script)).name)
            if not p.is_file():
                continue
            out.append({
                "id": str(sid), "path": p,
                "cadence_s": max(5, int(e.get("cadence_minutes", 15))) * 60,
                "timeout": min(120, max(10,
                                        int(e.get("timeout_seconds", 60)))),
                "max_wakes": min(self.per_scanner_cap,
                                 max(1, int(e.get("max_wakes_per_day", 2)))),
                "shadow_runs": max(self.shadow_min,
                                   int(e.get("shadow_runs", 8))),
                "enabled": bool(e.get("enabled", True)),
                "not_before": _parse_iso(e.get("not_before")),
                "not_after": _parse_iso(e.get("not_after")),
            })
        return out

    # -- the tick --------------------------------------------------------

    def tick(self, now: float) -> None:
        try:
            self._tick(now)
        except Exception as e:  # the scanner layer must never hurt the loop
            self.log(f"scanner layer error: {e!r}")

    def _tick(self, now: float) -> None:
        day = _now_utc_day()
        if self.health.get("day") != day:
            self.health["day"] = day
            self.health["global_wakes_today"] = 0
            for st in self.health["scanners"].values():
                st["wakes_today"] = 0
            self._save_health()
        self._reap(now)
        for m in self.load_manifest():
            st = self.health["scanners"].setdefault(m["id"], {
                "script_sha": "", "shadow_left": m["shadow_runs"],
                "wakes_today": 0, "consecutive_failures": 0,
                "disabled": False, "last_run_ts": 0.0,
                "total_runs": 0, "total_fires": 0,
                "total_shadow_fires": 0, "last_status": "never_ran"})
            sha = _sha(m["path"])
            if sha != st["script_sha"]:
                # new or edited code: fresh start, back into shadow
                st.update(script_sha=sha, shadow_left=m["shadow_runs"],
                          consecutive_failures=0, disabled=False)
                self.ledger.record_event("sentinel", "scanner_registered",
                                         {"id": m["id"],
                                          "shadow_runs": m["shadow_runs"]})
                self.log(f"scanner {m['id']} (re)registered — shadow for "
                         f"{m['shadow_runs']} runs")
                self._save_health()
            if (not m["enabled"] or st["disabled"]
                    or m["id"] in self.running
                    or len(self.running) >= self.max_concurrent
                    or now - st["last_run_ts"] < m["cadence_s"]
                    or (m["not_before"] and now < m["not_before"])
                    or (m["not_after"] and now > m["not_after"])):
                continue
            self._launch(m, st, now)

    # -- launch / reap ---------------------------------------------------

    def _env_for(self) -> dict:
        env = {k: v for k, v in os.environ.items()
               if k in _SAFE_EXACT
               or any(k.startswith(p) for p in _SAFE_PREFIXES)}
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def _launch(self, m: dict, st: dict, now: float) -> None:
        sdir = self.dir / "state" / m["id"]
        sdir.mkdir(parents=True, exist_ok=True)
        out_f, err_f = sdir / "out.log", sdir / "err.log"
        env = self._env_for()
        env["SCANNER_ID"] = m["id"]
        env["SCANNER_STATE_DIR"] = str(sdir)
        kw = {}
        if os.name == "posix":
            timeout = m["timeout"]

            def _limits():
                import resource
                resource.setrlimit(resource.RLIMIT_AS,
                                   (512 << 20, 512 << 20))
                resource.setrlimit(resource.RLIMIT_CPU,
                                   (timeout + 10, timeout + 10))
                os.nice(5)
            kw = {"preexec_fn": _limits, "start_new_session": True}
        try:
            proc = subprocess.Popen(
                [self.python, str(m["path"])], cwd=str(self.dir), env=env,
                stdout=open(out_f, "w"), stderr=open(err_f, "w"), **kw)
        except OSError as e:
            self._failure(m, st, now, f"launch failed: {e!r}", "")
            return
        st["last_run_ts"] = now
        st["total_runs"] += 1
        self._save_health()
        self.running[m["id"]] = {"proc": proc,
                                 "deadline": now + m["timeout"],
                                 "m": m, "out": out_f, "err": err_f}

    def _reap(self, now: float) -> None:
        for sid in list(self.running):
            r = self.running[sid]
            rc = r["proc"].poll()
            if rc is None:
                if now > r["deadline"]:
                    try:
                        if os.name == "posix":
                            os.killpg(r["proc"].pid, signal.SIGKILL)
                        else:
                            r["proc"].kill()
                    except OSError:
                        pass
                    st = self.health["scanners"].get(sid, {})
                    self._failure(r["m"], st, now, "timeout", "")
                    del self.running[sid]
                continue
            del self.running[sid]
            st = self.health["scanners"].get(sid, {})
            if rc != 0:
                tail = ""
                try:
                    tail = r["err"].read_text(errors="replace")[-300:]
                except OSError:
                    pass
                self._failure(r["m"], st, now, f"exit {rc}", tail)
                continue
            line = ""
            try:
                lines = [ln for ln in
                         r["out"].read_text(errors="replace").splitlines()
                         if ln.strip()]
                line = lines[-1] if lines else ""
                result = json.loads(line)
                assert isinstance(result, dict)
            except (OSError, json.JSONDecodeError, AssertionError,
                    ValueError):
                self._failure(r["m"], st, now,
                              "no JSON result line", line[:200])
                continue
            st["consecutive_failures"] = 0
            st["last_status"] = "ok"
            in_shadow = st.get("shadow_left", 0) > 0
            # A structurally-unable-to-fire run ({"noop": true}) counts
            # as a run but does not consume shadow validation — exiting
            # shadow having validated nothing defeats shadow's purpose.
            # A run that FIRES always consumes shadow: the fire IS the
            # datum under review.
            if in_shadow and (result.get("wake") or not result.get("noop")):
                st["shadow_left"] -= 1
                if st["shadow_left"] == 0:
                    self.log(f"scanner {sid} exits shadow mode — LIVE")
            if result.get("wake"):
                reason = str(result.get("reason") or "scanner fired")[:400]
                if in_shadow:
                    st["total_shadow_fires"] += 1
                    self.ledger.record_event(
                        "sentinel", "scanner_shadow_fire",
                        {"id": sid, "reason": reason})
                elif (st["wakes_today"] >= r["m"]["max_wakes"]
                      or self.health["global_wakes_today"]
                      >= self.global_budget):
                    self.ledger.record_event(
                        "sentinel", "scanner_budget_exhausted",
                        {"id": sid, "reason": reason})
                else:
                    st["wakes_today"] += 1
                    st["total_fires"] += 1
                    self.health["global_wakes_today"] += 1
                    self.ledger.record_event("sentinel", "scanner_fire",
                                             {"id": sid, "reason": reason})
                    self.request_wake(
                        f"SCANNER {sid}: {reason}",
                        {"scanner": sid,
                         "payload": result.get("payload")},
                        protective=bool(result.get("protective")))
            self._save_health()

    def _failure(self, m: dict, st: dict, now: float,
                 what: str, detail: str) -> None:
        st["consecutive_failures"] = st.get("consecutive_failures", 0) + 1
        st["last_status"] = what
        n = st["consecutive_failures"]
        self.ledger.record_event("sentinel", "scanner_error",
                                 {"id": m["id"], "error": what,
                                  "detail": detail, "consecutive": n})
        self.log(f"scanner {m['id']} failed ({what}) — {n} consecutive")
        if n >= 3 and not st.get("disabled"):
            # Fail LOUD to the author: disable and wake the agent ONCE
            # to fix its own code.
            st["disabled"] = True
            self.ledger.record_event("sentinel", "scanner_quarantined",
                                     {"id": m["id"], "error": what})
            self.request_wake(
                f"INERT SCANNER {m['id']}: quarantined after 3 consecutive "
                f"failures ({what}). It has NOT been sensing since it "
                "broke. Read scanners/state/" + m["id"] + "/err.log, fix "
                "the script (any edit re-registers it through shadow "
                "mode), or disable it in the manifest.",
                {"scanner": m["id"], "error": what, "detail": detail},
                protective=False)
        self._save_health()
