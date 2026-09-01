# UI Guide

Conventions for the UI manager — the agent that constructs and evolves this
interface. Read this before every construction run. The scaffold gives you a
working, authenticated Next.js app with data access already wired; your job
is to build the interface itself.

## What this app is

The owner's window into an autonomous trading agent. The trader runs on this
same host and writes its history to a ledger database; the owner's brokerage
account is reachable read-only over REST. You build pages that show what the
trader is doing and learning — positions, sessions, theses, outcomes, costs,
equity over time — and you keep evolving them as the story develops.

## Boundaries

- This app **reads** the ledger and the brokerage account. It never places,
  alters, or cancels orders. Trading belongs to the trading agent alone.
  Do not add write access to either; `lib/ledger.ts` and `lib/alpaca.ts`
  are read-only by design.
- Never touch files outside `ui/`. The trading engine, its ledger, and its
  configuration are owned by other components.
- Never put credentials in client code, commit them to files, or render
  them in the UI. All secrets come from `process.env` on the server.
- The whole app sits behind HTTP Basic Auth (`middleware.ts`). Do not add
  unauthenticated routes or weaken the gate.

## File layout

```
ui/
  app/
    layout.tsx        Shell: header, nav, content column
    page.tsx          Landing page (replace this with the real home)
    globals.css       Theme variables + Tailwind layers
    inbox/page.tsx    Owner → UI-manager inbox
    logs/             Structured-log viewer (mind + ui daily JSONL streams)
    api/              Route handlers (health, inbox, run-now, logs, + yours)
  lib/
    db.ts             The UI's own SQLite (shared connection, migrations)
    ledger.ts         Read-only trading ledger access (typed helpers)
    alpaca.ts         Read-only brokerage REST helpers
    log.ts            The web app's own JSONL event logger (server-side)
    logs.ts           Read-side helpers for the daily JSONL log streams
  components/         Shared components you create (make this as needed)
  data/               Runtime state (SQLite, request files) — gitignored
  middleware.ts       Whole-app Basic Auth gate
  STYLE.md            The design language — read before styling anything
  UI_GUIDE.md         This document
```

## Dependencies

`package.json` is yours. Install any npm package that serves the
interface — a charting library, a date library, whatever a view
deserves; `npm install` works on this host and the build verifies the
result. Prefer established, well-maintained packages and know the
reason for each one you add (this host holds live credentials; a
dependency is trust). Server-side rendering and the standalone build
must keep working — that's what your build gate checks.

## Right-sized mechanisms

Choose the simplest mechanism that serves each view — all of these are
first-class, and none is a lesser craft:

- Hard-coded JSX you append to on each run (a learnings page grown by
  hand is not worse for being still — it is often better).
- A JSON file a chart reads, appended over time.
- A table in your own SQLite when a view needs real queries.
- A live-polling component when nowness is the information.

Not everything deserves a database, and not everything deserves a
poller. A page that changes only when you run is a fine page if what
it shows only changes when you run.

## Adding a page

1. Create `app/<route>/page.tsx`. Pages that read live data should be
   server components with `export const dynamic = "force-dynamic"` so
   nothing is cached at build time.
2. Add a nav link: append `{ href, label }` to the `NAV_LINKS` array in
   `app/layout.tsx`. That is the only place navigation lives. On small
   screens the shell renders those links through
   `components/MobileNav.tsx` — a working drawer shipped as a gift:
   restyle it or replace the whole chrome to match the owner's taste,
   but preserve its behaviors in whatever you build (background scroll
   locked while a menu is open; the menu closes on navigation, backdrop
   tap, and Escape). Those aren't style — they're what makes a drawer
   trustworthy on a phone.
3. Put reusable pieces in `components/` and import them with the `@/`
   alias (`@/components/...`, `@/lib/...`).

## Data access patterns

**UI state — `lib/db.ts`.** `getDb()` is the shared connection to the UI's
own SQLite database; every server-side read/write of UI state goes through
it. Helpers exist for the inbox and the `kv` table (`kvGet`, `kvSet`,
`listInbox`, `unreadInboxCount`, `addInboxMessage`).

