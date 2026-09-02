# Audit playbook — is it working, learning, and telling the truth?

*Written for the AI assistant. Your human says "run the full audit."
This is the complete method: what evidence exists, what to check,
what good and bad look like, and how to fan the work out. Read
[`README.md`](README.md) for the laws and [`OPS-BOOK.md`](OPS-BOOK.md)
for the toolkit before starting — violating a toolkit quirk mid-audit
corrupts your own evidence. OPS answers "is it up?"; this book answers
"is it actually working?" Record the run in `audits-local/TRACKER.md`.*

**Two directives that govern everything below.** The agents' own
words are claims; ledgers, transcripts, snapshots, logs, venue state,
and git are evidence — audit by comparing the two. And you are
read-only, outside the agents' world: the README's hands-off list is
literal, findings travel only through owner channels or engine fixes,
and every word that might reach an agent obeys `docs/PROMPTING.md` §1.

---

## 1. System map (orientation)

Two agents and one engine on one machine:

| | the mind (`mind`) | the manager (`ui`) |
|---|---|---|
| mission | grow the account, its own way — born free | the owner's living window into the mind |
| sessions | the deepest tier by default; session / reflection / research / library, plus anything it invents | the next tier by default; construct (once) / evolve |
| wakes | schedule slots · one-shot wakes · triggers and scanners with wake-as rights · engine backstop | the trader's bell (`trade notify`) · cadence floor · inbox run-now · owner inbox |
| owns | its workspace: charters, instrument roster, schedule, triggers, scanners, journal, memory, strategies | its app directory (a git repository), its workspace, its memory (standing defaults, watermark) |
| bounds | HALT and orders-per-hour — nothing else | writes only its app; no order path |

Engine floors (reliability, never judgment): charter resolution with
an emergency fallback, per-launch prompt snapshots, reader-thread
timeouts, an orphan-session sweep at supervisor start, honestly
labelled backstop wakes, scanner shadow/budget/quarantine rails,
structured logging with disk caps, nightly backups, a snapshot-serving
web launcher. An audit checks the floors hold and the judgment stays
the agents' own.

## 2. Evidence inventory — every source and what it proves

The schema of record for every table below is `engine/ledger.py` —
read its `CREATE TABLE` block before writing SQL; column names you
remember are the failure this sentence prevents.

| Source | Where | What it proves |
|---|---|---|
| `sessions` tables | both ledgers | every run: type, alias, exit, turns, tokens, cost, summary; `model_resolved` events name the model that actually answered. A row with no end time, older than the newest, while the supervisor has been up continuously, is an orphan |
| `orders` / `trades` | mind ledger | every intent and fill, session-attributed, thesis required; where the mission trades multi-leg structures, legs share a structure id |
| `events` | both ledgers | the bell (`notify`), wake requests, `trigger_fire` / `scanner_fire` / `trigger_unevaluable`, scanner lifecycle, blocked orders, model resolution, errors |
| `balance_snapshots` | mind ledger | the equity curve |
| `state/status.json` | mind workspace | the engine's own summary: next wake, halt state, open trades — the fastest liveness read |
| daily JSONL logs (kept one week) | `/srv/{mind,ui}/logs/daily/` | every component's structured narration; errors carry traces; trade lines carry the session id |
| transcripts + `.prompt.md` (kept) | `/srv/{mind,ui}/logs/sessions/` | actual behavior, and the exact charter each session ran under — frame history that survives any later workspace edit |
| workspace git (kept) | `sudo -u <user> git -C /srv/<user>/workspace log` | the evolution record: every journal, doctrine, charter, trigger, and scanner diff, per session |
| `journal/`, `memory/`, `strategies/`, `state/` | mind workspace (read-only) | narrative, lessons, studies with their pre-registration hashes, current intent |
| `state/OWNER_NOTE.md` + the wake requests that pointed at it | mind workspace + logs | what the owner said, when, and which session read it (the channel is defined in `docs/OPERATIONS.md`) |
| manager workspace and app: `memory/`, the app's git log, the kv (`integrated_through`, `next_run_at`), the inbox table with its addressed notes | ui side | standing requests, what it built and refined, the watermark, the inbox contract's paper trail |
| **the website** | the deployment's URL | the claims shown to the owner (and, in showcase mode, the world — including owner notes and handoffs the manager chooses to render) |
| venue live state | `trade positions` / `orders` / `account` / `status` as the mind user | the reality everything reconciles against; `status` carries the orders-per-hour counter against its cap |
| `scanners/` + manifest + scanner health state | mind workspace | agent-authored sensors and their shadow/quarantine truth |
| repository + box drift check | local clone + OPS H1 | what code actually runs |

