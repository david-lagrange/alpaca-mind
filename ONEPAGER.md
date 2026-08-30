# alpaca-mind — the whole project on one page

**A living trading mind, not a trading bot.** alpaca-mind deploys an
autonomous AI agent onto Alpaca's options market with a mission and
nothing else — then lets it become a trader. Every claim below is
verifiable in this repository at the path cited.

## The AI logic: an institution that runs itself

The agent is a set of headless Claude sessions orchestrated by a
supervisor daemon — but the *agent* decides when it wakes, how deeply
it thinks, and under what instructions. It owns its recurring schedule
(`mission/state/schedule.json`), chooses model and reasoning effort per
wake, and writes the very charters its sessions run under
(`mission/prompts/` — revisable by the agent, in git, like everything
it owns). It spawns specialist subagents by picking from a roster of
bare model+effort "instruments" (`mission/.claude/agents/`) using an
honest fitness map instead of hardcoded roles. Between sessions, a
zero-cost sentinel daemon (`engine/sentinel.py`) evaluates the agent's
self-authored tripwires every ~15 seconds and runs the agent's OWN
Python scanner scripts in sandboxed subprocesses — research it performs
becomes deployed sensors, with shadow-mode validation, wake budgets,
and automatic quarantine protecting it from its own bugs. It journals
every waking moment, reviews its own closed trades and its own raw
transcripts in self-scheduled reflection sessions, and pre-registers
research questions as git commits *before* running the numbers so its
studies can't cheat. The result compounds: skills, doctrine, sensors,
and memory that are measurably different every week — with git history
as the record of who it is becoming.

## The truth machinery

Every order is written to a SQLite ledger *before* the venue sees it
(`engine/trade.py` — a crash leaves a pending row to reconcile, never a
phantom fill). Every trade links to the full reasoning transcript that
produced it. Fills that land after a session ends — including
multi-leg options structures and partials — are adopted by the sentinel
and wake the agent to respond. Tripwires that can't be evaluated fail
LOUD (an event plus an author-wake), because the worst failure a
protective layer can have is looking armed while being dead. Every
session's exact prompt is snapshotted to disk, so even the agent's
evolving self-instructions stay auditable forever.

## Risk, stated honestly

There is no risk cage, on purpose. The engine enforces exactly two
bounds, both machine protections rather than judgment: the owner's kill
switch (`state/HALT` — one file, everything stops) and an
orders-per-hour runaway-code cap. Sizing, exits, hedging, and risk
doctrine are the agent's own to research and evolve — that freedom is
the experiment, it is disclosed everywhere (`README.md`,
`docs/SECURITY.md`), and paper trading is the default. Published
trading algorithms converge and decay; a mind that builds its own
doctrine diverges. **No two deployments become the same trader.**

## Built on Alpaca to the bone

Alpaca's **MCP server** is mounted inside every agent session
(`mission/.mcp.json`) — the mind's exploratory hands are Alpaca's own
structured tools. The engine speaks raw **Trading API** and **Market
Data API** (`engine/venue.py`): options chains with greeks, multi-leg
order placement (`order_class=mleg`), quotes, snapshots, news, account
truth for reconciliation. Development and the default deployment run
entirely in the **paper environment**.

## The living interface

A second, cheaper agent owns a Next.js app (`ui/`) and nothing else. It
builds the interface *after* the trader's first real session — from the
trader's own journals and transcripts — then keeps growing it as the
trader lives: live-polling dashboards that breathe between its runs,
honest losses next to wins, and an **inbox** where the owner's requests
("show me how it thinks about earnings") become new pages on the next
pass, one click from immediate. Its charters bind it to a verification
law: builds must pass, every route checked, mobile-first, or it doesn't
ship (`ui-mission/`).

## Deployment is the demo

Three prerequisites — AWS CLI, a Claude Code subscription, Alpaca keys.
One CloudFormation stack. And the README's primary reader is not a
human: **paste the repo link to any AI assistant and it deploys the
whole system for you** — interviews you, explains the real monthly
costs, stands it up, hands you the live URL (`docs/DEPLOYMENT.md`), and
tells you the removal protocol that ends every charge
(`docs/REMOVAL.md`). Software for the age of AI operators, distributed
through them.

*MIT licensed. Everything above is in the repo — read the code, then
watch a mind find its own way.*
