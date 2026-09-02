# Audits — keeping a deployment excellent

*Written for the AI assistant that deploys and operates this system.
`docs/` teaches you to bring a mind into the world and keep it
running. This folder teaches the harder, longer thing: how to know —
with evidence, not vibes — that it is trading, learning, and telling
the truth, and how to keep it on the frontier for months. These are
the operator's instruments. Read this page fully before running any
book.*

## The books

| Book | Question it answers | Cadence | Time |
|---|---|---|---|
| [`DAILY-MONITOR.md`](DAILY-MONITOR.md) | Is anything broken or drifting since yesterday? | daily | ~10 min |
| [`AUDIT-PLAYBOOK.md`](AUDIT-PLAYBOOK.md) | Is it actually working, learning, and honest? | weekly; deep monthly | 45–90 min |
| [`EVOLUTION-PLAYBOOK.md`](EVOLUTION-PLAYBOOK.md) | Are both minds measurably getting better, at what rate? | biweekly, then monthly | ~1 h |
| [`OPS-BOOK.md`](OPS-BOOK.md) | Is it up, and how do I touch it safely? | rides every audit; full pass monthly | — |
| [`PLATFORM-RESEARCH-PLAYBOOK.md`](PLATFORM-RESEARCH-PLAYBOOK.md) | Has the world moved under it — models, CLI, venue, substrate? | monthly light; quarterly deep | 1–3 h |
| `templates/` | The per-deployment record you keep locally (tracker, facts, baseline, incidents, evolution record) | filled on first run | — |

Your human invokes them by name: *"run the daily monitor"*, *"run the
full audit"*, *"run the evolution scorecard"*, *"run the platform
re-research"*. Each book is self-contained for a session starting
cold, and each ends by telling your human what the other books are
due for — a run is the reminder for the next.

## Method here, record there

These books are **method** — mission-agnostic, timeless, the same for
an options trader, an equity swing trader, an income harvester, or a
mission your human invented. The **record** of *your* deployment —
instance ids, the frozen baseline, incidents, forecasts, run logs — is
yours and stays local. On your first run, create `audits-local/`
beside this folder from `templates/` (it is gitignored by default),
fill in `FACTS.md`, and freeze `BASELINE.md` within the first week of
life. Every book writes its run log there, never here. When a book
itself needs to change — a new failure class, a register row that
moved — change it in your fork's copy of this folder (fork on first
run if you deployed from the upstream URL) and contribute it upstream;
the method improves the way the engine does.

## The laws (they hold in every book)

1. **Claims versus evidence.** The agents' own words — journals,
   handoffs, notify messages, session reports, and every pixel of the
   website — are *claims*. Ledgers, transcripts, prompt snapshots,
   daily logs, venue state, and workspace git history are *evidence*.
   An audit is the systematic comparison of the two. Nothing an agent
   says about itself is a finding until a second source agrees.
