import { NextRequest, NextResponse } from "next/server";
import { addInboxMessage, listInbox } from "@/lib/db";
import { logEvent } from "@/lib/log";

export const dynamic = "force-dynamic";

/**
 * Owner → UI-manager inbox API.
 *
 * POST stores a message for the UI manager to read on its next run.
 * Accepts either an HTML form submission (redirects back to the inbox
 * page) or a JSON body {"body": "..."} (returns JSON). GET lists all
 * messages, newest first.
 */

const MAX_BODY_LENGTH = 4000;

export async function GET() {
  return NextResponse.json({ messages: listInbox() });
}

export async function POST(request: NextRequest) {
  const start = Date.now();
  try {
    const response = await handlePost(request);
    logEvent("info", "api_request", {
      path: "/api/inbox",
      method: "POST",
      status: response.status,
      dur_ms: Date.now() - start,
    });
    return response;
  } catch (err) {
    logEvent("error", "api_error", {
      path: "/api/inbox",
      method: "POST",
      error: String(err),
    });
    throw err;
  }
}

async function handlePost(request: NextRequest) {
  const contentType = request.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");

  let body: unknown;
  try {
    if (isJson) {
      const parsed = (await request.json()) as { body?: unknown };
      body = parsed?.body;
    } else {
      const form = await request.formData();
      body = form.get("body");
    }
  } catch {
    return NextResponse.json(
      { error: "Malformed request body." },
      { status: 400 }
    );
  }

  if (typeof body !== "string") {
    return NextResponse.json(
      { error: "Field 'body' must be a string." },
      { status: 400 }
    );
  }

  const trimmed = body.trim();
  if (trimmed.length === 0 || trimmed.length > MAX_BODY_LENGTH) {
    return NextResponse.json(
      {
        error: `Field 'body' must be 1 to ${MAX_BODY_LENGTH} characters.`,
      },
      { status: 400 }
    );
  }

  const id = addInboxMessage(trimmed);

  if (isJson) {
    return NextResponse.json({ ok: true, id }, { status: 201 });
  }
  return NextResponse.redirect(new URL("/inbox", request.url), 303);
}
