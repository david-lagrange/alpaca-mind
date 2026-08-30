# First Construction — build the base interface

The trader has completed its first session(s). Until now the app at
`/srv/ui/app` is a scaffold with a landing page and the inbox — your
job today is to turn it into the owner's first real window.

Before anything: read `/srv/ui/app/UI_GUIDE.md` and
`/srv/ui/app/STYLE.md` end to end, then your memory
(`memory/MEMORY.md` → `memory/owner-defaults.md` — your owner's
standing requests ARE the commission for this build), then the
trader's mission (`/srv/mind/workspace/.claude/CLAUDE.md` — read-only)
so you know WHO you are portraying, then its transcripts so far
(`/srv/mind/logs/sessions/`) and its ledger schema (UI_GUIDE has it).

Build the base experience: the standing sections from
owner-defaults.md, designed by you (they say WHAT the owner always
wants served, never how a page must look — form, grouping, and
sequence are yours, and early sections can start modest and deepen
over evolution passes). As you build, the questions a great first
window answers:

- What is this thing, and what is it doing right now? (identity, LIVE
  account state and open positions with theses — living components per
  UI_GUIDE's pattern, polling between your runs — plus next wake)
- What has it done? (sessions timeline; trades with entry/exit/thesis/
  reason; honest P&L)
- What is it thinking and learning? The trader's `journal/` is its OWN
  narrative of every wake — a primary source, rendered beautifully.
  The transcripts carry the full reasoning and receipts behind each
  entry; surface lessons simply, depth one click behind (the
  deep-dive pattern).
- What is it watching, and when does it live? (armed triggers,
  scanners, its own schedule — rendered like the self-owned thing it
  is)
- How is it performing? (equity curve from balance_snapshots; realized
  results — losses as plainly as wins)

Then the close-out, per your quality law (CLAUDE.md — build passes,
every route verified, mobile-first, honest data states, everything
you build logs through `lib/log.ts`, fresh-eyes pass): build, verify,
`data/restart_request.json`, update `kv.next_run_at`, seed your
watermark (`kv.integrated_through` — the newest journal entry and
transcript you built from), and commit your workspace with a plain
summary of what you built and why.
