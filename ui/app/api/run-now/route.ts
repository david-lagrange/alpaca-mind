import fs from "node:fs";
import path from "node:path";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/**
 * Request an immediate UI-manager run.
 *
 * Writes a small JSON marker file that the UI-manager scheduler watches
 * for; when the scheduler sees it, it starts a construction run ahead of
 * schedule and deletes the file. The path comes from UI_RUN_REQUEST_PATH,
 * defaulting to ./data/run_request.json. This endpoint takes no input —
 * it only signals "the owner wants the manager to look at the inbox now".
 */

const DEFAULT_RUN_REQUEST_PATH = "./data/run_request.json";

export async function POST(request: NextRequest) {
  const filePath = path.resolve(
    process.env.UI_RUN_REQUEST_PATH || DEFAULT_RUN_REQUEST_PATH
  );

  try {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(
      filePath,
      JSON.stringify({ requested_at: new Date().toISOString() }) + "\n",
      "utf8"
    );
  } catch {
    return NextResponse.json(
      { error: "Could not write the run request." },
      { status: 500 }
    );
  }

  const accepts = request.headers.get("accept") ?? "";
  const contentType = request.headers.get("content-type") ?? "";
  if (
    accepts.includes("application/json") ||
    contentType.includes("application/json")
  ) {
    return NextResponse.json({ ok: true });
  }
  return NextResponse.redirect(new URL("/inbox", request.url), 303);
}
