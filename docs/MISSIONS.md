# Missions — changing what the mind is FOR

*Written for the AI assistant. The default mission is options trading.
If your human wants a different mission, design it WITH them before
deploying — this is the how.*

## What a mission is (and is not)

A mission is the agent's PURPOSE and WORLD — never its strategy. The
founding design principle of this project is that the agent is **born
free**: you may change what it is for, what account it manages, what
its universe is, and what it should care about; you should not hand it
entry rules, indicators, sizing formulas, stop-loss doctrine, or risk
tolerances. It builds those itself, from research, and that is where a
deployment's individuality comes from. If your human asks you to bake
in a strategy, explain the principle — then respect their choice; it
is their deployment.

## Where a mission lives

Everything is in the `mission/` directory, seeded ONCE to the instance
at first boot (after that, the workspace belongs to the agent —
redeploying does not overwrite a living brain):

| File | What to edit |
|---|---|
| `mission/.claude/CLAUDE.md` | The identity: who it is, its mission line, its universe, its world facts. This is the main edit. |
| `mission/prompts/AWAKENING.md` | The first-ever session. Usually only the "meet the market" flavor needs adjusting. |
| `mission/prompts/SESSION.md` / `REFLECTION.md` / `RESEARCH.md` | The charters (duties, not routes). Rarely need mission-specific edits — they are deliberately universal. |
| `mission/state/schedule.json` | The seeded rhythm (reflection/research times). Match the mission's natural clock. |
| `config/mind.yaml` | Engine knobs (timeouts, poll rates). Rarely needs changing. |

Edit → commit to your human's fork → deploy with
`RepoUrl=<fork clone URL>` (DEPLOYMENT.md §3). For an already-deployed
instance, mission changes are the AGENT's to adopt: put a note in its
workspace (`state/` — an "owner note" file), or simply tell it via its
inbox-visible journal culture; never overwrite a living workspace from
outside.

## Mission ideas beyond the default (offer these if asked)

- **Equity swing/rotation trader** — drop the options emphasis from
  CLAUDE.md; universe = US stocks and ETFs; same machinery works
  unchanged (the trade CLI and sentinel handle equities natively).
- **Income harvester** — mission framed around steady premium capture
  and drawdown aversion; the agent still derives HOW itself.
- **Event trader** — mission framed around catalysts (earnings, macro
  prints); pairs naturally with the scanner system.
- **Long-horizon compounder** — a calmer clock: sparser seeded
  schedule, mission language about weeks not days.
- **Research-first paper lab** — a mission that prioritizes building a
  measured playbook before size; good for humans who want to watch
  the science.

For each: the edit is 80% `CLAUDE.md` identity language + schedule
seeds. Keep the born-free section, the honesty section, and the duties
intact — they are the institution, not the mission.

## The world-facts rule

Anything the agent genuinely needs to know about its situation belongs
in CLAUDE.md as a stated FACT of its world (account type, universe,
any real-world constraint of the venue or account). Facts inform;
directives cage. Write "this account cannot short" (fact), not "never
be bearish" (directive).
