"""The ledger — the agent's quantitative memory (SQLite).

Written automatically by the trade tool (orders/trades), the sentinel
(balance snapshots, adopted fills), and the supervisor (sessions). The
agent reads it freely (via trade subcommands or sqlite3 SELECTs) but
never hand-writes rows — that discipline is what keeps it truthful.

The venue remains the source of truth for live state; the ledger is the
durable local mirror and audit trail that links every trade to the
session (and therefore the full reasoning transcript) that produced it.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from jsonlog import get_logger

# Venue order statuses that mean "still live at the venue — keep
# watching". Shared vocabulary: the sentinel polls these for fill
# adoption; the trade tool refuses to stack a second exit on a trade
# that already has one resting.
OPEN_ORDER_STATUSES = ("pending", "pending_new", "new", "accepted",
                       "submitted", "partial", "partially_filled",
                       "held", "cancel_requested")

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    venue TEXT NOT NULL,
    venue_order_id TEXT,
    symbol TEXT NOT NULL,             -- underlying, or OCC option symbol
    side TEXT NOT NULL,               -- buy | sell
    order_type TEXT NOT NULL,         -- market | limit | stop | stop_limit
    qty REAL,
    notional REAL,
    limit_price REAL,
    stop_price REAL,
    status TEXT NOT NULL,
    filled_qty REAL DEFAULT 0,
    filled_avg_price REAL,
    fees REAL DEFAULT 0,
    session_id TEXT,                  -- agent session that placed it
    trade_id INTEGER,                 -- FK -> trades.id once associated
    structure_id TEXT,                -- groups the legs of one multi-leg order
    legs TEXT,                        -- JSON: per-leg detail for multi-leg orders
    raw TEXT,                         -- venue response JSON
    thesis TEXT                       -- why (carried to the trade if the fill
                                      -- lands after the placing session ended)
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_open REAL NOT NULL,
    ts_close REAL,
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,             -- underlying, or OCC option symbol
    side TEXT NOT NULL,               -- long | short
    qty REAL,
    entry_price REAL,
    exit_price REAL,
    fees REAL DEFAULT 0,
    pnl REAL,                         -- realized, net of fees, set on close
    pnl_pct REAL,
    thesis TEXT,                      -- required at open: why this trade exists
    exit_reason TEXT,
    status TEXT NOT NULL DEFAULT 'open',   -- open | closed
    structure_id TEXT,                -- groups the legs of one options structure
    session_id_open TEXT,
    session_id_close TEXT,
    reviewed INTEGER DEFAULT 0,       -- set after the agent's own post-mortem
    meta TEXT
);

CREATE TABLE IF NOT EXISTS balance_snapshots (
    ts REAL NOT NULL,
    equity REAL,
    cash REAL,
    positions_value REAL,
    raw TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    ts_start REAL NOT NULL,
    ts_end REAL,
    run_type TEXT NOT NULL,
    model TEXT,
    wake_reason TEXT,
    exit_code INTEGER,
    num_turns INTEGER DEFAULT 0,
    transcript_path TEXT,
    result_summary TEXT
);

CREATE TABLE IF NOT EXISTS events (
    ts REAL NOT NULL,
    source TEXT NOT NULL,             -- sentinel | supervisor | trade_tool
    kind TEXT NOT NULL,
    detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_ts ON orders (ts);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades (status);
CREATE INDEX IF NOT EXISTS idx_sessions_ts ON sessions (ts_start);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts);
"""


