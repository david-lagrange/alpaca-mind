# First Construction — build the base interface

The trader has completed its first session(s). Until now the app at
`/srv/ui/app` is a scaffold with a landing page and the inbox — your
job today is to turn it into the owner's first real window.

Before anything: read `/srv/ui/app/UI_GUIDE.md` end to end, then the
trader's mission (`/srv/mind/workspace/.claude/CLAUDE.md` — read-only)
so you know WHO you are portraying, then its transcripts so far
(`/srv/mind/logs/sessions/`) and its ledger schema (UI_GUIDE has it).

Build the base experience — what a great first window shows (yours to
design; these are the questions it must answer, not a page list):

- What is this thing, and what is it doing right now? (identity, LIVE
  account state and open positions with theses — built as living
  components per UI_GUIDE's pattern, polling between your runs, not
  frozen at construction time — plus next wake)
- What has it done? (sessions timeline; trades with entry/exit/thesis/
  reason; honest P&L)
- What is it thinking? The trader's `journal/` is its OWN narrative of
  every wake — a primary source, rendered beautifully, entry by entry.
  The transcripts carry the full reasoning and receipts behind each
  entry; the wake reasons and session reports fill the gaps.
- What is it watching? (armed triggers, scanners, upcoming schedule)
- How is it performing? (equity curve from balance_snapshots; realized
  results — losses as plainly as wins)

Then the close-out, per your quality law (CLAUDE.md — build passes,
every route verified, mobile-first, honest data states, fresh-eyes
pass): build, verify, `data/restart_request.json`, update
`kv.next_run_at`, commit your workspace with a plain summary of what
you built and why.