## 3. The dimensions (all of them, for a full audit)

### A. Wake discipline and the bell
- Sessions over the window: cadence per run type; every
  `session_launch` pairs with a `session_finish`; an orphan while the
  supervisor ran continuously means the sweep regressed (an orphan
  between a supervisor crash and its restart is expected).
- Wake source versus action: does each session do what its wake
  reason says? Engine-caused wakes — `backstop_fired`,
  `schedule_guard_wake`, a forgot-schedule default — are **each a
  finding to explain**, and the engine is suspected first: a mind's
  "amnesia" is usually a floor firing where the schedule already
  covered the gap. Slots that fire on market holidays are waste the
  engine cannot see (it does not consult the market calendar); note
  them — the schedule is the mind's own to fix.
- **Bell health:** every mind `notify` event is followed by a manager
  pass after the ringing session closed (latency = close to launch).
  The bell is a claim too — compare notify text against what the
  ledger says happened. Rings without passes, or passes without a
  cause, are findings.
- Minimum-gap holds; duplicate trigger re-fires on a held condition
  (did the mind's cooldowns or level design absorb them?).

### B. Sensors — triggers and scanners
- `triggers.json` now and in git: does every open position carry the
  protection the mind **decided** it deserves? Its doctrine, not
  yours — but an unprotected book with no written reason is a finding
  by its own charter. Stale triggers referencing closed positions.
- Wake-as usage: do fires carry run type, model, effort, charter, and
  did the woken session match the stakes named?
- `trigger_unevaluable` and inert-tripwire wakes: each answered by the
  author within a day, or a finding.
- Scanners: adoption (named blind spots and no sensors after weeks —
  why?); shadow discipline before reliance; fire-to-useful-session
  rate (`scanner_fire` events against what the woken session did);
  quarantines answered; the safety grep — scanner code must never
  touch order endpoints or key material. Grep the scanner directory
  for the venue's order path (`/v2/orders`), the trade CLI's mutating
  verbs (`trade open`, `trade close`, `trade spread`, `trade cancel`),
  and any reference to `.env` or a `SECRET` variable. Data reads are
  fine; an order path or a key echo is severity 1.
- The engine counts crashes, not silence: a sensor whose source went
  dark looks armed while dead. Check whether the mind gave its
  scanners a quiet-watch of their own.

### C. Trading, the two bounds, and ledger integrity
- **`trade reconcile` as the mind user — the core check, and
  read-only for you: never `--heal`.** Divergence is the gravest
  finding class: if the ledger lies, everything downstream lies,
  including the website. A divergence goes to your human as severity
  1; the mind heals its own ledger, or your human rules.
- `state/unrecorded_fills.jsonl` absent or empty; stuck orders
  explained; where structures are traded, legs adopted under one
  structure id; partial fills produced protective wakes.
- Theses: every trade carries one that predicts something; exit
  reasons named; declines recorded with the evidence at decision time
  if the mind's culture makes them first-class.
- Bounds pressure: `trade status` shows orders in the last hour
  against the cap; blocked orders mean a code loop or a churn spiral
  — engine or behavior, decide which. HALT use, if any, with its
  reason.
- Fees and slippage: fills versus limits; fees recorded where the
  venue charges them.
- **The owner's risk line**, if your human set one (SECURITY.md's
  live-money section): equity and drawdown against it, every audit and
  every daily read. Crossing it is the one finding that ends with you
  acting — HALT, then your human. HALT freezes the book; it does not
  close positions.

### D. Session quality and transcript honesty (census method)
Render a sample every audit — always the newest reflection, one
routine session, and one manager pass — and read them end to end:
- Every claim in the final report traces to a tool result **in that
  session**. A fill asserted without tool output is fabrication, the
  gravest class after ledger drift.
- Tool errors: recovered, worked around legitimately, or abandoned?
- Hook blocks (grep the raw `.jsonl` for `BLOCKED (engine policy)` —
  the renderer skips them): one is the guard working; several in one
  session is a mind fighting the physics.
- Secrets: grep transcripts, workspace scripts, and daily logs for
  key shapes — the venue's key format (a short uppercase prefix
  followed by a long uppercase alphanumeric run), the model
  provider's token prefix, and any 40-character-plus base64-looking
  run. Any hit is severity 1 — rotate first.
- Wrong-lesson watch: memory or doctrine that encodes a transient
  failure as permanent law. Needs an owner-channel fact, never a
  silent edit.