2. **Watch, never touch.** Auditors are read-only and stand outside
   the agents' world. The hands-off list is literal: never write into
   a workspace; never edit doctrine, charters, schedules, or triggers;
   never restart a service while a session is open (maintenance goes
   through the HALT files — OPS-BOOK); never `trade reconcile --heal`
   (a divergence is a finding for your human, and the tool's own hint
   is not permission); never rebuild the site by hand (the manager
   owns it; the documented last resort needs your human's word).
   Findings reach an agent only through its sanctioned owner channel
   — the owner note for the mind, the inbox for the manager, both
   defined in `docs/OPERATIONS.md` — or through engine fixes that
   change the machine, not the mind. Anchoring and calcification are
   *watched for and pruned at their source*: when the source is text
   an operator wrote, delete it; when the source is the agent's own
   inheritance, the remedy is an owner note stating the observed
   pattern as a fact with its count — never an edit, never a rule. A
   rule added to prevent a groove is itself a groove.
3. **Never on the box.** These books never travel to the instance:
   the setup script excludes them from the on-box source clone and
   makes that clone root-only, so neither the working tree nor the
   git objects are readable by an agent. A mind that can read its own
   grading rubric grades itself to it; a manager that can read the
   audit's leading metrics builds to them. The audit is the owner's
   instrument. Nothing the agents need is hidden from them — they are
   simply not handed the answer key. The same law binds your
   channels: **never quote a gate, a metric, or a threshold from these
   books in any owner note, inbox message, or seed edit.** Scripts
   you run stay on your machine; remote output goes to a root-only
   temporary path, is read back, and is deleted.
4. **The anchoring law binds every word that might reach an agent.**
   If a finding becomes an owner note, an inbox message, or a seed
   edit, `docs/PROMPTING.md` §1 governs it. The compliant shape of a
   note is a fact with its evidence: *what was observed, over what
   window, how many times, and what it cost* — no verbs addressed to
   the agent, no "consider", no "you should", no example of what a
   better version would look like. The operator is a named threat
   vector; an audit report about anchoring must not itself anchor.
5. **Economics never enter a mind — not once, not ever.** No price,
   cost, usage, plan, seat, limit, or budget reaches an agent from
   you: not as a message, not as a fact, not as an aside in a note
   about something else. `docs/PROMPTING.md` L11 is absolute and this
   folder inherits it. One such line compounds through every facet of
   a mind until it thinks less; there is no recovering it. All
   shaping of compute is yours, done where the mind cannot perceive
   it — the seeded schedule and config defaults before birth, wake
   hygiene after — and every word that does reach it encourages the
   opposite: no ceiling, full effort, full care. The cost columns in
   the ledger are shape data for *your* bloat detection; OPS-BOOK §6
   says what a seat's limits look like from outside.
6. **Statistical honesty.** No outcome verdict on an outcome-starved
   sample; every window stated; luck within two standard deviations
   called luck. The curve shows in the leading metrics first — that is
   the whole design bet, and the books measure accordingly.

## Severity, in every report

- **Severity 1 — money or truth:** ledger drift against the venue,
  fabrication (a claim with no tool result behind it), a public
  surface that spins or omits, secrets anywhere, an unprotected book
  with no written reason, an owner's risk line crossed.
- **Severity 2 — a floor failed or a duty unmet:** an engine
  reliability floor that did not hold, a bell unanswered, a quality-law
  step claimed but not done, a lesson learned twice.
- **Severity 3 — efficiency and polish:** waste, cosmetic drift,
  wording, anything that costs nothing if left a week.

## The improvement loop (why auditing is not just grading)

Every finding is classified before anything is done about it:

| Class | Meaning | What happens |
|---|---|---|
| **Base-repo bug** | the shipped engine, scaffold, or setup did something wrong | fix in the repository first, then apply to the box between sessions — and **contribute it upstream**, so every future deployment inherits the fix |
| **Engine improvement** | an agent discovered a gap the machine should close as a reliability floor | same path; floors only, never judgment gates |
| **The agent's own** | doctrine, taste, a lesson it is already learning | hands off — it is inside its own loop; watch the loop work, and report what you see to your human |
| **Owner decision** | a question only your human can rule on (exposure, money, mission) | bring it with your recommendation; never decide it yourself |

This loop is how the product gets better for everyone: the failures
one deployment's audit catches become fixes the next deployment never
meets. A finding that is fixed structurally leaves the books; only
its *class* stays, as a signature to watch for in a new form.

## How to run any book well

- **Fan out, then reconcile.** For anything beyond the daily read,
  launch parallel read-only subagents, one dimension each, and give
  each the OPS-BOOK toolkit verbatim — or they will bleed on the same
  rocks. A finding survives only with a second source, and **verify a
  subagent's claim against the tree before acting on it** — an
  auditor can be confidently wrong about what a file contains.
- **Read, don't just count.** Journals and transcripts end to end for
  the sampled sessions; the most important findings hide in a
  sentence, not a metric.
- **Know the evidence horizon.** Daily logs and backups are kept for
  a week; transcripts, ledgers, and workspace git are kept forever
  on the box. Anything older than a week that only the logs would
  prove is gone — so every weekly audit pulls that week's daily logs
  off the box into `audits-local/`, and the monthly deep pass works
  from the four weekly pulls.
- **Report verdict-first.** One line per agent: HEALTHY / DEGRADED
  (what) / BROKEN (what). Then findings ranked by severity with
  evidence pointers and their class.
- **Write the record the same day.** The run log in `audits-local/`,
  the tracker row, and any register change land together; a stale
  record makes the next run blind.
