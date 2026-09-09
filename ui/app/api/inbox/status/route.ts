import fs from "node:fs";
import path from "node:path";
import Database from "better-sqlite3";
import { NextResponse } from "next/server";
import { kvGet } from "@/lib/db";
import { logEvent } from "@/lib/log";

export const dynamic = "force-dynamic";

/**
 * Where the UI manager stands right now — for the inbox page's status
 * element. Three facts, each read from its own source of truth:
 *
 *   requested_at  the immediate-run marker file, if one is waiting
 *   session       the manager's newest session row from ITS OWN ledger
 *                 (UI_LEDGER_PATH): a row with no end time is a pass in
 *                 progress, and its own start time is the clock
 *   next_run_at   the manager's promise, from its kv store
 *
 * The running state and its clock come from one session row, never from
 * pairing separate start and finish events: an event pairing can drift
 * to the wrong pass and count from the wrong start.
 *
 * Lives under /api/inbox so it shares the inbox's access rule.
 */

const DEFAULT_RUN_REQUEST_PATH = "./data/run_request.json";

export interface ManagerSession {
  id: string;
  run_type: string | null;
  ts_start: number;
  ts_end: number | null;
  exit_code: number | null;
  num_turns: number | null;
}

const globalForUiLedger = globalThis as unknown as {
  __uiLedgerDb?: Database.Database;
};

function managerLedger(): Database.Database | null {
  if (globalForUiLedger.__uiLedgerDb) return globalForUiLedger.__uiLedgerDb;
  const ledgerPath = process.env.UI_LEDGER_PATH;
  if (!ledgerPath || !fs.existsSync(ledgerPath)) return null;
  try {
    const db = new Database(ledgerPath, { readonly: true, fileMustExist: true });
    globalForUiLedger.__uiLedgerDb = db;
    return db;
  } catch {
    return null;
  }
}

function newestSession(): { available: boolean; session: ManagerSession | null } {
  const db = managerLedger();
  if (!db) return { available: false, session: null };
  try {
    const row = db
      .prepare(
        "SELECT id, run_type, ts_start, ts_end, exit_code, num_turns FROM sessions ORDER BY ts_start DESC LIMIT 1"
      )
      .get() as ManagerSession | undefined;
    return { available: true, session: row ?? null };
  } catch {
    return { available: true, session: null };
  }
}

function requestedAt(): string | null {
  const filePath = path.resolve(
    process.env.UI_RUN_REQUEST_PATH || DEFAULT_RUN_REQUEST_PATH
  );
  try {
    if (!fs.existsSync(filePath)) return null;
    const parsed = JSON.parse(fs.readFileSync(filePath, "utf8")) as {
      requested_at?: unknown;
    };
    return typeof parsed?.requested_at === "string"
      ? parsed.requested_at
      : new Date(fs.statSync(filePath).mtimeMs).toISOString();
  } catch {
    return null;
  }
}

export async function GET() {
  const start = Date.now();
  const { available, session } = newestSession();
  const body = {
    now: Date.now() / 1000,
    requested_at: requestedAt(),
    next_run_at: kvGet("next_run_at"),
    available,
    session,
  };
  logEvent("info", "api_request", {
    path: "/api/inbox/status",
    method: "GET",
    status: 200,
    dur_ms: Date.now() - start,
  });
  return NextResponse.json(body, { headers: { "Cache-Control": "no-store" } });
}