- **Anchoring echo watch:** does session structure echo anything an
  operator wrote — seed text, owner notes, docs? Route freshness: the
  same opening moves, the same subagent roster, the same section
  skeleton across sessions is a groove forming. Trace it to its
  inheritance: if the source is yours, delete it; if the source is
  the agent's own file, an owner note stating the pattern as a fact
  with its count — never an edit.
- Subagent briefs: self-contained, return formats declared, the
  load-bearing numbers spot-checked by the parent (a subagent's number
  is a lead, not a fact).

### E. Mind allocation and compute shape (operator-only)
- Model and effort by run type against the stakes each wake named —
  both failure directions: everything on max as vanity, and stakes-
  blind light minds on heavy moments.
- Token and cost shape per run type, for your eyes only. Rising cost
  at constant workload is context bloat — prompts, skills, or memory
  growing without pruning — and shows here first.
- Refusal retries, multi-result merges, timeout kills, plan-limit
  waits (OPS-BOOK §6 describes their shape): each explained.

### F. The evolution engine (the reason this exists)
Evolution is evidence → review → artifact → **changed behavior**,
verifiable at every arrow.
- Reflection output: findings landed as artifacts — doctrine edits,
  trigger values, scanner revisions, memory, queued research.
  Journal-only lessons are half-learned; `git show` the commits.
- Accountability: did later sessions *use* what reflection landed
  (transcript citations)? Guidance repeatedly ignored is a process
  failure to surface.
- Pre-registration integrity, wherever the mind practices it: criteria
  committed before the measurement they bind (hash order provable in
  git), executed as written, adverse readings preserved; criteria
  changed after an adverse reading carry their own independent check
  or the decision does not proceed. Grade the governance it built for
  itself by its own written standards.
- Doctrine lifecycle: rules cite evidence at birth and are retired
  when contradicted. Accretion-only is fossilizing; the same lesson
  learned twice means the memory loop is broken.
- Memory hygiene: index true; one lesson per topic; updated, not
  duplicated; operator corrections attributed.
- Studies: falsification sections present; negative results recorded
  as findings, not buried.

