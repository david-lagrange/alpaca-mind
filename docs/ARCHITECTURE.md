# Architecture — how alpaca-mind works

*Written for the AI assistant deploying or operating this system. Read
fully before explaining it to your human or changing anything.*

## The one-diagram version

```
┌─ EC2 instance (one CloudFormation stack) ──────────────────────────┐
│                                                                    │
│  /opt/alpaca-mind (root-owned, read-only to agents) — THE ENGINE   │
│    supervisor.py   wakes agents as headless `claude -p` sessions   │
│    sentinel.py     24/7 senses: triggers, fills, scanners          │
│    trade.py        execution CLI (auto-writes the ledger)          │
│    venue.py        Alpaca REST (options + equities + data)         │
│    ledger.py       SQLite: orders/trades/sessions/events/balances  │
│                                                                    │
│  user `mind` — THE TRADER                                          │
│    /srv/mind/workspace   its evolving self: CLAUDE.md identity,    │
│      prompts/ (charters), .claude/agents/ (subagent tiers),        │
│      journal/, memory/, strategies/, scanners/, state/             │
│      (schedule.json, wake.json, triggers.json, handoff.md, HALT)   │
│    /srv/mind/ledger.db   its quantitative memory                   │
│    /srv/mind/logs        session transcripts + prompt snaps +      │
│      daily/ (structured JSONL logs, one file per UTC day — every   │
│      engine component; the UI's Logs page renders them)            │
│    /srv/mind/lab         its own python venv (pip-extendable)      │
│                                                                    │
│  user `ui` — THE UI MANAGER                                        │
│    /srv/ui/workspace     its identity + charters                   │
│    /srv/ui/app           the Next.js app it builds and evolves     │
│      (inbox + kv in its own SQLite; reads the trader's ledger,     │
│       entire workspace, and transcripts READ-ONLY)                 │
│                                                                    │
│  systemd: mind-supervisor, mind-sentinel, ui-supervisor, ui-web    │
│    (+ ui-restart.path and the nightly mind-backup.timer → S3)      │
│  UI served on port 80 (Basic Auth, password set at deploy)         │
└────────────────────────────────────────────────────────────────────┘
        │                                   │
   Alpaca APIs (paper or live)         Claude (Max subscription,
   + Alpaca MCP server in-session      headless CLI sessions)
```

## The trader: an institution, not a loop

**Sessions.** The supervisor launches the agent as headless Claude
sessions. Each session gets a small WAKE CONTEXT header (why it is
awake, session-lifetime physics) followed by the charter for the run
type — a file the agent itself owns in `prompts/`.

**The agent owns its time.** `state/schedule.json` holds its recurring
cadence (reflection, research, anything it invents — seeded with a
sensible rhythm it may rewrite from day one); `state/wake.json` holds
one-shot wakes. Both may specify `run_type`, `model`, `effort`, and
`charter` — the agent chooses its own mind per wake. Malformed
schedules degrade to safe defaults, never to "fire now". One generous
aliveness backstop exists: if no reflection-class session completes for
days, the engine fires one wake that says plainly it is an engine
backstop — engine-caused wakes never impersonate the agent.

**The sentinel** never sleeps and never thinks — it evaluates the
agent's own tripwires (`state/triggers.json`: price levels,
bid/ask-aware variants, percent moves, ranges, order fills) every ~15s,
adopts fills that land after the placing session ended (including
multi-leg options structures, partial fills, and resting exits), runs
the agent's scanner scripts, snapshots the account balance, and wakes
the agent by writing `state/wake_request.json`. The agent's sensors
carry the same choice rights as its schedule: a trigger or a scanner
fire may name the `run_type`, `model`, `effort`, and `charter` its
wake should run under — a thesis-invalidation tripwire can summon the
deepest mind under a crisis frame the agent wrote for that moment.
Unevaluable triggers fail LOUD (an event plus an author-wake) — the
worst failure a protective layer can have is looking armed while
being dead.

**Scanners** are the agent's own Python sensors (`scanners/` +
`manifest.json`), run in isolated subprocesses with resource limits,
shadow-mode validation for new code, per-day wake budgets, and
quarantine after repeated failures. Research becomes a deployed sensor
without any human in the loop.

