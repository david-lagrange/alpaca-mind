import { NextRequest, NextResponse } from "next/server";

/**
 * HTTP Basic Auth gate.
 *
 * Default: every route — pages, API routes, and assets alike — sits behind
 * a single credential. There are no anonymous surfaces: anything the app
 * can show (account state, trade history, agent activity) is for the owner
 * only.
 *
 * Showcase mode (UI_PUBLIC=true): the read-only site is open to anyone —
 * for deployments the owner wants to show the world — while everything
 * that STEERS stays gated: the inbox (page and API, reads included; the
 * owner's requests are theirs) and every mutating request, whichever
 * route carries it. Method-based gating covers routes that don't exist
 * yet — the interface grows itself, and a future POST must not be born
 * open.
 *
 * Username is fixed ("owner"); the password comes from the UI_PASSWORD
 * environment variable. If that variable is unset the app refuses to serve
 * at all (503) rather than falling open — an unconfigured deployment must
 * never be an unprotected one, in either mode.
 */

const REALM = "alpaca-mind";
const USERNAME = "owner";

/** Constant-time string comparison to avoid leaking match length/prefix. */
function safeEqual(a: string, b: string): boolean {
  const len = Math.max(a.length, b.length);
  let diff = a.length === b.length ? 0 : 1;
  for (let i = 0; i < len; i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}

function unauthorized(challenge = true): NextResponse {
  // The WWW-Authenticate header is what makes a browser throw its
  // sign-in dialog. On a public showcase page, a background fetch to a
  // gated API must fail QUIETLY (plain 401, component shows its
  // owner-only state) — otherwise one widget interrogates every
  // visitor with a popup over a page that is meant to be open.
  return new NextResponse("Authentication required.", {
    status: 401,
    headers: challenge
      ? { "WWW-Authenticate": `Basic realm="${REALM}", charset="UTF-8"` }
      : {},
  });
}

/** A top-level page navigation, as opposed to a fetch/asset request. */
function isDocumentRequest(request: NextRequest): boolean {
  const dest = request.headers.get("sec-fetch-dest");
  if (dest) return dest === "document";
  return (request.headers.get("accept") ?? "").includes("text/html");
}

function notConfigured(): NextResponse {
  const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>alpaca-mind — not configured</title>
    <style>
      body {
        margin: 0;
        display: grid;
        place-items: center;
        min-height: 100vh;
        background: #0c0d10;
        color: #e4e6eb;
        font-family: ui-sans-serif, system-ui, sans-serif;
      }
      main { text-align: center; padding: 2rem; max-width: 34rem; }
      h1 { font-size: 1.25rem; font-weight: 600; margin: 0 0 0.75rem; }
      p { color: #949ba8; line-height: 1.6; margin: 0; }
      code {
        font-family: ui-monospace, monospace;
        background: #1c1f26;
        border: 1px solid #2a2e37;
        border-radius: 4px;
        padding: 0.1rem 0.35rem;
      }
    </style>
  </head>
  <body>
    <main>
      <h1>UI password not configured</h1>
      <p>
        This interface refuses to serve without authentication. Set the
        <code>UI_PASSWORD</code> environment variable and restart the
        service to unlock it.
      </p>
    </main>
  </body>
</html>`;
  return new NextResponse(html, {
    status: 503,
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

export function middleware(request: NextRequest): NextResponse {
  const password = process.env.UI_PASSWORD;
  if (!password) {
    return notConfigured();
  }

  const publicMode = process.env.UI_PUBLIC === "true";
  if (publicMode) {
    const method = request.method.toUpperCase();
    const safeMethod =
      method === "GET" || method === "HEAD" || method === "OPTIONS";
    const path = request.nextUrl.pathname;
    const inboxSurface =
      path === "/inbox" ||
      path.startsWith("/inbox/") ||
      path.startsWith("/api/inbox");
    if (safeMethod && !inboxSurface) {
      return NextResponse.next();
    }
  }

  // In public mode, only a deliberate page navigation earns the
  // browser's sign-in dialog; everything else fails quietly.
  const challenge = !publicMode || isDocumentRequest(request);

  const header = request.headers.get("authorization") ?? "";
  if (!header.startsWith("Basic ")) {
    return unauthorized(challenge);
  }

  let user = "";
  let pass = "";
  try {
    const decoded = atob(header.slice(6).trim());
    const sep = decoded.indexOf(":");
    if (sep === -1) return unauthorized(challenge);
    user = decoded.slice(0, sep);
    pass = decoded.slice(sep + 1);
  } catch {
    return unauthorized(challenge);
  }

  // Evaluate both comparisons unconditionally to keep timing uniform.
  const userOk = safeEqual(user, USERNAME);
  const passOk = safeEqual(pass, password);
  if (!(userOk && passOk)) {
    return unauthorized(challenge);
  }

  return NextResponse.next();
}

/**
 * Match everything. The gate intentionally covers static assets and API
 * routes as well as pages — nothing this app serves is public.
 */
export const config = {
  matcher: ["/(.*)"],
};
