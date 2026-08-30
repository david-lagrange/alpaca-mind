import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { ledgerAvailable } from "@/lib/ledger";
import { logEvent } from "@/lib/log";

export const dynamic = "force-dynamic";

/**
 * Liveness and dependency check. `ui_db` reports whether the UI's own
 * database opened; `ledger` reports whether the trading engine's ledger
 * is present and readable. A false ledger is normal before the first
 * trading session.
 */
export async function GET() {
  let uiDbOk = false;
  try {
    getDb().prepare("SELECT 1").get();
    uiDbOk = true;
  } catch (err) {
    uiDbOk = false;
    logEvent("error", "health_ui_db_check_failed", {
      path: "/api/health",
      error: String(err),
    });
  }

  return NextResponse.json({
    ok: true,
    ui_db: uiDbOk,
    ledger: ledgerAvailable(),
  });
}
