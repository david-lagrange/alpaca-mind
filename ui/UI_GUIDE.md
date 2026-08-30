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
    api/              Route handlers (health, inbox, run-now, + yours)
  lib/
    db.ts             The UI's own SQLite (shared connection, migrations)
    ledger.ts         Read-only trading ledger access (typed helpers)
    alpaca.ts         Read-only brokerage REST helpers
  components/         Shared components you create (make this as needed)
  data/               Runtime state (SQLite, request files) — gitignored
  middleware.ts       Whole-app Basic Auth gate
  UI_GUIDE.md         This document
```

## Adding a page

1. Create `app/<route>/page.tsx`. Pages that read live data should be
   server components with `export const dynamic = "force-dynamic"` so
   nothing is cached at build time.
2. Add a nav link: append `{ href, label }` to the `NAV_LINKS` array in
   `app/layout.tsx`. That is the only place navigation lives.
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

**Live account — `lib/alpaca.ts`.** `getAccount()` and `getPositions()`,
both returning `null` on missing credentials or network failure. Same
rule: optional-render, never crash on `null`.

**API routes.** Follow `app/api/inbox/route.ts` as the template: validate
every input (type, length, range) before touching the database, return
JSON errors with proper status codes, and support form posts with a 303
redirect back to the page when the route backs an HTML form. Server
actions are also fine for page-local mutations; prefer an API route when
anything else (including you) might call it.

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

Tailwind, themed through the CSS variables in `app/globals.css` and mapped
to semantic names in `tailwind.config.ts`:

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
| `UI_DB_PATH` | The UI's own SQLite database | `./data/ui.sqlite` |
| `LEDGER_PATH` | The trading engine's ledger (read-only) | — |
| `UI_RUN_REQUEST_PATH` | Immediate-run marker file | `./data/run_request.json` |
| `ALPACA_API_KEY` | Brokerage API key, e.g. `<YOUR_ALPACA_KEY>` | — |
| `ALPACA_SECRET_KEY` | Brokerage API secret, e.g. `<YOUR_ALPACA_SECRET>` | — |
| `ALPACA_PAPER` | `"true"` targets the paper API, else live | `true` |

## Quality bar

Build interfaces a professional would ship: beautiful, dense with real
information, and honest — losses shown as plainly as wins, costs alongside
results, empty states that say why they are empty. Prefer one page that
tells the truth clearly over three that decorate it. Every number gets
units and context; every list gets an order the owner would choose; every
color means something.
