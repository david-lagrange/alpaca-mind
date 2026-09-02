# Tracker — when each book last ran, when each is next due

*Copy to `audits-local/TRACKER.md` on first run. Purpose: no run ever
silently lapses. Two rules make it work: every run updates its row
here the same day as its log entry, and every run's report ends with
the other rows' due-status — each run is the reminder for the next.
Cadences start from the deployment's birth; the first evolution
scorecard lands about two weeks after it.*

| Book | Cadence | Last run | Outcome (one line) | Next due |
|---|---|---|---|---|
| DAILY-MONITOR | daily (twice daily in a declared event window) | — | — | — |
| AUDIT-PLAYBOOK (full) | weekly (pull the week's logs off the box); deep monthly from the four pulls | — | — | — |
| EVOLUTION-PLAYBOOK | biweekly for two months, then monthly; outcome layer on the mission's clock | — (baseline in BASELINE.md) | — | — |
| OPS-BOOK full pass | monthly (H1–H7 ride every audit; security sweep in full monthly) | — | — | — |
| PLATFORM-RESEARCH | monthly light; quarterly deep; and on any event trigger | — | — | — |
| Restore drill (docs/BACKUPS.md; own SSM prefix, a different account's keys, revoked after) | quarterly, and once soon after birth | never | — | — |

## Standing watch-dates and event triggers
- Event windows the owner has declared (with their dates and what
  makes them different).
- The agents' own upcoming self-set criteria worth watching — watch,
  never touch.
- Decisions parked for the owner.
- Event triggers that run a book slice immediately: a CLI, model, or
  MCP-server release; an unrecognized platform error in any session;
  a planned stack update (the base-image law); a venue changelog
  touching trading or data; the owner asking "does this matter?"

## Run logs (one line per run, per book)

### Daily monitor
| Date | Equity | Verdict | Notes |
|---|---|---|---|

### Full audit
| Date | Scope | Verdicts | Headline |
|---|---|---|---|

### Evolution scorecard
| Date | Window | Mind gate | Manager gate | Headline |
|---|---|---|---|---|

### Platform research
| Date | Type | Outcome |
|---|---|---|

### OPS full pass / restore drill
| Date | What | Outcome |
|---|---|---|
