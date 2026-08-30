#!/usr/bin/env python3
"""supervisor — launches, observes, and paces an agent. No LLM of its own.

The contract with the agent:
  * The agent owns its own cadence. state/schedule.json holds its
    recurring slots (reflection, research, anything it invents);
    state/wake.json holds one-shot wakes. Both may carry run_type,
    model, effort, and charter — the agent chooses its own mind and
    frame per wake. The engine honors what is written and never
    allocates thought on its own.
  * The sentinel may file state/wake_request.json (a trigger fired, a
    fill landed) — serviced ahead of the schedule. Its optional wake_as
    block carries the same choice fields, so the agent's sensors wake
    it as the mind and under the charter the agent armed them with.
  * If the schedule stops producing reflection entirely, one generous
    aliveness backstop fires — and says plainly that the ENGINE fired
    it. Engine-caused wakes never impersonate the agent's own reasons;
    an agent that cannot trust its wake reasons burns sessions
    investigating ghosts.
  * A malformed schedule or wake time means default cadence, NEVER
    "due now" — treating a parse failure as due-now converts a typo
    into a wake storm.

Also owns: session launch (headless CLI), per-launch prompt snapshots
(the exact charter text every session ran under stays auditable
forever), timeouts that cannot be starved by a silent hang, retry with
backoff, and the owner's kill switch (state/HALT).

A second role exists for the UI manager (config `role: ui`): its wake
rule is driven by the TRADER's session count — construct the interface
after the trader's first completed session, then evolve it every few
trader sessions and whenever the owner's inbox asks.

Run: supervisor.py --config /path/to/config.yaml
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ENGINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE_DIR))

from ledger import Ledger  # noqa: E402

POLL_SECONDS = 5

EMERGENCY_CHARTER = (
    "# Emergency charter (engine-embedded)\n\n"
    "The charter file for this run type could not be read, so you are "
    "working from this minimal engine fallback. Work from CLAUDE.md and "
    "your own state files. Keep it tight: verify your positions and "
    "account state, make sure any protection you intend is armed, then "
    "diagnose and repair your prompts/ charter files (`git log -- "
    "prompts/` shows what changed). Write state/wake.json and "
    "state/handoff.md, commit, and report plainly what happened.\n")


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}",
          flush=True)


class Supervisor:
    MODEL_CHOICES = {"fable", "opus", "sonnet", "haiku"}
    EFFORT_CHOICES = {"low", "medium", "high", "xhigh", "max"}

    def __init__(self, cfg: dict, cfg_path: str):
        self.cfg = cfg
        self.cfg_path = str(Path(cfg_path).resolve())
        self.role = cfg.get("role", "trader")
        self.workspace = Path(cfg["paths"]["workspace"])
        self.state = Path(cfg["paths"]["state"])
        self.logs = Path(cfg["paths"]["logs"]) / "sessions"
        self.state.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(cfg["paths"]["ledger"])
        # The UI role paces itself off the trader's activity: it reads
        # the trader's ledger (read-only) to count completed sessions.
        tl = cfg["paths"].get("trader_ledger")
        self.trader_ledger = Ledger(tl) if tl else None
        self.claude_bin = self._find_claude()
        self.retry_count = 0
        self._sched_warned = False

    @staticmethod
    def _find_claude() -> str:
        found = shutil.which("claude")
        if found:
            return found
        for cand in (Path.home() / ".local/bin/claude",
                     Path.home() / ".claude/local/claude",
                     Path("/usr/local/bin/claude")):
            if cand.exists():
                return str(cand)
        return "claude"

    def _cli_version(self) -> tuple:
        """Computed per call (no cache) so a CLI upgrade between launches
        takes effect on the very next session without a restart."""
        try:
            outp = subprocess.run([self.claude_bin, "--version"],
                                  capture_output=True, text=True, timeout=15)
            m = re.match(r"(\d+)\.(\d+)\.(\d+)", (outp.stdout or "").strip())
            return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
        except Exception:
            return (0, 0, 0)

    # ------------------------------------------------------------------
    # Wake decisions
    # ------------------------------------------------------------------

    def read_json(self, name: str) -> dict | None:
        f = self.state / name
        if not f.exists():
            return None
        try:
            return json.loads(f.read_text())
        except json.JSONDecodeError:
            return None

    def wake_due(self) -> tuple[str, dict] | None:
        if (self.state / "HALT").exists():
            return None  # the owner's kill switch: nothing runs
        if self.role == "ui":
            return self.ui_wake_due()

        # First boot: the awakening retries until one SUCCEEDS — a failed
        # launch must not count as having been born.
        if not self.ledger.has_successful_session():
            last = self.ledger.last_session_ts() or 0
            if time.time() - last < 120:
                return None
            return ("awakening", {"reason": "first awakening"})

        # Debounce: never launch within the minimum interval of the
        # previous session's END.
        last = self.ledger.last_session_ts() or 0
        min_gap = self.cfg["sessions"]["min_wake_interval_minutes"] * 60
        if time.time() - last < min_gap:
            return None

        # Sentinel wake request (a trigger fired, a fill landed). The
        # agent's sensors carry the same choice rights as its schedule:
        # a trigger or scanner may name the run_type, model, effort, and
        # charter its wake should run under (the wake_as block).
        req = self.read_json("wake_request.json")
        if req:
            wa = req.get("wake_as") or {}
            rt = self._sanitize_run_type(wa.get("run_type")) or "session"
            return (rt, {"reason": req.get("reason", "trigger"),
                         "trigger": req,
                         "run_type_hint": wa.get("run_type"),
                         "model_choice": wa.get("model"),
                         "effort_choice": wa.get("effort"),
                         "charter_file": wa.get("charter")})

        # The agent's own recurring schedule.
        sched_f = self.state / "schedule.json"
        if sched_f.exists():
            sched = self.read_json("schedule.json")
            if isinstance(sched, dict) and isinstance(sched.get("slots"), list):
                self._sched_warned = False
                due = self.agent_slot_due(sched)
                if due:
                    return due
            elif not self._sched_warned:
                # Present-but-broken means the aliveness floor only — the
                # default clock must not silently resurrect against the
                # agent's will just because it fat-fingered a JSON edit.
                self._sched_warned = True
                log("schedule.json present but unparseable — "
                    "aliveness floor only")
                self.ledger.record_event("supervisor", "schedule_unparseable",
                                         {})
            due = self.reflection_backstop_due()
            if due:
                return due

        # The agent's one-shot wake.
        wake = self.read_json("wake.json")
        if wake:
            raw = (wake.get("next_wake") or wake.get("wake_at")
                   or wake.get("next_wake_utc"))
            fire, guard_why, _due = self._schedule_decision(
                raw, last, time.time(),
                self.cfg["sessions"]["default_wake_minutes"],
                self.cfg["sessions"]["max_sleep_hours"],
                float(self.cfg["sessions"].get(
                    "schedule_trust_ceiling_hours", 96)))
            if fire and guard_why is None:
                rt = self._sanitize_run_type(wake.get("run_type")) or "session"
                return (rt, {"reason": wake.get("reason", "scheduled wake"),
                             "run_type_hint": wake.get("run_type"),
                             "model_choice": wake.get("model"),
                             "effort_choice": wake.get("effort"),
                             "charter_file": wake.get("charter"),
                             "one_shot": True})
            if fire:
                self.ledger.record_event(
                    "supervisor", "schedule_guard_wake",
                    {"scheduled": str(raw), "why": guard_why})
                return ("session", {"reason": (
                    "SCHEDULE GUARD (engine): state/wake.json is "
                    f"{guard_why}. Waking on the bounded fallback instead — "
                    "your schedule file was NOT consumed or altered. Verify "
                    "your positions cheaply, then fix or re-affirm "
                    "state/wake.json."), "schedule_guard": True})
        else:
            if time.time() - last > \
                    self.cfg["sessions"]["default_wake_minutes"] * 60:
                return ("session", {"reason": "no wake.json on file — "
                                    "default wake",
                                    "forgot_schedule": True})
        return None

    @staticmethod
    def _schedule_decision(raw, last, now, default_min, max_sleep_h,
                           ceiling_h=96.0):
        """One-shot scheduling math, pure so it is directly testable.
        Returns (fire, guard_why, due): guard_why is None when the
        agent's schedule fires as written; otherwise it names why the
        engine fell back. A valid schedule within the trust ceiling is
        honored AS WRITTEN — a long weekend sleep is legitimate. Beyond
        the ceiling, or with no parseable time, a bounded fallback fires
        and SAYS SO."""
        due = None
        try:
            due = datetime.fromisoformat(
                str(raw).replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            pass
        if due is not None and due - last <= ceiling_h * 3600:
            return (now >= due, None, due)
        if due is None:
            fallback = last + default_min * 60
            why = "missing a parseable next_wake"
        else:
            fallback = last + max_sleep_h * 3600
            why = (f"scheduled {(due - last) / 3600.0:.0f}h after the last "
                   f"session — beyond the {ceiling_h:.0f}h trust ceiling")
        return (now >= fallback, why, fallback)

    @staticmethod
    def _sanitize_run_type(rt) -> str | None:
        """Agent-invented run types become transcript filenames and
        ledger rows — keep them path-safe. Invalid -> None."""
        if not rt or not isinstance(rt, str):
            return None
        rt = rt.strip().lower()[:24]
        return rt if re.fullmatch(r"[a-z0-9][a-z0-9_-]*", rt) else None

    def agent_slot_due(self, sched: dict) -> tuple[str, dict] | None:
        """The agent's recurring cadence. Slot shape (run_type +
        at_local_time required, the rest optional):
          {"name": "...", "run_type": "reflection", "days": ["mon",...],
           "at_local_time": "16:45", "timezone": "America/New_York",
           "model": "...", "effort": "...", "charter": "prompts/X.md",
           "reason": "..."}
        A malformed slot is SKIPPED (never due-now). Slots are
        due-until-consumed — a busy afternoon delays a slot, never eats
        it — and consumed only by a FINISHED session of the slot's
        run_type at/after the slot time (a killed session doesn't
        consume the cycle)."""
        for s in sched.get("slots", []):
            try:
                rt = self._sanitize_run_type(s.get("run_type"))
                if not rt or rt == "awakening":
                    continue
                tz = ZoneInfo(str(s.get("timezone") or "UTC"))
                now = datetime.now(tz)
                days = [str(d).lower()[:3] for d in (s.get("days") or [])]
                if days and now.strftime("%a").lower() not in days:
                    continue
                hh, mm = map(int, str(s["at_local_time"]).split(":"))
                slot_dt = now.replace(hour=hh, minute=mm,
                                      second=0, microsecond=0)
                if now < slot_dt:
                    continue
                if self.ledger.last_finished_ts(rt) >= slot_dt.timestamp():
                    continue  # consumed
                name = str(s.get("name") or rt)
                return (rt, {
                    "reason": str(s.get("reason")
                                  or f"scheduled slot '{name}' (my own "
                                     "schedule.json)"),
                    "run_type_hint": rt,
                    "model_choice": s.get("model"),
                    "effort_choice": s.get("effort"),
                    "charter_file": s.get("charter"),
                    "from_slot": name})
            except Exception as e:
                log(f"schedule.json slot skipped (malformed): {e!r}")
                continue
        return None

    def reflection_backstop_due(self) -> tuple[str, dict] | None:
        """The aliveness floor — NOT a schedule. Fires only when no
        non-trading-class session has COMPLETED in a long while, meaning
        the agent's schedule stopped producing reflection entirely.
        Generous on purpose: it must never fight a deliberate cadence
        choice."""
        hrs = float(self.cfg["sessions"].get(
            "reflection_backstop_hours", 72))
        rows = self.ledger.query(
            "SELECT MAX(ts_end) t FROM sessions "
            "WHERE run_type NOT IN ('session') AND ts_end IS NOT NULL")
        last = float(rows[0]["t"] or 0) if rows else 0.0
        if not last or time.time() - last <= hrs * 3600:
            return None
        self.ledger.record_event("supervisor", "backstop_fired",
                                 {"hours_since_reflection":
                                  round((time.time() - last) / 3600, 1)})
        return ("reflection", {"reason": (
            "ENGINE BACKSTOP (aliveness floor): no reflection- or "
            "research-class session has completed in a long while. Your "
            "schedule file was NOT consumed or altered — this wake means "
            "state/schedule.json stopped producing reflection entirely "
            "(check it parses and says what you mean). Run whatever "
            "reflection your judgment calls for."), "backstop": True})

    # -- UI-manager role -------------------------------------------------

    def ui_wake_due(self) -> tuple[str, dict] | None:
        """The UI manager's pace is the TRADER's pace. Genesis: construct
        the interface once the trader has at least one completed session
        (so the constructor builds from a real transcript, not just the
        mission text). Steady state: evolve after every N trader
        sessions, or immediately when the owner's inbox requests a run."""
        if not self.trader_ledger:
            return None
        last = self.ledger.last_session_ts() or 0
        min_gap = self.cfg["sessions"]["min_wake_interval_minutes"] * 60
        if time.time() - last < min_gap:
            return None

        trader_done = self.trader_ledger.query(
            "SELECT COUNT(*) c FROM sessions WHERE ts_end IS NOT NULL")
        trader_count = trader_done[0]["c"] if trader_done else 0
        if trader_count == 0:
            return None

        if not self.ledger.has_successful_session():
            return ("construct", {"reason": (
                "FIRST CONSTRUCTION: the trader has completed its first "
                "session(s). Read the mission, the scaffold guide, and "
                "the transcripts, then build the base interface.")})

        # Owner pressed "run now" (or the inbox has a pending request).
        rr = self.cfg["paths"].get("run_request")
        if rr and Path(rr).exists():
            try:
                Path(rr).unlink()
            except OSError:
                pass
            return ("evolve", {"reason": (
                "OWNER REQUEST: the inbox has at least one message waiting "
                "and the owner asked for an immediate run. Read the inbox "
                "first; answer requests WITH interface.")})

        last_ui_end = float(self.ledger.query(
            "SELECT MAX(ts_end) t FROM sessions WHERE ts_end IS NOT NULL"
        )[0]["t"] or 0)
        new_trader = self.trader_ledger.count_finished_since(last_ui_end)
        every_n = int(self.cfg.get("ui", {}).get("trader_sessions_per_run", 4))
        max_gap_h = float(self.cfg.get("ui", {}).get("max_gap_hours", 12))
        if new_trader >= every_n or (
                new_trader >= 1
                and time.time() - last_ui_end > max_gap_h * 3600):
            return ("evolve", {"reason": (
                f"{new_trader} trader session(s) completed since the last "
                "interface pass. Read what happened; grow the interface "
                "to show it.")})
        return None

    # ------------------------------------------------------------------
    # Prompt assembly
    # ------------------------------------------------------------------

    def _resolve_charter(self, run_type: str, ctx: dict) -> str:
        """Charter resolution, first hit wins: the wake/slot's explicit
        `charter` path -> prompts/<RUN_TYPE>.md -> the role's default. A
        named-but-unreadable charter is a LOUD failure (event + engine
        fallback charter) — never a silent retry loop."""
        prompts = self.workspace / "prompts"
        candidates = []
        cf = ctx.get("charter_file")
        if cf and isinstance(cf, str):
            p = (self.workspace / cf).resolve()
            if str(p).startswith(str(self.workspace.resolve())):
                candidates.append(p)
        candidates.append(prompts / f"{run_type.upper()}.md")
        default = {"awakening": "AWAKENING.md",
                   "construct": "CONSTRUCT.md",
                   "evolve": "EVOLVE.md",
                   "reflection": "REFLECTION.md",
                   "research": "RESEARCH.md"}.get(run_type, "SESSION.md")
        candidates.append(prompts / default)
        candidates.append(prompts / ("EVOLVE.md" if self.role == "ui"
                                     else "SESSION.md"))
        for p in candidates:
            try:
                text = p.read_text(encoding="utf-8")
                if text.strip():
                    return text
            except OSError:
                continue
        self.ledger.record_event("supervisor", "charter_missing",
                                 {"run_type": run_type,
                                  "charter": str(ctx.get("charter_file"))})
        log(f"charter missing for run type '{run_type}' — emergency charter")
        return EMERGENCY_CHARTER

    def build_prompt(self, run_type: str, ctx: dict) -> str:
        body = self._resolve_charter(run_type, ctx)
        last = self.ledger.last_session_ts()
        elapsed = f"{(time.time() - last) / 3600:.1f}h" if last else "n/a"
        header = [
            f"WAKE CONTEXT — {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            f"- Role: {self.role} | run type: {run_type}",
            f"- Why you are awake: {ctx.get('reason')}",
            f"- Time since previous session: {elapsed}",
            "- SESSION LIFETIME: this session ends the moment you stop "
            "replying with tool calls. Background tasks die with it and "
            "can NEVER re-invoke you — never park a duty on one. Close "
            "out properly before ending: schedule written, handoff "
            "written, work committed.",
        ]
        if ctx.get("trigger"):
            header.append("- Trigger detail: "
                          + json.dumps(ctx["trigger"], default=str))
        if ctx.get("forgot_schedule"):
            header.append("- NOTE: your previous session ended without a "
                          "valid schedule. Investigate why, and do not "
                          "repeat it.")
        return "\n".join(header) + "\n\n---\n\n" + body

    # ------------------------------------------------------------------
    # Session launch
    # ------------------------------------------------------------------

    def launch(self, run_type: str, ctx: dict) -> None:
        models = self.cfg.get("models") or {}
        choice = ctx.get("model_choice")
        if choice and str(choice).lower() not in self.MODEL_CHOICES:
            log(f"ignoring unknown model choice {choice!r}")
            choice = None
        alias = (str(choice).lower() if choice else None) \
            or models.get(ctx.get("run_type_hint") or run_type) \
            or models.get("default", "opus")
        echoice = ctx.get("effort_choice")
        if echoice and str(echoice).lower() not in self.EFFORT_CHOICES:
            log(f"ignoring unknown effort choice {echoice!r}")
            echoice = None
        effort = (str(echoice).lower() if echoice else None) \
            or (models.get("effort") or {}).get(
                ctx.get("run_type_hint") or run_type) \
            or (models.get("effort") or {}).get("default")

        max_turns = int((self.cfg.get(run_type) or {}).get(
            "max_turns", self.cfg["sessions"].get("max_turns", 600)))
        session_uuid = str(uuid.uuid4())
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        transcript = self.logs / f"{stamp}-{run_type}.jsonl"
        prompt = self.build_prompt(run_type, ctx)

        # Snapshot the exact prompt this session ran under: charters are
        # agent-owned and edited over time — the audit record of what
        # each session actually read must survive any later edit.
        try:
            transcript.with_suffix(".prompt.md").write_text(
                prompt, encoding="utf-8")
        except OSError as e:
            log(f"prompt snapshot failed: {e!r}")

        import os
        env = dict(os.environ)
        env["MIND_CONFIG"] = self.cfg_path
        env["MIND_SESSION_ID"] = session_uuid
        # Background SUBAGENTS are waited for at session exit; a generous
        # ceiling keeps a late deep helper from being truncated. The
        # absolute session deadline below still bounds everything.
        env.setdefault("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS", "1800000")

        cmd = [self.claude_bin, "-p",
               "--output-format", "stream-json", "--verbose",
               "--model", alias,
               "--max-turns", str(max_turns),
               "--dangerously-skip-permissions"]
        if effort:
            cmd += ["--effort", effort]
        mcp_cfg = self.workspace / ".mcp.json"
        if mcp_cfg.exists():
            cmd += ["--mcp-config", str(mcp_cfg)]
        if self._cli_version() >= (2, 1, 211):
            cmd.append("--forward-subagent-text")
        log(f"launch {run_type} model={alias}"
            f"{f' effort={effort}' if effort else ''} "
            f"turns<={max_turns} -> {transcript.name}")
        self.ledger.start_session(session_uuid, run_type, alias,
                                  ctx.get("reason", ""), str(transcript))
        # Consume the wake request ONLY when this launch services it —
        # an unconditional delete could eat a request filed in the
        # instant between the wake decision and here.
        if ctx.get("trigger"):
            (self.state / "wake_request.json").unlink(missing_ok=True)

        result: dict = {}
        results: list[dict] = []
        exit_code = -1
        timeout = int((self.cfg.get(run_type) or {}).get(
            "session_timeout_minutes",
            self.cfg["sessions"]["session_timeout_minutes"])) * 60
        try:
            with open(transcript, "w", encoding="utf-8") as tf:
                proc = subprocess.Popen(
                    cmd, cwd=str(self.workspace), env=env,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8")
                proc.stdin.write(prompt)
                proc.stdin.close()
                # Reader thread + absolute deadline: a deadline checked
                # only when a LINE arrives is starved by a silently hung
                # session and blocks the whole single-threaded loop. The
                # wall clock must fire regardless of output.
                import queue as queue_mod
                import threading
                q: queue_mod.Queue = queue_mod.Queue()

                def _reader(stream, out_q):
                    try:
                        for ln in stream:
                            out_q.put(ln)
                    except Exception:
                        pass
                    finally:
                        out_q.put(None)

                threading.Thread(target=_reader, args=(proc.stdout, q),
                                 daemon=True).start()
                deadline = time.time() + timeout
                while True:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        proc.kill()
                        result.setdefault("subtype", "timeout")
                        log("session timeout — killed")
                        break
                    try:
                        line = q.get(timeout=min(remaining, 10))
                    except queue_mod.Empty:
                        continue
                    if line is None:
                        break
                    tf.write(line)
                    tf.flush()
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            evt = json.loads(line)
                            if evt.get("type") == "result":
                                results.append(evt)
                        except json.JSONDecodeError:
                            pass
                exit_code = proc.wait(timeout=30)
            # A session woken again by a late subagent emits MULTIPLE
            # result events. Turns and tokens SUM across them; cost is
            # cumulative, so it takes the MAX (a sum would double-count).
            if results:
                result = dict(results[-1])
                result.setdefault("subtype", "unknown")
                if len(results) > 1:
                    result["num_turns"] = sum(
                        int(r.get("num_turns") or 0) for r in results)
                    result["total_cost_usd"] = max(
                        float(r.get("total_cost_usd") or 0) for r in results)
                    merged = dict(result.get("usage") or {})
                    for k in ("input_tokens", "output_tokens"):
                        merged[k] = sum(
                            int((r.get("usage") or {}).get(k) or 0)
                            for r in results)
                    result["usage"] = merged
        except FileNotFoundError:
            log(f"FATAL: claude binary not found ({self.claude_bin})")
            self.ledger.end_session(session_uuid, 127, 0, 0, 0, 0,
                                    "claude binary not found")
            self.claude_bin = self._find_claude()
            time.sleep(300)
            return
        except Exception as e:
            log(f"launch error: {e!r}")

        self.finish(session_uuid, run_type, exit_code, result, alias, ctx)

    # ------------------------------------------------------------------

    def finish(self, session_uuid: str, run_type: str, exit_code: int,
               result: dict, alias: str, ctx: dict) -> None:
        usage = result.get("usage") or {}
        cost = float(result.get("total_cost_usd") or 0)
        full_report = result.get("result") or ""
        self.ledger.end_session(
            session_uuid, exit_code, cost,
            int(usage.get("input_tokens") or 0),
            int(usage.get("output_tokens") or 0),
            int(result.get("num_turns") or 0), full_report[:2000])
        subtype = result.get("subtype", "unknown")
        log(f"session done exit={exit_code} subtype={subtype} "
            f"cost=${cost:.2f}")

        ok = exit_code == 0 and subtype in ("success", "unknown")
        if ok:
            self.retry_count = 0
            if self.role == "trader":
                self._forgot_check(run_type, ctx)
                self._prune_wake_request()
            return

        # Refusal fallback: a frontier-tier false positive gets ONE
        # retry on the next tier, keyed off the launched alias.
        if alias == "fable" and self.retry_count == 0 \
                and "refus" in json.dumps(result).lower():
            log("possible refusal — retrying once on opus")
            self.retry_count += 1
            self.launch(run_type, dict(
                ctx, reason=ctx.get("reason", "") + " (retry)",
                model_choice="opus"))
            return
        self.retry_count += 1
        if self.retry_count <= 3:
            backoff = 60 * 2 ** (self.retry_count - 1)
            log(f"session failed — retry {self.retry_count}/3 in {backoff}s")
            time.sleep(backoff)
        else:
            self.retry_count = 0
            self.ledger.record_event("supervisor", "retries_exhausted",
                                     result)
            log("3 consecutive failures — sleeping 1h")
            time.sleep(3600)

    def _forgot_check(self, run_type: str, ctx: dict) -> None:
        """Forgot to schedule? "Forgot" means NO VALID FUTURE WAKE ON
        FILE at session end — never "file untouched": a still-valid
        schedule the session merely verified STANDS. Non-destructive:
        every field the agent wrote is preserved; the default names what
        was missing. Sessions launched from recurring slots (and
        reflection/research classes) don't own the one-shot schedule and
        are exempt."""
        if ctx.get("from_slot") or ctx.get("backstop") \
                or run_type in ("reflection", "research", "awakening"):
            return
        wake_f = self.state / "wake.json"
        nxt_ts = 0.0
        w: dict = {}
        try:
            w = json.loads(wake_f.read_text())
            raw = (w.get("next_wake") or w.get("wake_at")
                   or w.get("next_wake_utc"))
            nxt_ts = datetime.fromisoformat(
                str(raw).replace("Z", "+00:00")).timestamp()
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
        if nxt_ts > time.time():
            return
        nxt = datetime.now(timezone.utc) + timedelta(
            minutes=self.cfg["sessions"]["default_wake_minutes"])
        keys = ", ".join(sorted(w.keys())) if isinstance(w, dict) and w \
            else "none (file missing/unparseable)"
        merged = dict(w) if isinstance(w, dict) else {}
        if merged.get("reason"):
            merged["orphaned_reason"] = merged["reason"]
        merged.update({
            "next_wake": nxt.isoformat(),
            "reason": ("default (previous session left no parseable "
                       f"next_wake — keys found: {keys}). Its original "
                       "fields are preserved in this file; verify your "
                       "positions, then re-schedule properly."),
            "forgot_schedule": True})
        wake_f.write_text(json.dumps(merged, indent=2))
        log(f"agent forgot wake.json — default applied (keys: {keys})")

    def _prune_wake_request(self) -> None:
        """A stale pending wake request whose trigger the session just
        removed is a cleared tripwire — drop it so it cannot re-fire the
        agent's own past. Requests without a trigger id (protective
        adoptions) are never dropped."""
        req = self.read_json("wake_request.json")
        if not req:
            return
        tid = ((req.get("context") or {}).get("trigger") or {}).get("id")
        if not tid:
            return
        trigs = self.read_json("triggers.json") or {}
        ids = {t.get("id") for t in trigs.get("triggers", [])
               if isinstance(t, dict)}
        if tid not in ids:
            (self.state / "wake_request.json").unlink(missing_ok=True)
            self.ledger.record_event("supervisor", "wake_request_pruned",
                                     {"trigger_id": tid})
            log("pruned stale wake_request after session")

    def write_status(self) -> None:
        wake = self.read_json("wake.json") or {}
        (self.state / "status.json").write_text(json.dumps({
            "updated": datetime.now(timezone.utc).isoformat(),
            "role": self.role,
            "halt": (self.state / "HALT").exists(),
            "next_wake": wake.get("next_wake"),
            "next_wake_reason": wake.get("reason"),
            "open_trades": len(self.ledger.open_trades())
            if self.role == "trader" else None,
        }, indent=2))

    def run(self) -> None:
        log(f"supervisor up: role={self.role} workspace={self.workspace}")
        while True:
            try:
                due = self.wake_due()
                if due:
                    self.launch(*due)
                self.write_status()
            except Exception as e:
                log(f"loop error: {e!r}")
                self.ledger.record_event("supervisor", "error", repr(e))
                time.sleep(30)
            time.sleep(POLL_SECONDS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    Supervisor(cfg, args.config).run()


if __name__ == "__main__":
    main()
