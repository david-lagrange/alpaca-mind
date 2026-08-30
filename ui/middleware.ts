import { NextRequest, NextResponse } from "next/server";

/**
 * Whole-app HTTP Basic Auth gate.
 *
 * This UI runs on a host that may be exposed to the public internet, so
 * every route — pages, API routes, and assets alike — sits behind a single
 * credential by design. There are no anonymous surfaces: anything the app
 * can show (account state, trade history, agent activity) is for the owner
 * only.
 *
 * Username is fixed ("owner"); the password comes from the UI_PASSWORD
 * environment variable. If that variable is unset the app refuses to serve
 * at all (503) rather than falling open — an unconfigured deployment must
 * never be an unprotected one.
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

function unauthorized(): NextResponse {
  return new NextResponse("Authentication required.", {
    status: 401,
    headers: {
      "WWW-Authenticate": `Basic realm="${REALM}", charset="UTF-8"`,
    },
  });
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

  const header = request.headers.get("authorization") ?? "";
  if (!header.startsWith("Basic ")) {
    return unauthorized();
  }

  let user = "";
  let pass = "";
  try {
    const decoded = atob(header.slice(6).trim());
    const sep = decoded.indexOf(":");
    if (sep === -1) return unauthorized();
    user = decoded.slice(0, sep);
    pass = decoded.slice(sep + 1);
  } catch {
    return unauthorized();
  }

  // Evaluate both comparisons unconditionally to keep timing uniform.
  const userOk = safeEqual(user, USERNAME);
  const passOk = safeEqual(pass, password);
  if (!(userOk && passOk)) {
    return unauthorized();
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
