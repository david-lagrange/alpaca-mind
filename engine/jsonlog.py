"""jsonlog — structured logging for every engine component.

Two sinks, one call:
  * a concise human line to STDERR (journald picks it up; stderr because
    some components — the trade CLI, session hooks — use stdout as a
    machine-read protocol that log lines must never corrupt), and
  * a full JSONL record appended to <log_dir>/daily/YYYY-MM-DD.jsonl
    (UTC dating, so the day boundary is unambiguous). The owner's
    interface reads these files; an AI assistant diagnosing the system
    reads them too — that reader is who the key-values are for.

Conventions:
  * Levels: debug (chatty mechanics), info (lifecycle and decisions),
    warn (degraded but handled), error (failures, with exception
    context). LOG_LEVEL filters the stderr sink only; the daily file
    receives every level, because the record that explains a failure is
    usually written before anyone knows a failure is coming.
  * Events are short snake_case names ("session_launch", "trigger_fire")
    with the story in key-values, so the stream is both greppable and
    machine-filterable.
  * Logging must never break the host program: a file-sink failure
    degrades to stderr-only and says so once.
  * Logging must never fill the disk. Three self-enforcing bounds, no
    external housekeeping required: a per-day file byte cap (a runaway
    loop hits the ceiling, one "log_file_capped" marker is written,
    the rest of the day's records are dropped from the file — stderr
    keeps flowing so journald still shows the loop), a total-directory
    byte cap (oldest days deleted first), and day-count retention.
    Retention and the directory cap run automatically on day rollover.
  * No secrets: callers never pass keys, tokens, or auth headers.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

_LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}
_lock = threading.Lock()

# Disk-safety bounds (env-overridable). Generous for real operation,
# small next to the instance disk — the point is that no defect can
# convert logging into an outage.
_MAX_FILE_MB = float(os.environ.get("JSONLOG_MAX_FILE_MB", "64"))
_MAX_TOTAL_MB = float(os.environ.get("JSONLOG_MAX_TOTAL_MB", "512"))
_KEEP_DAYS = int(os.environ.get("JSONLOG_KEEP_DAYS", "7"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JsonLogger:
    def __init__(self, component: str, log_dir: str | os.PathLike | None = None,
                 min_level: str | None = None, _ctx: dict | None = None):
        self.component = component
        d = log_dir if log_dir is not None else os.environ.get("JSONLOG_DIR")
        self.daily_dir: Path | None = (Path(d) / "daily") if d else None
        lvl = (min_level or os.environ.get("LOG_LEVEL") or "info").lower()
        self.min_level = _LEVELS.get(lvl, 20)
        self._ctx = dict(_ctx or {})
        self._file_sink_warned = False
        self._day: str | None = None
        self._capped = False

    def bind(self, **kv) -> "JsonLogger":
        """A child logger whose records all carry these key-values —
        e.g. bind(session_id=...) so every line of a session correlates."""
        child = JsonLogger(self.component, min_level="debug")
        child.daily_dir = self.daily_dir
        child.min_level = self.min_level
        child._ctx = {**self._ctx, **{k: v for k, v in kv.items() if v is not None}}
        return child

    # -- level methods ---------------------------------------------------

    def debug(self, event: str, **kv) -> None:
        self._emit("debug", event, kv)

    def info(self, event: str, **kv) -> None:
        self._emit("info", event, kv)

    def warn(self, event: str, **kv) -> None:
        self._emit("warn", event, kv)

    def error(self, event: str, exc: BaseException | None = None, **kv) -> None:
        if exc is not None:
            kv.setdefault("error", repr(exc))
            tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
            kv.setdefault("trace", "".join(tb)[-2000:])
        self._emit("error", event, kv)

    # -- emission --------------------------------------------------------

    def _emit(self, level: str, event: str, kv: dict) -> None:
        rec = {"ts": _now().isoformat(timespec="milliseconds"),
               "level": level, "component": self.component, "event": event}
        rec.update(self._ctx)
        for k, v in kv.items():
            if v is not None:
                rec[k] = v
        if _LEVELS[level] >= self.min_level:
            self._stderr_line(level, event, rec)
        self._file_line(rec)

    def _stderr_line(self, level: str, event: str, rec: dict) -> None:
        parts = [f"[{level}] {self.component} {event}"]
        for k, v in rec.items():
            if k in ("ts", "level", "component", "event", "trace"):
                continue
            s = str(v)
            if len(s) > 200:
                s = s[:200] + "…"
            parts.append(f"{k}={s}")
        try:
            print(" ".join(parts), file=sys.stderr, flush=True)
        except OSError:
            pass  # a dead stderr must not take the program with it

    def _file_line(self, rec: dict) -> None:
        if self.daily_dir is None:
            return
        try:
            day = _now().strftime("%Y-%m-%d")
            if day != self._day:
                # Day rollover: retention and the directory cap enforce
                # themselves here, so no housekeeping job is a single
                # point of disk-safety failure.
                self._day = day
                self._capped = False
                _prune_dir(self.daily_dir)
            path = self.daily_dir / f"{day}.jsonl"
            try:
                if path.stat().st_size >= _MAX_FILE_MB * 1024 * 1024:
                    if not self._capped:
                        self._capped = True
                        marker = json.dumps({
                            "ts": rec.get("ts"), "level": "warn",
                            "component": self.component,
                            "event": "log_file_capped",
                            "limit_mb": _MAX_FILE_MB,
                            "note": ("daily file reached its byte cap; "
                                     "further records today are dropped "
                                     "from the file (stderr/journald "
                                     "unaffected)")})
                        with _lock, open(path, "a", encoding="utf-8") as f:
                            f.write(marker + "\n")
                    return
            except OSError:
                pass  # no file yet — a fresh day, write proceeds
            self.daily_dir.mkdir(parents=True, exist_ok=True)
            line = json.dumps(rec, default=str, ensure_ascii=False)
            with _lock, open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            if not self._file_sink_warned:
                self._file_sink_warned = True
                try:
                    print(f"[warn] {self.component} log_file_sink_down "
                          f"error={e!r} — continuing on stderr only",
                          file=sys.stderr, flush=True)
                except OSError:
                    pass


def get_logger(component: str, log_dir: str | os.PathLike | None = None) -> JsonLogger:
    return JsonLogger(component, log_dir=log_dir)


def _prune_dir(daily: Path, keep_days: int | None = None) -> int:
    """Enforce retention (keep_days) and the total-directory byte cap,
    oldest days first, never touching the newest file. Returns how many
    files were removed. Never raises."""
    removed = 0
    try:
        if not daily.is_dir():
            return 0
        days = keep_days if keep_days is not None else _KEEP_DAYS
        cutoff_day = (_now() - timedelta(days=days)).strftime("%Y-%m-%d")
        # YYYY-MM-DD names sort chronologically.
        files = sorted(daily.glob("*.jsonl"))
        kept: list[Path] = []
        for f in files:
            if f.stem < cutoff_day:
                try:
                    f.unlink()
                    removed += 1
                except OSError:
                    pass
            else:
                kept.append(f)
        cap = _MAX_TOTAL_MB * 1024 * 1024
        sizes = []
        for f in kept:
            try:
                sizes.append(f.stat().st_size)
            except OSError:
                sizes.append(0)
        total = sum(sizes)
        i = 0
        while total > cap and i < len(kept) - 1:
            try:
                kept[i].unlink()
                removed += 1
                total -= sizes[i]
            except OSError:
                pass
            i += 1
    except OSError:
        pass
    return removed


def prune_daily(log_dir: str | os.PathLike, keep_days: int | None = None) -> int:
    """Delete daily files beyond retention or the total byte cap under
    <log_dir>/daily. Returns how many were removed. Safe to call often;
    never raises. (Loggers also self-prune on day rollover — this
    exists for explicit housekeeping calls.)"""
    return _prune_dir(Path(log_dir) / "daily", keep_days)