**The ledger** is the truth spine: every order is recorded *before*
the venue sees it, every trade links to the session (and therefore the
complete reasoning transcript) that produced it, and the agent never
hand-writes rows. `trade reconcile` diffs ledger vs venue whenever
anyone doubts.

**Evolution.** The agent journals every wake (`journal/`), reviews its
closed trades and its own transcripts in self-scheduled reflection
sessions, pre-registers research questions as git commits before
running the numbers, ships studies with their own falsification
attempts, and lands findings as edits to its skills, frames, triggers,
scanners, and memory. Git history is the record of who it is becoming.

**Born free.** The engine enforces exactly two bounds, both machine
protections: `state/HALT` (the owner's kill switch — touch the file,
everything stops launching) and an orders-per-hour cap (stops a code
defect from spamming the venue). Strategy, sizing, exits, and risk
doctrine are the agent's own, by design — see the README's "What it is
not".

## The market surfaces

Two, one venue. The **engine adapter** (`venue.py`, raw Alpaca REST)
powers truth: sentinel polling, the trade CLI, reconciliation. The
**Alpaca MCP server** is mounted into every trader session
(`mission/.mcp.json`) as the agent's exploratory hands — market data,
chains, account context — through structured tools. Execution always
goes through `trade` so the ledger stays truthful.

## The UI manager: a window that grows

A second, cheaper agent whose whole territory is `/srv/ui/app`. The
engine wakes it after the trader's FIRST completed session (so it
builds from real transcripts) for First Construction, then after every
few trader sessions, and immediately when the owner presses "run now"
in the inbox. The trader can also ring it directly — `trade notify`,
one command, callable from any session when something worth showing
happened — and the manager wakes as soon as that session closes; the
session-count cadence and max-gap are only the floor for a trader
that never rings. Each pass it reads the owner's standing requests
(a seeded memory file listing the sections the interface always
serves — live account tracking, trades with theses, lessons with
deep-dive reports, compounding knowledge, problems overcome, open-
trade trackers, the trader's own schedule), then the trader's journals
(the trader narrating its own life), transcripts, and ledger — from a
watermark, so it integrates only what's new — and grows the app:
pages, components, its own SQLite tables, whatever makes the trader's
inner life visible. Its taste is bound to restraint (live components
only where nowness is the information; a design language in
`ui/STYLE.md`), and its charters bind it to a hard quality law: builds
must pass, every route verified, mobile-first, honest empty/error
states, everything it builds logs, a fresh-eyes review — it never
restarts the site onto a broken build.

**The inbox** is the owner's steering wheel for *visibility* (never for
trading): messages become interface on the next pass, with an
addressed-note trail, and a "run now" button when something's waiting.

## Security boundaries (see docs/SECURITY.md for the full model)

- Engine root-owned; agents execute it, never write it.
- The trader cannot touch `/srv/ui`; the UI manager cannot WRITE
  anything under `/srv/mind` (filesystem permissions + settings deny
  rules), reads the ledger, transcripts, and the trader's whole
  workspace through read-only group access, and has no order path —
  its blast radius is "the interface changed".
- Secrets live in SSM and per-user `.env` files (mode 600); agent
  settings deny reading them; the whole web app sits behind Basic
  Auth.
- Headless sessions run a PreToolUse hook blocking backgrounded shell
  tasks (a session ends when it stops calling tools; background work
  would silently die — the hook makes the physics explicit).

## What runs when (defaults — the trader may rewrite its own)

| When | What |
|---|---|
| First boot | trader awakening → UI First Construction |
| Market hours | sentinel triggers/scanners wake the trader as armed |
| 9:10 ET weekdays (seed) | pre-open briefing — plan the day before the bell |
| 16:45 ET weekdays (seed) | trader reflection session |
| 20:30 ET nightly (seed) | library hour — study, build, explore |
| Sat 12:00 ET (seed) | trader research block |
| `trade notify` rung | UI evolution pass as soon as that session closes |
| Every ~4 trader sessions / 12h | UI evolution pass (floor, if never rung) |
| 00:00 UTC nightly | full backup to the stack's S3 bucket (7-day window) |
| Anytime | owner inbox "run now" → UI pass; `HALT` file → all quiet |