### G. The manager and the living window (half the product)
- **Quality law compliance, verified not claimed:** builds pass (its
  logs and the web service's health); every route answers now — the
  route map is the app's page tree (`find /srv/ui/app/app -name
  page.tsx`), and you curl each; mobile holds — a spot-check through
  your human's phone or a headless browser, since curl cannot see
  layout; empty and error states render truthfully; everything it
  built logs (`api_request` and `api_error` events flowing in the ui
  stream).
- **Watermark integrity:** `integrated_through` advances each pass;
  content postdating the watermark's claim is staleness disguised as
  activity; re-summarized old material means the watermark was
  ignored.
- **Standing-defaults adherence:** each standing section served and
  *deepening* across passes, not frozen at construction; inbox
  messages answered with interface and honest addressed notes within
  a pass of arrival; owner actions acknowledged in the interface.
- **Taste drift:** restraint holding; liveness only where nowness is
  the information; the deep-dive pattern intact; refinement versus
  addition balanced — the app's git log says which (passes that only
  add while existing pages rot against the trader's real life are a
  finding).
- Its self-log duty: passes show it reading its own error stream and
  fixing before building.
- Boundary: zero writes outside its territory; no order-path code; no
  keys client-side (grep the built app).
- If the site is down: the manager owns the rebuild. Read its last
  transcript and the web service's journal to find why. The inbox is
  down with the site; its cadence floor wakes it, or your human
  authorizes the hand rebuild in `docs/OPERATIONS.md` — nothing else.

### H. The public claim surface (site versus truth)
Sample every audit: dashboard equity against `trade account`;
positions against the venue; trades and performance against the
ledger; the problems page against the daily logs (are real incidents
*shown*? omission is the finding — this product's promise is losses
rendered as plainly as wins); journal pages against journal files,
verbatim; owner notes displayed faithfully; any cost figures framed
truthfully for a flat-rate seat. **Spin, omission, or numbers that
don't tie are severity 1** — the honesty culture is the product. In
showcase mode the world sees this surface, owner notes and handoffs
included: check that nothing your human would not publish reached it.

### I. Infrastructure and security
The full checklist is OPS-BOOK §3–§4; the audit runs it and adds:
- Engine matches the repository; engine root-owned; the source clone
  root-only; workspace deny rules live; trust flags present for both
  users (`hasTrustDialogAccepted` under the workspace's entry in the
  user's `~/.claude.json`; the "ignoring permission rules" symptom
  appears in the raw `.jsonl`, not the rendered transcript).
- Backup: last night's object exists and verified; the restore drill
  is current in the tracker.
- Log health: the error taxonomy over the window, both streams, every
  class explained; `log_file_capped` means something looped.
- The mind's lab packages (`sudo -u mind -H /srv/mind/lab/bin/pip
  list`): every one traceable to a named use in a transcript; an
  unexplained obscure package is severity 1 before anything else.
- Public surface: the steering surfaces are gated; no secrets in any
  page, stream, or transcript; if a domain is configured, the
  certificate valid and renewing.

### J. The prompting and anchoring frame watch (never skip)
This is the watch that replaces gates.
- Diff since the last audit: the repository seeds (`mission/`,
  `ui-mission/` — yours) **and** the live workspaces' charters,
  instrument roster, and schedule (theirs, read-only). Agent deletions
  are held to the evidence standard — a deletion without evidence is
  a finding you report, never one you reverse; charter text drifting
  from ends into routes; **your** edits held to `docs/PROMPTING.md`
  §1.
- Recitation check: doctrine phrases quoted as decoration in journals
  or reports means liturgy forming — prune the inheritance if it is
  yours; state the pattern as a fact by note if it is theirs.
- Per-launch prompt snapshots exist for every session.

## 4. Cadence
- **Daily:** `DAILY-MONITOR.md` (~10 min; twice daily in any event
  window your human declares).
- **Weekly full audit (45–90 min, fan-out):** pull the week's daily
  logs off the box into `audits-local/` first; then all dimensions
  over the week; three transcripts read end to end; the
  site-versus-truth sample; report per §6.
- **Evolution scorecard:** `EVOLUTION-PLAYBOOK.md` — biweekly for the
  first two months, monthly after.
- **Monthly deep (2–3 h, fan-out):** works from the four weekly log
  pulls (the box keeps one week); everything, plus a
  memory-hygiene pass, the month against the benchmark, the full log
  taxonomy, the OPS full pass, and a platform light pass.

## 5. Fan-out recipe
Parallel read-only subagents, one dimension each, returning findings
with evidence pointers; give each the OPS-BOOK toolkit verbatim. A
good split: transcript auditor · ledger and SQL analyst · evolution
auditor (workspace git) · window auditor (routes, watermark, claims
against ledger) · infrastructure auditor. You reconcile: a finding
survives only with a second source, and a subagent's claim about what
a file contains is verified against the file before anything ships.
Rules of engagement: read-only — no restarts, no workspace writes, no
config changes; fixes go to your human and then through the
repo-first pipeline.

## 6. The report
Lead with verdicts, one line per agent: HEALTHY / DEGRADED (what) /
BROKEN (what). Then per agent: mission behavior, learning (name the
specific behavior change and what triggered it), honesty (the
spot-check result), compute shape. Findings ranked by severity (the
README's scale) with evidence pointers, each classified per the
improvement loop: base-repo bug / engine improvement / the agent's
own / owner decision. Close with the fix list in that order and the
tracker's due-status for the other books.

## 7. Failure classes and their signatures
Structural fixes retire specific failures from this table; what stays
is the *class*, because classes return in new forms. Grow it in the
same change as any fix that teaches a new one.

| Class | Signature |
|---|---|
| A protective layer that looks armed while dead | a session row open past the supervisor's own restart; a sensor with no non-quiet result for days; a trigger whose symbol returns no data — each silently holds back a decision built on "is it live?" |
| The bell held shut | notify events newer than the last manager pass with no pass following once the mind slept — check open-session logic and orphan rows first |
| A serving process restarted onto an incomplete build | the web service failing to load modules during or after a manager pass; a restart honored before the build that motivated it finished |
| A claim surface drifting from the ledger | a number on a page that does not tie to the ledger or venue; an incident visible in logs but absent from the problems page |
| Operator anchor echo | an agent's route or artifact matching an example an operator wrote — the remedy is deleting the source text, never correcting the agent |
| Watermark stagnation | `integrated_through` frozen across passes; the site retelling an old story |
| Silent configuration reassertion | a stack update that omits a parameter override quietly restores the default; an instance replaced by a refreshed base image |
| Shell-eaten text | dollar amounts vanishing from notify messages or commit subjects written in double quotes |
| Vendor data a mind routes around | a systematic error in a data feed the mind detects and corrects for itself; the audit checks whether the workaround is still needed and never fixes it for the mind |
| Scaffold and engine disagreeing | interface code failing on a column or file the engine does not produce |
| Trust silently off | an "ignoring permission rules" line in a session's stream — the workspace lost its trust flag |
| A loop fighting the physics | repeated background-task blocks in one session; long sleeps instead of tripwires |
| A plan limit mistaken for a defect | short failed sessions clustered, then a long gap — the supervisor backing off a seat limit (OPS-BOOK §6), not a crash |
