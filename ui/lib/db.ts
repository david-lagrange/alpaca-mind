import Database from "better-sqlite3";
import fs from "node:fs";
import path from "node:path";

/**
 * The UI's own SQLite database — the shared connection for everything the
 * interface persists on its own behalf.
 *
 * This database belongs to the UI layer alone. It is entirely separate from
 * the trading agent's ledger (see lib/ledger.ts, which is read-only). Path
 * comes from UI_DB_PATH, defaulting to ./data/ui.sqlite relative to the
 * process working directory.
 *
 * Baseline schema (created on first open):
 *   - inbox: messages from the owner to the UI manager. The owner writes
 *     them through the Inbox page; the UI manager reads them, builds what
 *     they ask for, and marks them read/addressed with a note.
 *   - kv: small key/value store for UI-manager state (e.g. next_run_at,
 *     an ISO timestamp of the manager's next scheduled run).
 *
 * The UI manager adds its own tables as the interface grows. Convention:
 * add idempotent CREATE TABLE IF NOT EXISTS statements to MIGRATIONS below
 * so a fresh deployment and an existing one converge on the same schema.
 * Never rewrite or reorder existing entries; append only.
 */

const DEFAULT_DB_PATH = "./data/ui.sqlite";

const MIGRATIONS: string[] = [
  `CREATE TABLE IF NOT EXISTS inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    body TEXT NOT NULL,
    read INTEGER NOT NULL DEFAULT 0,
    addressed INTEGER NOT NULL DEFAULT 0,
    addressed_note TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT
  )`,
];

export interface InboxMessage {
  id: number;
  created_at: string;
  body: string;
  read: number;
  addressed: number;
  addressed_note: string | null;
}

/** Cache the connection on globalThis so dev-server reloads reuse it. */
const globalForDb = globalThis as unknown as {
  __uiDb?: Database.Database;
};

function openDb(): Database.Database {
  const dbPath = process.env.UI_DB_PATH || DEFAULT_DB_PATH;
  fs.mkdirSync(path.dirname(path.resolve(dbPath)), { recursive: true });

  const db = new Database(dbPath);
  db.pragma("journal_mode = WAL");
  for (const statement of MIGRATIONS) {
    db.exec(statement);
  }
  return db;
}

/**
 * The shared UI database connection. All server-side code that reads or
 * writes UI state should go through this helper rather than opening its
 * own connection.
 */
export function getDb(): Database.Database {
  if (!globalForDb.__uiDb) {
    globalForDb.__uiDb = openDb();
  }
  return globalForDb.__uiDb;
}

/** Read a value from the kv table; null when the key is absent. */
export function kvGet(key: string): string | null {
  const row = getDb()
    .prepare("SELECT value FROM kv WHERE key = ?")
    .get(key) as { value: string | null } | undefined;
  return row?.value ?? null;
}

/** Upsert a value into the kv table. */
export function kvSet(key: string, value: string): void {
  getDb()
    .prepare(
      "INSERT INTO kv (key, value) VALUES (?, ?) " +
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    )
    .run(key, value);
}

/** All inbox messages, newest first. */
export function listInbox(): InboxMessage[] {
  return getDb()
    .prepare("SELECT * FROM inbox ORDER BY id DESC")
    .all() as InboxMessage[];
}

/** Count of messages the UI manager has not yet read. */
export function unreadInboxCount(): number {
  const row = getDb()
    .prepare("SELECT COUNT(*) AS n FROM inbox WHERE read = 0")
    .get() as { n: number };
  return row.n;
}

/** Store a new owner message; returns its id. */
export function addInboxMessage(body: string): number {
  const result = getDb()
    .prepare("INSERT INTO inbox (created_at, body) VALUES (?, ?)")
    .run(new Date().toISOString(), body);
  return Number(result.lastInsertRowid);
}
