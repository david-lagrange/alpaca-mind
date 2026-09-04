#!/usr/bin/env python3
"""usage_collect — the operator's usage store, built from Claude Code's own
session files.

Runs as root on a timer. Reads the CLI's per-session transcripts under
each agent user's ~/.claude/projects (reading only; those files are the
CLI's and are never modified) and aggregates the token usage each one
carries into a small SQLite database that the agent users cannot open.
The engine the agents read computes none of this; this script is the
only place it exists. The UI manager may read the store (group read)
and show it to the owner behind the login. The trader has no path to
it — by permission, and by the absence of any reference to it in the
files the trader can reach.

Tables:
  files(path PK, size, mtime)                    what has been read
  sessions(agent, session_id PK, file, first_ts, last_ts, messages,
           input_tokens, cache_creation_input_tokens,
           cache_read_input_tokens, output_tokens)
  models(agent, session_id, model, messages, input_tokens,
         cache_creation_input_tokens, cache_read_input_tokens,
         output_tokens)                           per-model breakdown
No pricing is stored: prices drift, tokens do not. Whoever reads the
store applies the rates of the day.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens",
              "cache_read_input_tokens", "output_tokens")

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY, size INTEGER, mtime REAL);
CREATE TABLE IF NOT EXISTS sessions (
    agent TEXT NOT NULL, session_id TEXT PRIMARY KEY, file TEXT,
    first_ts TEXT, last_ts TEXT, messages INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    cache_creation_input_tokens INTEGER DEFAULT 0,
    cache_read_input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS models (
    agent TEXT NOT NULL, session_id TEXT NOT NULL, model TEXT NOT NULL,
    messages INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    cache_creation_input_tokens INTEGER DEFAULT 0,
    cache_read_input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    PRIMARY KEY (session_id, model));
CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions (agent, first_ts);
"""


def session_files(home: Path):
    root = home / ".claude" / "projects"
    if not root.is_dir():
        return
    for p in root.rglob("*.jsonl"):
        if p.is_file():
            yield p


def parse(path: Path) -> tuple[dict, dict]:
    """One CLI transcript -> (session totals, per-model totals)."""
    totals = {k: 0 for k in USAGE_KEYS}
    totals.update({"messages": 0, "first_ts": None, "last_ts": None,
                   "session_id": None})
    per_model: dict[str, dict] = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            sid = rec.get("sessionId")
            if sid and not totals["session_id"]:
                totals["session_id"] = sid
            if rec.get("type") != "assistant":
                continue
            msg = rec.get("message") or {}
            usage = msg.get("usage") or {}
            if not isinstance(usage, dict):
                continue
            ts = rec.get("timestamp")
            if ts:
                totals["first_ts"] = totals["first_ts"] or ts
                totals["last_ts"] = ts
            model = str(msg.get("model") or "unknown")
            m = per_model.setdefault(model, {k: 0 for k in USAGE_KEYS}
                                     | {"messages": 0})
            totals["messages"] += 1
            m["messages"] += 1
            for k in USAGE_KEYS:
                v = int(usage.get(k) or 0)
                totals[k] += v
                m[k] += v
    if not totals["session_id"]:
        totals["session_id"] = path.stem
    return totals, per_model


def collect(db_path: Path, agents: dict[str, Path]) -> int:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    seen = {r[0]: (r[1], r[2]) for r in
            conn.execute("SELECT path, size, mtime FROM files")}
    updated = 0
    for agent, home in agents.items():
        for p in session_files(home):
            st = p.stat()
            if seen.get(str(p)) == (st.st_size, st.st_mtime):
                continue
            totals, per_model = parse(p)
            sid = totals["session_id"]
            conn.execute(
                "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (agent, sid, str(p), totals["first_ts"], totals["last_ts"],
                 totals["messages"], *[totals[k] for k in USAGE_KEYS]))
            conn.execute("DELETE FROM models WHERE session_id=?", (sid,))
            for model, m in per_model.items():
                conn.execute(
                    "INSERT OR REPLACE INTO models VALUES (?,?,?,?,?,?,?,?)",
                    (agent, sid, model, m["messages"],
                     *[m[k] for k in USAGE_KEYS]))
            conn.execute("INSERT OR REPLACE INTO files VALUES (?,?,?)",
                         (str(p), st.st_size, st.st_mtime))
            updated += 1
    conn.commit()
    conn.close()
    return updated


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/var/lib/alpaca-mind/ops/usage.db")
    ap.add_argument("--agent", action="append", default=[],
                    help="name=home, repeatable (default: mind and ui)")
    ap.add_argument("--group", default="ui",
                    help="group that may read the store")
    args = ap.parse_args()
    agents = {}
    for a in args.agent or ["mind=/srv/mind", "ui=/srv/ui"]:
        name, _, home = a.partition("=")
        agents[name] = Path(home)
    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    n = collect(db, agents)
    try:
        import grp
        gid = grp.getgrnam(args.group).gr_gid
        os.chown(db.parent, 0, gid)
        os.chmod(db.parent, 0o750)
        for f in db.parent.glob(db.name + "*"):
            os.chown(f, 0, gid)
            os.chmod(f, 0o640)
    except (KeyError, PermissionError):
        pass
    print(f"usage store {db}: {n} session file(s) (re)read")
    return 0


if __name__ == "__main__":
    sys.exit(main())
