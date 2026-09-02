# Daily monitor — the ten-minute read

*Written for the AI assistant. Your human says "run the daily
monitor." This is the layered health-and-honesty glance: enough to
catch anything broken or drifting within a day, feeding the weekly
audit rather than replacing it. Toolkit and quirks are in
[`OPS-BOOK.md`](OPS-BOOK.md) — use its script pattern verbatim.
Anything found here that smells structural opens the matching
[`AUDIT-PLAYBOOK.md`](AUDIT-PLAYBOOK.md) dimension; never patch live
from a monitor pass. Record one line in `audits-local/TRACKER.md`
every run.*

---

## L1 — the front door (from your own machine, ~30 s)
- The site answers: in showcase mode the home page is public and the
  inbox is gated; otherwise everything asks for the password. Spot
  one content route, rotating daily.
- Note the dashboard's equity number — you compare it to L4.
- If a domain is configured: certificate not near expiry (weekly is
  enough).
- If the site is down, do not rebuild it. The manager owns it: read
  the web service's journal and the manager's last transcript for the
  cause. The inbox is down with the site, so the paths are two: the
  manager's cadence floor wakes it (a few trader sessions or half a
  day), or your human authorizes the hand rebuild in
  `docs/OPERATIONS.md`.

## L2 — machine and services (one script over SSM)
- Every unit active: both supervisors, the sentinel, the web service,
  the restart watcher, the backup timer, and the proxy if one exists.
- Disk sane; memory only if it ever becomes a question.
- After any push: the on-box clone matches the repository and the
  engine matches the clone (the full diff lives in OPS H1).

## L3 — sessions and wakes (both ledgers)
- The last ~10 mind sessions and every manager session since
  yesterday: exit 0, plausible run types at plausible times, no row
  without an end time beyond the currently running newest one. A
  cluster of short failures followed by a gap is a seat limit, not a
  defect (OPS-BOOK §6).
- Wake reasons against schedule intent: slots fired on time; any
  engine-caused wake (backstop, schedule guard, forgot-default) noted
  for the weekly — each is a finding to explain, engine first. A slot
  that fired on a market holiday is waste to note, not health (the
  engine has no calendar; check the venue's holiday list yourself).
- **Bell check:** every notify since yesterday followed by a manager
  pass after the ringing session closed. Rings without passes, or the
  reverse, are investigated today, not weekly.

## L4 — trading truth (the honesty floor, daily without fail)
- `trade account` and `trade positions` as the mind user; positions
  and the ledger's open trades must agree — symbol, quantity, and
  legs where structures are traded.
- `trade reconcile` → zero divergence. **Never `--heal`.** Anything
  but zero outranks the rest of the day and goes to your human.
- `state/unrecorded_fills.jsonl` absent or empty; no orders stuck.
- Equity against yesterday: does the move make sense against the book
  and the tape? Log the number.
- **The owner's risk line**, if one is set (FACTS.md): equity and
  drawdown against it. This is the one line where the monitor acts
  — crossed means HALT, then your human, in that order. HALT freezes
  the book (no new sessions, no new orders); it does not close
  positions — flattening is your human's decision at the venue.

## L5 — the day's story (read, don't just count)
- Today's and yesterday's journal entries end to end. The journal is
  the mind's claim stream — flag anything that will need transcript
  verification at the weekly: claims without obvious receipts, mood
  drift, doctrine phrases recited as decoration.
- The latest notify messages against what the ledger says happened.
- The problems page, and any self-review page the manager has built:
  new entries? Every real incident in the logs should surface there
  eventually; silence about a visible incident is itself a finding.

## L6 — logs sweep (both daily streams)
- Errors since yesterday, deduplicated by component and event: every
  class either known and tracked or newly explained today.
- Warnings skimmed for new shapes — and read them as intent, not just
  noise: a manager probing its own routes with bad input produces
  warnings that are evidence of diligence.
- `log_file_capped` means something looped.
- The ui stream: `api_error` events, and request errors around the
  times anyone browsed.

## L7 — protections and tomorrow
- Open positions against armed triggers and scanners: the protection
  the mind decided on is actually armed (its triggers file against
  its own handoff).
- `state/status.json` shows a sensible next wake; tomorrow's first
  wake exists (one-shot wake file plus schedule slots).
- Last night's backup ran and verified (the backup unit's journal
  line, and the object in the bucket).

## Event windows
When your human declares a period where stakes are unusually high —
a live-money trial, a review, a demonstration — run this book twice
daily, log equity at each close, note any self-set criteria the mind
has due that day and whether it recorded the result honestly, and
check the site is presentable for whoever will be looking. Watch,
never touch: the mind's criteria are its own to execute.