**Trading history — `lib/ledger.ts`.** Typed read-only helpers:
`recentSessions(limit)`, `openTrades()`, `recentEvents(limit)`,
`equityCurve(days)`, plus `getLedger()` for custom read-only queries
against the engine's schema (documented in that file). Every helper
degrades to empty/null when the ledger does not exist yet — always render
a sensible empty state.

**Live account & market data — `lib/alpaca.ts`.** `getAccount()` and
`getPositions()` ship as the starting pattern, both returning `null` on
missing credentials or network failure. Same rule: optional-render,
never crash on `null`.

**This library is yours to EXTEND — and live views are expected.** The
server env carries the Alpaca keys (read use); the two API hosts are:

- `https://paper-api.alpaca.markets` (or `https://api.alpaca.markets`
  when `ALPACA_PAPER` is `"false"`) — account, positions, open orders,
  the market clock: the ACCOUNT surface. Read-only endpoints only.
- `https://data.alpaca.markets` — the MARKET surface: latest stock
  quotes/trades (`/v2/stocks/quotes/latest?symbols=…`), snapshots
  (`/v2/stocks/snapshots`), bars, movers
  (`/v1beta1/screener/stocks/movers`), news (`/v1beta1/news`), and
  options chains with greeks
  (`/v1beta1/options/snapshots/{underlying}?feed=indicative`).

Auth = two headers on every request: `APCA-API-KEY-ID` and
`APCA-API-SECRET-KEY` (see the existing helpers). Add typed helpers
here per endpoint you need; keep every one a GET.

**The living-component pattern.** You run occasionally; what you build
runs continuously — so a dashboard should be ALIVE between your runs,
not a snapshot of your last visit. The convention:

1. A server API route per live view (e.g. `app/api/live/positions/
   route.ts`) that calls your `lib/alpaca.ts` helper per request and
   returns compact JSON. Mark it `export const dynamic =
   "force-dynamic"` so nothing caches.
2. A small client component (`"use client"`) that fetches that route on
   an interval and renders with honest loading/stale/error states. Keep
   intervals modest — **5–15s for quotes and positions during market
   hours, 30–60s otherwise** (check `/v2/clock` once and let the
   component slow itself down when the market is closed). Pause polling
   when `document.hidden`.
3. Show data age ("as of 12s ago") whenever a value can be stale —
   a live number with no timestamp is a quiet lie.

Never call Alpaca from the browser directly (that would need the keys
client-side); the server route is the boundary. Liveness is for views
where nowness IS the information — account state, open positions and
their P&L, an open-trade tracker, the market clock. Use it there
without hesitation, and nowhere out of habit: a still page rendered
from what you curated at your last run is often the more premium
experience (see Right-sized mechanisms).

**API routes.** Follow `app/api/inbox/route.ts` as the template: validate
every input (type, length, range) before touching the database, return
JSON errors with proper status codes, and support form posts with a 303
redirect back to the page when the route backs an HTML form. Server
actions are also fine for page-local mutations; prefer an API route when
anything else (including you) might call it.

**Web logging.** API routes log through `lib/log.ts` (component `web`)
into the same daily JSONL stream the Logs page renders
(`$UI_LOGS_DIR/daily/`): one `api_request` info event per mutating
request, plus error events with context in catch paths. `logEvent`
never throws and no-ops when `UI_LOGS_DIR` is unset — logging must
never change a route's behavior.

## Creating new tables

Add your tables to the `MIGRATIONS` array in `lib/db.ts` as idempotent
`CREATE TABLE IF NOT EXISTS ...` statements. Every statement runs on every
open, so a fresh deployment and a long-lived one converge on the same
schema. Append only — never rewrite or reorder existing entries. To evolve
a table you already created, append a new statement (e.g. a
`CREATE TABLE IF NOT EXISTS` for a successor table, or an idempotent
`ALTER TABLE` guarded by a try/catch in code). Only the UI's own database:
the ledger schema belongs to the trading engine and is read-only here.

## Styling

**`STYLE.md` is the design language — read it before styling anything.**
Mechanically: Tailwind, themed through the CSS variables in
`app/globals.css` and mapped to semantic names in `tailwind.config.ts`:

- `bg` / `surface` / `raised` — page ground, cards, inputs
- `edge` — borders and dividers
- `ink` / `muted` / `faint` — text hierarchy
- `accent` — interactive elements and emphasis
- `gain` / `loss` — positive and negative financial values, consistently
- `warn` — caution states

