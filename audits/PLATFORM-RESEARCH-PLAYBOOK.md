# Platform research playbook — keeping a deployment on the frontier

*Written for the AI assistant. Your human says "run the platform
re-research." This is the method for re-auditing a deployment against
the current state of the model platform, the Claude Code runtime, the
venue's APIs and MCP server, and the deploy substrate — then upgrading
deliberately. The standing risk: **the platform advances monthly;
this app's assumptions froze at write-time.** Every finding is judged
against the product sentence (distinct from your deployment's mission
line in FACTS.md): a state-of-the-art, self-evolving trading mind,
deployable by anyone's AI, honest to a fault, no two alike.*

Research *is* capability here: the installer and the venue surface
run on findings verified by probe, not memory. This book keeps that
habit alive after birth.

## 0. How to run (cold start)
1. Read §1 — the baseline register is the diff target. Your
   deployment's dated watch rows live in `audits-local/FACTS.md`.
2. §2 version and drift check first — measure "new" from what the
   *box* runs, not from training data.
3. Fan out per §3.
4. Findings return as diffs ("the register says X; reality is Y;
   evidence: url"); classify per §4; verify load-bearing claims
   yourself before any migration panic.
5. Deliver per §5. An adopted change updates §1 in your fork's copy
   of this book **in the same change** — and goes upstream — because a
   stale register makes the next pass blind for everyone.

## 1. The baseline register (update on every adopted change)

### 1a. The runtime (the agents' body)
| # | Assumption | What it drove |
|---|---|---|
| C1 | Headless `claude -p` with stream-json output, a model alias, a turn cap, skipped permissions, an effort level, the workspace's MCP config, and forwarded subagent text; the CLI **pinned** by stack parameter — upgrades are deliberate canary acts, and **a CLI upgrade is a model upgrade** because aliases resolve inside the CLI | the supervisor's launch — the whole session mechanism |
| C2 | The result event carries turns, subtype, duration and the result text, alongside usage fields the engine discards on write (turns sum across the several result events a late subagent can cause); usage exists only in the operator's store, built from the CLI's own session files | the transcript writer's projection; the usage collector |
| C3 | Model aliases resolve; the init event names the resolved model; effort is behavioral, not a token budget | per-wake mind choice (agent-owned); `model_resolved` events |
| C4 | No native scheduling, triggers, or budgets — the supervisor, sentinel, and bell exist for that reason | the engine's reason to exist; the first thing to re-check each pass |
| C5 | Workspace `.claude/`: identity file, instrument roster, settings deny rules, a pre-tool hook (exit 2 blocks); **workspaces must be pre-trusted** or permission rules are silently ignored — setup does this; re-verify after any CLI upgrade | security posture |
| C6 | Headless sessions end when tool calls stop; background shell tasks die with them (hook-enforced); in-flight subagents are awaited at exit (the supervisor sets a generous ceiling) — subagent fan-out is the sanctioned concurrency path | session-lifetime physics in every charter |
| C7 | The stream schema (system, task, result events) is what the renderer and the audits parse; **re-verify schema, hook contract, and trust behavior on any CLI upgrade** | transcripts, audits |
| C8 | Long-lived subscription auth for headless sessions comes from an interactive token setup — a headless shell cannot complete it | deploy protocol |
| C9 | The agents' memory is their workspace memory system, not the CLI's user-scope memory — deliberate | evolution design |
| C10 | Web search is budgeted per session and shared with all subagents; agents route around exhaustion via fetches and primary sources | fan-out design |
| C11 | Subagents can do substantial work and then end without a final report; the parent salvages from the transcript. Reading a *running* subagent's output dumps raw stream into context | delegated-research reliability |
| C12 | Waiting in a session means a foreground polling loop inside one shell call; bare sleep chains may be refused by the harness | session wait mechanics |
| C13 | A seat's plan limit ends a session early with the limit named in the result; the supervisor backs off and sleeps — the shape is described in OPS-BOOK §6 | plan-limit signature; never a finding against the agent |

### 1b. Models and billing
| # | Assumption | What it drove |
|---|---|---|
| M1 | A tiered lineup: the deepest tier at the mind's helm; the next tier for agentic tool work (the manager and the subagent workhorse); lighter tiers for legwork. The names and the fitness map move with releases — keep the lineup and the last-verified release in `audits-local/FACTS.md` | config defaults; fitness maps |
| M2 | Billing is a flat-rate subscription seat; no per-token bills; plan limits make sessions wait, not degrade; the deepest tier consumes limits fastest | cost guidance; the operator-only economics law |
| M3 | Hosted runtimes (managed agents, scheduled cloud routines) are not adopted — the sentinel needs local polling and a local ledger, and self-sufficiency on one instance is a product feature. Re-evaluate quarterly | the one-stack design |
| M4 | Prompting doctrine per `docs/PROMPTING.md`, distilled from the official guidance for the models in force; craft drift is silent — re-diff it each deep pass | every charter and seed |
| M5 | **Model boundaries are epoch lines.** Record the first session on any new model in the local record; the evolution scorecard splits windows there; the mind's own fitness-map facts may be stale across the boundary and are its own to re-ground | evolution windows; owner notes |

### 1c. The venue (trading, data, MCP)
| # | Assumption | What it drove |
|---|---|---|
| V1 | The trading API is called raw (no SDK): paper and live, permission levels, multi-leg orders with per-leg sides and a single net limit, fractional rules | the venue adapter and the trade CLI |
| V2 | Market data is served on the account's entitled feed by default (the engine ships no feed override); the free tier's coverage and the paid tier's upgrade are documented facts the mind may weigh | the venue adapter; the feed escape hatch |
| V3 | **Vendor data can be systematically wrong, and a mind may detect and route around it.** If your deployment's mind has made such a finding, it becomes a watch row in FACTS.md: each pass re-checks whether the vendor fixed it (so the mind's workaround could simplify) and never fixes it for the mind | the mind's own venue doctrine |
| V4 | **The MCP server is launched unpinned** at every session — upstream ships changes straight into the agents' hands. Watch its releases every pass; pin if drift ever bites | the MCP mount |
| V5 | The trade CLI's stdout is a machine protocol the agents parse; stderr is narration and stays out of it when piped | log sink design |
| V6 | Any external constraints on the account (a program's rules, an event window, a data-plan condition) live in the local facts sheet and in the mind's identity as world facts | requirements handling |

### 1d. The deploy substrate
| # | Assumption | What it drove |
|---|---|---|
| I1 | One CloudFormation stack: its own network, an arm64 instance, SSM-only management, optional static address, a public-mode switch, HTTPS ingress inert until a proxy exists, a self-expiring backup bucket | the template |
| I2 | **The base image is resolved by pointer** so fresh deployments are always current — which means a stack update after a new image is published replaces the instance. The mitigation is the OPS-BOOK law (backup first, verify the instance id), not pinning | stack-update discipline |
| I3 | Setup is idempotent; parameters are remembered for re-runs; first boot does not restart what it just enabled; workspaces are seeded once; the app is seeded as a git repository; the web service serves from a snapshot the build never touches; the audit books are excluded from the root-only source clone | the setup script |
| I4 | A reverse proxy on the box provides TLS when a domain is added; package installs can bounce services | the domain procedure |

## 2. Version and drift check (first, every pass)
The box's CLI version against the current changelog — the changelog
delta is the primary research input. Engine drift (OPS H1). The MCP
server's latest release against last-known behavior (V4 moves without
you upgrading anything). The venue's API changelog against V1–V2.
**CLI upgrade procedure:** changelog delta → flag every §1a row it
touches → canary on a throwaway deployment with throwaway keys (the
product's own deploy path is the canary harness) → transcript audit →
upgrade the live box per the OPS-BOOK model-upgrade rule (per user,
HALT-gated, canaried, saved pin updated) → set the stack parameter for
future deployments (never as a live stack update without the
base-image law) → update the register in the same change.

## 3. Research protocol (fan-out)
- **Runtime researcher** (a Claude Code documentation agent if one is
  available): diff every C row; hunt native scheduling, triggers, or
  budgets (which would shrink the engine); headless flag changes (a
  renamed permission flag breaks every launch); schema, hook, and
  trust changes; subagent mechanics.
- **Models and platform researcher:** diff M rows; new tiers (a
  cheaper deep tier re-routes nothing lightly — the helm is a product
  decision for your human); plan changes; hosted-runtime maturity.
- **Venue researcher:** diff V rows; MCP server releases; data plans;
  the status of any vendor-data watch row; order types.
- **Craft researcher:** diff `docs/PROMPTING.md` against current
  official guidance — would the charters be written differently
  today?
- **Unknown-unknowns sweep (mandatory each deep pass):** every
  researcher also reads its source's full news and changelog for the
  window and walks the documentation's navigation tree, listing every
  capability that fits no register row. Each becomes a row — adopted
  or declined with a reason. The register grows every pass; it never
  merely confirms itself.

## 4. Adoption filter
| Class | Meaning | Posture |
|---|---|---|
| DELETE | a native capability replaces engine glue | strongest candidate; canary on a throwaway deployment |
| UNLOCK | a new capability serving the mission | bring to your human with the cost |
| SAVE | the same behavior with less compute or complexity | adopt after canary parity |
| BREAK | a deprecation touching a register row | urgent; schedule before end of life |
| MEH | does not serve the product sentence | record it; do nothing |

Rules: a change must delete code, add wanted capability, or cut risk
— name which. Stability beats novelty (novelty-chasing is how legacy
apps happen). One platform change per deploy. And the public-product
dimension: every adopted change belongs in the repository — contribute
it — so every future deployment inherits it.

## 5. Deliverable
Report the edge status (CURRENT / DRIFTING with a count / AT-RISK with
a pending BREAK); a findings table (row → change → class →
recommendation → effort); your human's decision list; the do-now
list; the register updates made; the tracker row updated and the
other books' due-status. Log the pass in `audits-local/TRACKER.md`.
