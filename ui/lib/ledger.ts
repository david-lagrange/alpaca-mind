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
 * Engine-owned schema this module reads:
 *   sessions(id TEXT, run_type TEXT, model TEXT, reason TEXT,
 *            ts_start REAL, ts_end REAL, exit_code INT, cost_usd REAL,
 *            num_turns INT, summary TEXT)
 *   trades(id INT, symbol TEXT, side TEXT, qty REAL, entry_price REAL,
 *          exit_price REAL, pnl REAL, status TEXT, thesis TEXT,
 *          ts_open REAL, ts_close REAL)
 *   orders(id INT, trade_id INT, symbol TEXT, side TEXT, qty REAL,
 *          order_type TEXT, status TEXT, filled_avg_price REAL, ts REAL,
 *          legs TEXT)
 *   events(ts REAL, source TEXT, kind TEXT, detail TEXT)
 *   balance_snapshots(ts REAL, equity REAL, cash REAL, buying_power REAL)
 *
 * Timestamps (ts*) are Unix epoch seconds.
 */

export interface LedgerSession {
  id: string;
  run_type: string;
  model: string;
  reason: string;
  ts_start: number;
  ts_end: number | null;
  exit_code: number | null;
  cost_usd: number | null;
  num_turns: number | null;
  summary: string | null;
}

export interface LedgerTrade {
  id: number;
  symbol: string;
  side: string;
  qty: number;
  entry_price: number | null;
  exit_price: number | null;
  pnl: number | null;
  status: string;
  thesis: string | null;
  ts_open: number;
  ts_close: number | null;
}

export interface LedgerOrder {
  id: number;
  trade_id: number | null;
  symbol: string;
  side: string;
  qty: number;
  order_type: string;
  status: string;
  filled_avg_price: number | null;
  ts: number;
  legs: string | null;
}

export interface LedgerEvent {
  ts: number;
  source: string;
  kind: string;
  detail: string | null;
}

export interface BalanceSnapshot {
  ts: number;
  equity: number;
  cash: number;
  buying_power: number;
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