SESSION_COLUMNS = ("id", "ts_start", "ts_end", "run_type", "model",
                   "wake_reason", "exit_code", "num_turns",
                   "transcript_path", "result_summary")


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._conform("sessions", SESSION_COLUMNS)

    def _conform(self, table: str, columns: tuple) -> None:
        """A ledger created under an earlier schema may carry columns this
        one does not define. Rebuild the table to the current shape —
        every row kept, columns outside the schema dropped — so every
        reader sees one schema. A no-op when the shapes already match;
        a concurrent opener that loses the lock simply leaves it to the
        one that holds it."""
        have = [r[1] for r in self._conn.execute(
            f"PRAGMA table_info({table})").fetchall()]
        if set(have) == set(columns):
            return
        keep = ", ".join(c for c in columns if c in have)
        ddl = SCHEMA[SCHEMA.index(f"CREATE TABLE IF NOT EXISTS {table} ("):]
        ddl = ddl[:ddl.index(");") + 2].replace("IF NOT EXISTS ", "")
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(f"ALTER TABLE {table} RENAME TO {table}__old")
            self._conn.execute(ddl)
            self._conn.execute(
                f"INSERT INTO {table} ({keep}) SELECT {keep} FROM {table}__old")
            self._conn.execute(f"DROP TABLE {table}__old")
            self._conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_ts ON {table} (ts_start)")
            self._conn.commit()
        except sqlite3.OperationalError:
            self._conn.rollback()

    # -- generic helpers ------------------------------------------------

    def _insert(self, table: str, row: dict[str, Any]) -> int:
        keys = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        cur = self._conn.execute(
            f"INSERT INTO {table} ({keys}) VALUES ({marks})", list(row.values())
        )
        self._conn.commit()
        return cur.lastrowid

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    # -- orders / trades (written by trade.py) --------------------------

    def record_order(self, **kw) -> int:
        kw.setdefault("ts", time.time())
        for k in ("raw", "legs"):
            if isinstance(kw.get(k), (dict, list)):
                kw[k] = json.dumps(kw[k], default=str)
        return self._insert("orders", kw)

    def update_order(self, order_id: int, **kw) -> None:
        for k in ("raw", "legs"):
            if isinstance(kw.get(k), (dict, list)):
                kw[k] = json.dumps(kw[k], default=str)
        sets = ", ".join(f"{k}=?" for k in kw)
        self._conn.execute(
            f"UPDATE orders SET {sets} WHERE id=?", [*kw.values(), order_id]
        )
        self._conn.commit()

    def open_trade(self, **kw) -> int:
        kw.setdefault("ts_open", time.time())
        kw.setdefault("status", "open")
        if isinstance(kw.get("meta"), (dict, list)):
            kw["meta"] = json.dumps(kw["meta"], default=str)
        return self._insert("trades", kw)

    def close_trade(self, trade_id: int, exit_price: float, fees_add: float,
                    exit_reason: str, session_id: Optional[str]) -> dict:
        t = self.query("SELECT * FROM trades WHERE id=?", (trade_id,))
        if not t:
            raise ValueError(f"trade {trade_id} not found")
        t = t[0]
        qty, entry = t["qty"] or 0, t["entry_price"] or 0
        fees = (t["fees"] or 0) + fees_add
        direction = 1 if t["side"] == "long" else -1
        # Option prices are quoted per share while a contract controls a
        # multiple (usually 100); the multiplier is stored on the trade's
        # meta at open so P&L reflects dollars, not quote points.
        mult = self._multiplier(t)
        gross = direction * (exit_price - entry) * qty * mult
        pnl = gross - fees
        basis = abs(entry * qty * mult)
        pnl_pct = (pnl / basis * 100) if basis else None
        self._conn.execute(
            """UPDATE trades SET ts_close=?, exit_price=?, fees=?, pnl=?, pnl_pct=?,
               exit_reason=?, status='closed', session_id_close=? WHERE id=?""",
            (time.time(), exit_price, fees, pnl, pnl_pct, exit_reason,
             session_id, trade_id),
        )
        self._conn.commit()
        return {"trade_id": trade_id, "pnl": pnl, "pnl_pct": pnl_pct, "fees": fees}

    def split_close_trade(self, trade_id: int, filled_qty: float,
                          exit_price: float, fees_add: float,
                          exit_reason: str,
                          session_id: Optional[str]) -> dict:
        """Partial exit: close ONLY the filled quantity as a new closed
        trade row and shrink the original to the remainder. Booking a
        partial fill as a full close silently deletes the surviving
        position from the ledger — the venue and the ledger must never
        disagree about what is still open.

        The returned dict always carries pnl_pct: callers print the
        close summary unconditionally, and an absent key aborts the CLI
        after the ledger has already committed."""
        t = self.query("SELECT * FROM trades WHERE id=?", (trade_id,))
        if not t:
            raise ValueError(f"trade {trade_id} not found")
        t = t[0]
        qty = t["qty"] or 0
        if not (0 < filled_qty < qty):
            raise ValueError(f"split_close needs 0 < filled ({filled_qty}) "
                             f"< trade qty ({qty}) — use close_trade")
        entry = t["entry_price"] or 0
        direction = 1 if t["side"] == "long" else -1
        mult = self._multiplier(t)
        pnl = direction * (exit_price - entry) * filled_qty * mult - fees_add
        basis = abs(entry * filled_qty * mult)
        cur = self._conn.execute(
            """INSERT INTO trades (ts_open, ts_close, venue, symbol, side,
               qty, entry_price, exit_price, fees, pnl, pnl_pct, thesis,
               exit_reason, status, structure_id, session_id_open,
               session_id_close, reviewed, meta)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'closed',?,?,?,0,?)""",
            (t["ts_open"], time.time(), t["venue"], t["symbol"], t["side"],
             filled_qty, entry, exit_price, fees_add, pnl,
             (pnl / basis * 100) if basis else None,
             t["thesis"], exit_reason, t["structure_id"],
             t["session_id_open"], session_id,
             json.dumps({"split_from_trade": trade_id})))
        self._conn.execute(
            "UPDATE trades SET qty=? WHERE id=?",
            (qty - filled_qty, trade_id))
        self._conn.commit()
        return {"trade_id": cur.lastrowid, "pnl": pnl,
                "pnl_pct": (pnl / basis * 100) if basis else None,
                "remainder_trade_id": trade_id,
                "remainder_qty": qty - filled_qty}

    @staticmethod
    def _multiplier(trade_row: dict) -> float:
        try:
            meta = json.loads(trade_row.get("meta") or "{}")
            return float(meta.get("multiplier") or 1)
        except (ValueError, TypeError):
            # falling back to 1 mis-scales option P&L, so say so
            get_logger("ledger").warn("trade_meta_unparseable",
                                      trade_id=trade_row.get("id"))
            return 1.0

    def update_trade(self, trade_id: int, **kw) -> None:
        if isinstance(kw.get("meta"), (dict, list)):
            kw["meta"] = json.dumps(kw["meta"], default=str)
        sets = ", ".join(f"{k}=?" for k in kw)
        self._conn.execute(
            f"UPDATE trades SET {sets} WHERE id=?", [*kw.values(), trade_id])
        self._conn.commit()

    def open_trades(self) -> list[dict]:
        return self.query("SELECT * FROM trades WHERE status='open' ORDER BY ts_open")

    def realized_pnl_since(self, ts: float) -> float:
        rows = self.query(
            "SELECT COALESCE(SUM(pnl),0) s FROM trades WHERE status='closed' AND ts_close>=?",
            (ts,),
        )
        return rows[0]["s"] or 0.0

    def orders_in_last(self, seconds: float) -> int:
        rows = self.query(
            "SELECT COUNT(*) c FROM orders WHERE ts>=?", (time.time() - seconds,)
        )
        return rows[0]["c"]

    def unreviewed_closed_trades(self) -> list[dict]:
        return self.query(
            "SELECT * FROM trades WHERE status='closed' AND reviewed=0 ORDER BY ts_close"
        )

    def mark_reviewed(self, trade_id: int) -> None:
        self._conn.execute("UPDATE trades SET reviewed=1 WHERE id=?", (trade_id,))
        self._conn.commit()

    # -- snapshots (written by sentinel) ---------------------------------

    def record_balance(self, equity, cash, positions_value, raw=None) -> None:
        self._insert("balance_snapshots", {
            "ts": time.time(), "equity": equity, "cash": cash,
            "positions_value": positions_value,
            "raw": json.dumps(raw, default=str) if raw is not None else None,
        })

    def latest_equity(self) -> Optional[float]:
        rows = self.query(
            "SELECT equity FROM balance_snapshots ORDER BY ts DESC LIMIT 1")
        return rows[0]["equity"] if rows else None

    # -- sessions (written by supervisor) --------------------------------

    def start_session(self, session_id: str, run_type: str, model: str,
                      wake_reason: str, transcript_path: str) -> None:
        self._insert("sessions", {
            "id": session_id, "ts_start": time.time(), "run_type": run_type,
            "model": model, "wake_reason": wake_reason,
            "transcript_path": transcript_path,
        })

    def end_session(self, session_id: str, exit_code: int, num_turns: int,
                    result_summary: str) -> None:
        self._conn.execute(
            """UPDATE sessions SET ts_end=?, exit_code=?, num_turns=?,
               result_summary=? WHERE id=?""",
            (time.time(), exit_code, num_turns,
             result_summary[:2000] if result_summary else None, session_id),
        )
        self._conn.commit()

    def last_session_ts(self) -> Optional[float]:
        # END of the last completed session (start for in-flight rows).
        # Debounces and sleep clamps measure from when the agent went BACK
        # TO SLEEP — measuring from ts_start lets sessions longer than the
        # minimum gap chain back-to-back with zero rest.
        rows = self.query(
            "SELECT MAX(COALESCE(ts_end, ts_start)) m FROM sessions")
        return rows[0]["m"]

    def has_successful_session(self) -> bool:
        rows = self.query(
            "SELECT 1 FROM sessions WHERE exit_code=0 LIMIT 1")
        return bool(rows)

    def last_finished_ts(self, run_type: str) -> float:
        """Latest COMPLETED session of a run type (ts_end set). A session
        killed mid-flight never reached finalization and must not satisfy
        a cadence debounce — otherwise one killed reflection session
        silently eats a whole cycle."""
        rows = self.query(
            "SELECT MAX(ts_end) m FROM sessions "
            "WHERE run_type=? AND ts_end IS NOT NULL", (run_type,))
        return float(rows[0]["m"] or 0) if rows else 0.0

    def count_finished_since(self, ts: float, exclude_run_types: tuple = ()) -> int:
        """Completed sessions since a timestamp, optionally excluding run
        types — the UI manager's cadence counts the trader's sessions."""
        excl = ""
        params: list = [ts]
        if exclude_run_types:
            excl = ("AND run_type NOT IN (" +
                    ",".join("?" for _ in exclude_run_types) + ")")
            params += list(exclude_run_types)
        rows = self.query(
            f"SELECT COUNT(*) c FROM sessions WHERE ts_end IS NOT NULL "
            f"AND ts_end > ? {excl}", tuple(params))
        return rows[0]["c"] if rows else 0

    def close_orphan_sessions(self) -> int:
        """Finalize sessions left open by a kill that outran
        end_session. A supervisor calls this at startup, when nothing
        it owns can be running. Returns how many rows were closed."""
        cur = self._conn.execute(
            "UPDATE sessions SET ts_end = ts_start, exit_code = -1 "
            "WHERE ts_end IS NULL")
        self._conn.commit()
        return cur.rowcount

    def has_open_session(self, since: float) -> bool:
        """A session started after `since` and not yet finalized. The
        time bound matters: a crash can orphan a NULL ts_end row, and a
        stale orphan must never read as 'still running' forever."""
        rows = self.query(
            "SELECT COUNT(*) c FROM sessions "
            "WHERE ts_end IS NULL AND ts_start > ?", (since,))
        return bool(rows and rows[0]["c"])

    # -- events -----------------------------------------------------------

    def notify_events_since(self, ts: float) -> list[dict]:
        """The agent's rung notify events after a timestamp — the
        interface manager's wake bell (detail carries the optional
        message), oldest first."""
        return self.query(
            "SELECT ts, detail FROM events "
            "WHERE kind='notify' AND ts > ? ORDER BY ts", (ts,))

    def record_event(self, source: str, kind: str, detail: Any = None) -> None:
        self._insert("events", {
            "ts": time.time(), "source": source, "kind": kind,
            "detail": json.dumps(detail, default=str) if not isinstance(detail, (str, type(None))) else detail,
        })
