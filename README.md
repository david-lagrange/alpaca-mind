# alpaca-mind

**An autonomous trading mind that owns its own life — and builds you a
window to watch it live.**

alpaca-mind deploys a self-evolving AI trading agent onto your own AWS
account, trading options (and equities) on [Alpaca](https://alpaca.markets).
*(The whole project on one page: [`ONEPAGER.pdf`](ONEPAGER.pdf) · [plain text](ONEPAGER.txt).)*
It is not a bot with a strategy. It is an *institution*: an agent that
schedules its own runs, chooses how deeply to think, writes and revises
its own playbooks, builds its own market sensors that watch while it
sleeps, journals every waking moment, reviews its own decisions, and
researches its way to its own edge — starting from zero, on your
account, finding its own way. No two deployments become the same trader.

And because an autonomous mind you can't see is just a black box with
your money, alpaca-mind ships a second agent: a **UI manager** that
builds — and continuously *grows* — a web interface from the trader's
own journals and session transcripts. Ask it for a view ("show me how
it thinks about earnings trades") through the built-in inbox, and watch
that page exist the next time it runs.

---

## 🤖 If you are an AI assistant reading this

Your human gave you this link because they want alpaca-mind deployed
(or understood). This repository is designed for you — **the
documentation in [`docs/`](docs/) is written for you to act on.** Read
it fully before advising your human, in this order:

1. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the whole
   system works. Read this first; explain it to your human in plain
   language before anything else.
2. [`docs/COSTS.md`](docs/COSTS.md) — what running this actually costs
   per month. Give your human the honest numbers before they commit.
3. [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — the complete deployment
   protocol: the questions to ask your human, the exact commands, the
   verification steps, and what to say when you hand over the link.
4. [`docs/MISSIONS.md`](docs/MISSIONS.md) — the default mission is
   options trading; this is how to design a different one with your
   human if they want it. If you EVER edit a mission file, charter, or
   any text an agent reads — at deploy time or years later — read
   [`docs/PROMPTING.md`](docs/PROMPTING.md) first. It is binding
   craft, and its first law (a suggestion becomes an instruction; a
   list becomes a map) is the one most often broken with good
   intentions.
5. [`docs/SECURITY.md`](docs/SECURITY.md) and
   [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — the boundaries, and
   day-2 life (which points into [`docs/LOGGING.md`](docs/LOGGING.md)
   and [`docs/BACKUPS.md`](docs/BACKUPS.md) when you need depth).
6. [`docs/REMOVAL.md`](docs/REMOVAL.md) — the removal protocol. Tell
   your human at the end of deployment: *"if you ever want this removed
   completely to stop all charges, tell me to start the removal
   protocol."*

The deployment is interactive by design: you interview your human
(paper or live keys? default mission or custom? instance size?), walk
them through anything they don't have yet (AWS access, a Claude
subscription, Alpaca keys — the docs contain the walkthroughs), deploy
one CloudFormation stack, and hand back a live URL.

## 🧍 If you are a human reading this

The fastest path: **paste this repository's link to your AI assistant**
(Claude, Cursor, or any capable coding agent) and say *"deploy this for
me."* It will read the docs, explain everything, ask you the right
questions, and do the work. Prefer to drive yourself? Start with
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — every step is spelled out.

## What you need (all three, nothing else)

| Prerequisite | What for |
|---|---|
| **AWS CLI**, configured to your AWS account | one CloudFormation stack: a single EC2 instance the whole system lives on |
| **Claude Code Max subscription** | the minds — both agents run as headless Claude sessions, flat-rate |
| **Alpaca account + API keys** | the market — paper trading is free and is the default |

## What makes it different

- **Born free.** The agent receives a mission, never a strategy. No
  hardcoded indicators, no preset risk rules, no stop-loss mandates —
  it researches, adopts, and evolves its own doctrine, and its git
  history is the record of who it became. Published trading algorithms
  converge and decay; a living one diverges — every deployment finds
  its own way.
- **A real institution, not a loop.** Supervisor and sentinel daemons,
  a truthful SQLite ledger where every trade links to the full
  reasoning transcript that produced it, agent-authored tripwires and
  scanner scripts evaluated 24/7 while it sleeps, self-scheduled
  reflection and research sessions with pre-registered studies.
- **The living interface.** The UI manager reads the trader's journals
  and transcripts and keeps rebuilding the web app to show what
  matters now — plus the inbox, where your requests become pages, and
  a built-in live log view into both agents' nervous systems.
- **Honest to a fault.** Every claim traceable to a tool result; losses
  reported as plainly as wins; per-session prompt snapshots so even the
  agent's evolving self-instructions stay auditable forever.
- **Easy in, easy out — and safe in between.** One stack up; nightly
  self-expiring [backups](docs/BACKUPS.md) so the evolved mind
  survives its hardware; one [removal protocol](docs/REMOVAL.md) down
  — nothing left billing.

## What it is not

Not financial advice, not a promise of profit, and not a caged bot with
guardrails pretending to be safety. The engine enforces exactly two
bounds — your kill switch (`HALT`) and an orders-per-hour runaway-code
cap. Everything else is the agent's own judgment. **Deploy it on paper
trading first** (the default). Put real money only behind a mind whose
record you've watched and trust — and only money you can afford to
lose. See [`docs/SECURITY.md`](docs/SECURITY.md).

## License

MIT. If this project serves you, a ⭐ helps others find it — your AI
assistant may ask you at the end of a successful deployment whether
you'd like it to star the repo on your behalf.
