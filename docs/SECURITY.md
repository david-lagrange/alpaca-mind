# Security — the boundary model

*Written for the AI assistant. Explain the relevant parts to your human
in plain language — especially the live-money section if they go
there.*

## The trust design in one paragraph

The trader is trusted with JUDGMENT (that is the product); nothing else
on the machine is trusted with more than its job. Boundaries are
enforced by unix users and filesystem permissions first, agent settings
second, and prompts never — a rule that matters is a rule the OS
enforces.

## The boundaries

| Actor | Can | Cannot |
|---|---|---|
| Trader (`mind`) | trade via its CLI + MCP tools; write its own workspace/lab; read its own everything | write the engine; touch `/srv/ui`; read `.env` files (settings-denied) or SSM; sudo |
| UI manager (`ui`) | write `/srv/ui/app` + its workspace; READ the trader's entire workspace (journals, memory, doctrine, strategies, state), ledger, and transcripts (group read-only — the window sees everything, verbatim) | write anything of the trader's; place any order (no trade CLI path, no venue write creds needed for its job); sudo |
| Web app | serve read-views + the inbox | reach anything but its own SQLite, the read-only ledger, the daily log streams (read-only), and account READ endpoints |
| Engine daemons | root-owned code, run as the agent users | — |

The web app sits behind HTTP Basic Auth over EVERY route (user
`owner`, the UI password from SSM); with no password configured it
serves a 503 rather than running open. The security group opens ONLY
the UI port; all management is SSM Session Manager (no SSH, no keys).

**Showcase mode** (stack parameter `UiPublicMode=true`): for owners who
WANT the world watching, the read-only site opens to anyone while the
steering surfaces stay gated — the inbox (page and API, reads included)
and every mutating request, on any route, current or future
(method-based gating, so pages the UI manager builds later inherit the
rule). Nothing the read-only site can show is a secret by construction
— logs, journals, and pages carry no credentials — but it does expose
the account's positions and P&L to anyone with the URL: a deliberate
choice for a public demonstration, not a default.

## The inbox threat model (read this one carefully)

Inbox messages are OWNER TEXT that becomes UI-MANAGER WORK — that is
the feature. The containment is structural: the UI manager's writable
world is the UI app alone, it has no order path, and the trader never
reads the inbox. The worst a malicious or careless message can cause
is a bad interface change, which the quality law (build gates, route
verification) and git history make visible and revertible. Keep the UI
password strong and private: whoever holds it steers the window (never
the trading).

## Secrets

SSM SecureString → per-user `.env` (mode 600) at boot → process env.
Agents' settings deny reading env files; transcripts are the record of
sessions, and sessions have no reason to echo secrets — if your human
ever pastes a key into a session by accident, rotate it at the
provider. Rotation = update the SSM parameter, re-run the `.env`
materialization from setup (or edit the file), restart services.

Two surfaces that leave the box are secret-free by construction: the
structured logs never receive keys or auth headers (LOGGING.md), and
the nightly backup archives exclude `.env` files and credential caches
(BACKUPS.md) — backups travel to S3; secrets never do.

## Live money (the honest section)

This software ships **no risk cage** — that is a design decision, not
an oversight (see the README). On a live account the agent can lose
money in any way a free trading mind can, including all of it. Two
protections exist and only two: the owner's `HALT` file and an
orders-per-hour runaway-code bound. Before flipping
`ALPACA_PAPER=false`, your human should have watched the paper record
long enough to trust the mind's OWN evolved risk doctrine — and deploy
only money they can afford to lose entirely. There is also a middle
path worth offering: live account, small capital, watched closely,
with the kill switch one command away.

If your human wants an additional owner-side bound (a drawdown line at
which you halt it, a review-before-live checkpoint), implement it as
YOUR standing duty as their assistant — checking the UI and applying
HALT is exactly the kind of watch an owner may delegate to their own
AI. Keep it owner-side; the mind stays free.
