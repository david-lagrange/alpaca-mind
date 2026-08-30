# Evolution Pass — grow the window

Trader sessions have run since your last pass (the wake context says
how many, or that the owner asked for you). Your duties, any route:

1. **Read the inbox FIRST** (unread messages via lib/db). Every owner
   message is answered WITH INTERFACE — a new page, component, or view
   that directly addresses what they asked — then marked read and
   addressed with a note saying what you built and where.
2. **Read what the trader did** since your last pass: its `journal/`
   entries first (the trader narrating its own life — a primary
   source), then the new transcripts in `/srv/mind/logs/sessions/`
   (fan subagents across them when there are many), new ledger rows,
   new strategy artifacts (all read-only). Ask: what happened that the
   current interface does NOT yet show well?
3. **Grow the interface** where the story outgrew it: new dashboards,
   timelines, drill-downs, searches; new tables in your own database
   when a view needs curated data; refinements to what exists. Views
   of the PRESENT are built ALIVE (UI_GUIDE's living-component
   pattern: server routes polling live market/account data, client
   components refreshing with visible data age) — the window breathes
   between your runs. The bar is a window so good the owner feels
   present inside the trader's day — and honest: losses, mistakes, and
   lessons rendered as plainly as wins.
4. **Keep it current**: update `kv.next_run_at` so the inbox always
   shows when you'll look next.

Close out per your quality law (CLAUDE.md): build passes, every touched
route verified, mobile-first, honest data states, fresh-eyes pass —
then `data/restart_request.json`, commit, plain report.
