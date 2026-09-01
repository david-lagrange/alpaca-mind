import Database from "better-sqlite3";
import fs from "node:fs";

/**
 * Read-only access to the trading agent's ledger.
 *
 * The ledger SQLite file is owned and written exclusively by the trading
 * engine; this module never writes to it, and its schema is the engine's
 * to define. The UI reads it to show the owner what the trader has done.
 *
 * The path comes from LEDGER_PATH. The file may legitimately not exist
 * yet (a fresh deployment before the first trading session), so every
 * helper degrades gracefully: null / empty results rather than errors.
 *
 * Engine-owned schema this module reads (mirrors engine/ledger.py —
 * that file's CREATE TABLE block is the authority; when in doubt,
 * verify against the live database with `.schema`):
 *   sessions(id TEXT PK, ts_start REAL, ts_end REAL, run_type TEXT,
 *            model TEXT, wake_reason TEXT, exit_code INT,
 *            cost_usd REAL, input_tokens INT, output_tokens INT,
 *            num_turns INT, transcript_path TEXT, result_summary TEXT)
 *   trades(id INT PK, ts_open REAL, ts_close REAL, venue TEXT,
 *          symbol TEXT, side TEXT, qty REAL, entry_price REAL,
 *          exit_price REAL, fees REAL, pnl REAL, pnl_pct REAL,
 *          thesis TEXT, exit_reason TEXT, status TEXT,
 *          structure_id TEXT, session_id_open TEXT,
 *          session_id_close TEXT, reviewed INT, meta TEXT)
 *   orders(id INT PK, ts REAL, venue TEXT, venue_order_id TEXT,
 *          symbol TEXT, side TEXT, order_type TEXT, qty REAL,
 *          notional REAL, limit_price REAL, stop_price REAL,
 *          status TEXT, filled_qty REAL, filled_avg_price REAL,
 *          fees REAL, session_id TEXT, trade_id INT,
 *          structure_id TEXT, legs TEXT, raw TEXT, thesis TEXT)
 *   events(ts REAL, source TEXT, kind TEXT, detail TEXT) — no id
 *          column; order by ts (or rowid)
 *   balance_snapshots(ts REAL, equity REAL, cash REAL,
 *          positions_value REAL, raw TEXT) — no id column
 *
 * Timestamps (ts*) are Unix epoch seconds. `detail`, `legs`, `raw`,
 * and `meta` are JSON strings.
 */

export interface LedgerSession {
  id: string;
  ts_start: number;
  ts_end: number | null;
  run_type: string;
  model: string | null;
  wake_reason: string | null;
  exit_code: number | null;
  cost_usd: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  num_turns: number | null;
  transcript_path: string | null;
  result_summary: string | null;
}

export interface LedgerTrade {
  id: number;
  ts_open: number;
  ts_close: number | null;
  venue: string;
  symbol: string;
  side: string;
  qty: number | null;
  entry_price: number | null;
  exit_price: number | null;
  fees: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  thesis: string | null;
  exit_reason: string | null;
  status: string;
  structure_id: string | null;
  session_id_open: string | null;
  session_id_close: string | null;
  reviewed: number;
  meta: string | null;
}

export interface LedgerOrder {
  id: number;
  ts: number;
  venue: string;
  venue_order_id: string | null;
  symbol: string;
  side: string;
  order_type: string;
  qty: number | null;
  notional: number | null;
  limit_price: number | null;
  stop_price: number | null;
  status: string;
  filled_qty: number | null;
  filled_avg_price: number | null;
  fees: number | null;
  session_id: string | null;
  trade_id: number | null;
  structure_id: string | null;
  legs: string | null;
  raw: string | null;
  thesis: string | null;
}

export interface LedgerEvent {
  ts: number;
  source: string;
  kind: string;
  detail: string | null;
}

export interface BalanceSnapshot {
  ts: number;
  equity: number | null;
  cash: number | null;
  positions_value: number | null;
  raw: string | null;
}

const globalForLedger = globalThis as unknown as {
  __ledgerDb?: Database.Database;
};

/**
 * Open the ledger read-only, or return null when it is not available.
 * The connection is cached once it opens successfully; a missing file is
 * re-checked on every call so the ledger is picked up as soon as the
 * trading engine creates it.
 */
export function getLedger(): Database.Database | null {
  if (globalForLedger.__ledgerDb) {
    return globalForLedger.__ledgerDb;
  }

  const ledgerPath = process.env.LEDGER_PATH;
  if (!ledgerPath || !fs.existsSync(ledgerPath)) {
    return null;
  }

  try {
    const db = new Database(ledgerPath, {
      readonly: true,
      fileMustExist: false,
    });
    globalForLedger.__ledgerDb = db;
    return db;
  } catch {
    return null;
  }
}

/** True when the ledger file exists and can be opened. */
export function ledgerAvailable(): boolean {
  return getLedger() !== null;
}

/** Wrap a query so a missing ledger or missing table yields the fallback. */
function query<T>(fallback: T, run: (db: Database.Database) => T): T {
  const db = getLedger();
  if (!db) return fallback;
  try {
    return run(db);
  } catch {
    return fallback;
  }
}

/** Most recent trading sessions, newest first. */
export function recentSessions(limit: number): LedgerSession[] {
  return query<LedgerSession[]>([], (db) =>
    db
      .prepare("SELECT * FROM sessions ORDER BY ts_start DESC LIMIT ?")
      .all(Math.max(0, Math.floor(limit))) as LedgerSession[]
  );
}

/** Trades that are currently open, most recent first. */
export function openTrades(): LedgerTrade[] {
  return query<LedgerTrade[]>([], (db) =>
    db
      .prepare(
        "SELECT * FROM trades WHERE status = 'open' ORDER BY ts_open DESC"
      )
      .all() as LedgerTrade[]
  );
}

/** Most recent engine events, newest first. */
export function recentEvents(limit: number): LedgerEvent[] {
  return query<LedgerEvent[]>([], (db) =>
    db
      .prepare("SELECT * FROM events ORDER BY ts DESC LIMIT ?")
      .all(Math.max(0, Math.floor(limit))) as LedgerEvent[]
  );
}

/** Balance snapshots over the trailing N days, oldest first. */
export function equityCurve(days: number): BalanceSnapshot[] {
  const since = Date.now() / 1000 - Math.max(0, days) * 86400;
  return query<BalanceSnapshot[]>([], (db) =>
    db
      .prepare(
        "SELECT * FROM balance_snapshots WHERE ts >= ? ORDER BY ts ASC"
      )
      .all(since) as BalanceSnapshot[]
  );
}