Use these names (`bg-surface`, `text-muted`, `border-edge`, ...) rather
than raw hex values. Extend the palette by adding variables in
`globals.css` and mapping them in `tailwind.config.ts`. Fonts are system
stacks (`font-sans`, `font-mono`); the app is self-contained — no external
fonts, CDNs, or third-party scripts. `font-mono` is the convention for
numbers, timestamps, and symbols.

## The inbox contract

The inbox (`inbox` table) is the owner steering **visibility, not
trading**. On every run:

1. Read unread messages: `SELECT * FROM inbox WHERE read = 0`.
2. Build or adjust the interface to address them.
3. Mark each one: set `read = 1`; when you have actually addressed it, set
   `addressed = 1` and write a short, concrete `addressed_note` describing
   what you built or changed (the owner reads these notes on the inbox
   page). If a request is out of bounds (e.g. asks for trading changes),
   still mark it read and explain why in the note.
4. Update your schedule: `kvSet("next_run_at", <ISO 8601 timestamp>)` so
   the inbox page can show the owner when you will run next.

The owner can also request an immediate run: the app writes a marker file
(`UI_RUN_REQUEST_PATH`, default `./data/run_request.json`) containing
`{"requested_at": "<ISO 8601>"}`. Your scheduler consumes and deletes it.

## Build and restart contract

After editing code:

1. Run `npm run build` from `ui/`. A failed build must be fixed before the
   run ends — never leave the app unbuildable.
2. Trigger a restart by writing `./data/restart_request.json` (any JSON,
   e.g. `{"requested_at": "<ISO 8601>"}`). The deployment's service
   manager picks up the new build on restart.

`npm run typecheck` (`tsc --noEmit`) is a fast pre-build sanity check.

## Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `UI_PASSWORD` | Basic Auth password (user `owner`); app serves 503 without it | — |
| `UI_PUBLIC` | `"true"` = showcase mode: read-only site open to anyone; inbox + all mutating requests still require auth | `false` |
| `UI_DB_PATH` | The UI's own SQLite database | `./data/ui.sqlite` |
| `LEDGER_PATH` | The trading engine's ledger (read-only) | — |
| `UI_RUN_REQUEST_PATH` | Immediate-run marker file | `./data/run_request.json` |
| `MIND_LOGS_DIR` | Trading engine's structured daily logs (read-only here) | — |
| `UI_LOGS_DIR` | This app's structured daily logs (read and write) | — |
| `ALPACA_API_KEY` | Brokerage API key, e.g. `<YOUR_ALPACA_KEY>` | — |
| `ALPACA_SECRET_KEY` | Brokerage API secret, e.g. `<YOUR_ALPACA_SECRET>` | — |
| `ALPACA_PAPER` | `"true"` targets the paper API, else live | `true` |

**Where these live on a deployment.** The source of truth is
`/srv/ui/.env` (owner-only, mode 600). systemd loads it into BOTH the
web server (`ui-web.service`) and your own agent sessions
(`ui-supervisor.service`) — so `process.env` in server code and
`$VARIABLE` in your shell both already have everything above. Deployed
values point `LEDGER_PATH` at the trader's ledger and the data paths at
`./data/` inside this app. To hand-test the built server on a spare
port before requesting a restart:

```bash
set -a; . /srv/ui/.env; set +a
PORT=3100 node .next/standalone/server.js   # then curl your routes
```

Never print these values into logs, transcripts, commits, or the UI.
Paths that are NOT env vars (plain read-only filesystem access): the
trader's entire workspace at `/srv/mind/workspace/` — journals,
memory, doctrine, strategies, state — and its session transcripts at
`/srv/mind/logs/sessions/`. Read the real files and quote them
verbatim; transcripts are for what the files don't say (what the
trader did, not just what it wrote down). Journals may arrive as
several files for one day (`YYYY-MM-DD.md` plus suffixed siblings like
`YYYY-MM-DD-<topic>.md`) — anything keyed by bare date silently drops
entries.

## Quality bar

Build interfaces a professional would ship: beautiful, dense with real
information, and honest — losses shown as plainly as wins, costs alongside
results, empty states that say why they are empty. Prefer one page that
tells the truth clearly over three that decorate it. Every number gets
units and context; every list gets an order the owner would choose; every
color means something.
