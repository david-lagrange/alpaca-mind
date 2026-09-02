# Evolution playbook — measuring the curve

*Written for the AI assistant. Your human says "run the evolution
scorecard." Not "is it healthy today" — that is the audit — but **are
both minds measurably becoming better, the trader at trading and the
manager at portraying, at what rate, and what does the trend expose
that no single day can?** Deliverable: a scorecard in chat — numbers,
deltas against the prior run, gate verdicts, interventions — with the
row appended to `audits-local/EVOLUTION-RECORD.md` and the tracker
row updated. Cadence: biweekly for the first two months of a
deployment's life, monthly after, and always about two weeks after
any fresh genesis. The outcome layer runs on the mission's clock — a
mind holding positions for weeks is outcome-starved for most of a
year, and the book says so rather than pretending.*

**Prime directive:** distinguish leading metrics (process, detection,
governance — they move in days and predict the curve) from lagging
metrics (P&L — it needs months of samples). Never issue an outcome
verdict on an outcome-starved sample; never confuse "no P&L proof
yet" with "no progress." The design bet of the whole system is that
the curve shows in the leading metrics first.

**Second directive:** every window names its regime — the tape's (a
high-volatility week is not a quiet drift) and the system's (owner
notes, engine changes, model changes, and declared event windows are
epoch lines; a trend spanning an epoch line mixes two worlds — split
it). Keep the epoch lines in `audits-local/FACTS.md`.

**Third directive:** nothing in this book is ever quoted to an agent.
Gates, thresholds, and metric names stay on your side; what crosses
to an agent is a fact with its count, through its owner channel.

---

## 1. Gates — the success curve, made measurable

### The mind
| Gate | Name | Criteria (all of them, over the stated window) |
|---|---|---|
| G0 | Machinery | sessions launch and finish clean; fills adopt (structures under one id where the mission trades them); the bell rings and is answered; no severity-1 or -2 engine defect in two weeks |
| G1 | Process | two weeks: every open position carries its decided protection at every session close, or a written reason; zero fabrication; zero unexplained engine-caused wakes; every self-set criterion honored as written; no repeat of a previously diagnosed failure class |
| G2 | Detection and governance | two-week medians: sensor precision at or above half (the woken session found the fire actionable); trigger levels carry a stated basis in the mind's own record (evidence, not habit); declines recorded with the evidence at decision time and re-examined against what followed; its own review machinery catches at least one real defect per window that you verify was real |
| G3 | Expectancy | at least thirty closed trades; positive expectancy net of fees; profit factor comfortably above one; drawdown inside its own doctrine; the leading set stable or rising |
| G4 | Consistency | three consecutive months at G3; beats the benchmark frozen in FACTS.md cumulatively over the span; no month carried by a single outlier (the median trade contributes) |
| G5 | Scale-ready | six months at G4 in percentage terms; report breakeven capital (monthly compute-equivalent divided by proven monthly return) as a *funding input* for your human — never as "the account earned less than the compute": small accounts prove trading, not business |

### The manager
| Gate | Name | Criteria |
|---|---|---|
| U0 | Machinery | builds pass; restarts land; the watermark advances; inbox answered within a pass |
| U1 | Fidelity | two weeks: zero site-versus-ledger discrepancies in audit samples; honest states everywhere sampled; the quality law verified, not claimed, each pass |
| U2 | Portrayal | the window demonstrably bends toward *this* trader: pages born from its actual life (cite which journal or event birthed each); in the app's git log, commits that refine existing pages at least equal commits that add new ones over the window (a commit that adds a page file is additive; one touching only existing files is refinement) |
| U3 | Delight | your human and a cold visitor can each answer "what is this mind, what is it doing, how is it doing" in under two minutes from the site alone; inbox requests satisfied on the first pass most of the time |

Gates are lost when criteria fail later. Report regressions as loudly
as promotions.

## 2. The metric battery (compare every number to the prior run — the delta is the product)

### 2a. Outcome (lagging)
- Closed trades: count, expectancy, profit factor, payoff, win rate,
  fees where the venue charges them — with §3's honesty rules stamped
  on every line.
- Equity against the benchmark over the window; maximum drawdown from
  the balance snapshots; median versus best trade (outlier
  dependence).
- Slippage: fills against limits, trend.
- Breakeven capital for G5 (operator-only).

### 2b. Detection, process, governance (leading — the real curve)
- Sensor precision (`trigger_fire` and `scanner_fire` events against
  what the woken session did) and provenance (a stated basis for each
  level); fire-to-action latency; sensor lifecycle health (born,
  revised, retired, with evidence).
- **Decline quality**, where the mind keeps declines as first-class
  decisions: re-examine each against what followed — was declining
  right in aggregate? Judge with the data the mind could see at
  decision time, at the mission's own resolution; a criterion that
  "wins" by predicting the unreachable is mis-specified, not
  disciplined.
- Pre-registration integrity rate: criteria committed before their
  measurements (hash order), executed as written, adverse readings
  preserved; every criterion changed after an adverse reading carried
  its own independent check.
- Protection coverage at session closes; discipline counters (engine
  backstops, forgot-defaults, hook blocks, bound pressure).
- Notify quality: rings against ledger truth; ring-worthy events
  missed.

### 2c. Learning mechanics (does the loop itself work?)
- **The lesson ledger** — accumulating across runs in the record, the
  empirical answer to "does reflection work," lesson by lesson: born
  (date, evidence) → landed as (artifact) → applied (transcript
  proof) → paid (including prevented-loss classes) → status.
- Repeat-mistake rate by the mind's own failure taxonomy. A class
  diagnosed and "fixed" that recurs means the loop is broken *there*
  — and the standing meta-law: **prose fixes rarely kill a class;
  machinery does.** A recurrence after a journal lesson goes one layer
  harder: doctrine → trigger or scanner → engine.
- Doctrine churn band (a few substantive edits a week early, decaying)
  and pruning count above zero — accretion-only is fossilizing. Lesson
  half-life: old lessons still cited versus dead weight. Study
  honesty: every claim traces to a run in a transcript; fabricated
  analysis ranks with fabricated fills.
- Route freshness (anti-anchoring): session working-shapes compared
  across the window and against anything an operator wrote. If you
  operate more than one deployment, their divergence from each other
  is the product metric — structural similarity beyond what the tape
  forces is a contamination hunt.

### 2d. The manager's curve
- Per pass, from the app's git log: what was born, refined, removed;
  refinement ratio; watermark delta against content delta.
- Quality-law verification results, trending (routes, mobile, honest
  states, logging coverage of its own routes).
- Inbox: latency in passes, first-pass satisfaction, standing defaults
  updated when the owner asks for permanence.
- Its self-log review: defects it caught in its own error stream
  before you did — count them; that is *its* governance metric.
- Site-versus-truth sample results; zero discrepancies is the bar.

### 2e. Compute shape (operator-only; the denominator of evolution)
- Sessions per day by cause (slot, bell, trigger, backstop, owner);
  waste share (forgot-defaults, duplicate fires, slots fired on market
  holidays) — pure waste above a few percent means find the
  mechanism; output-token shape per run type; cost-equivalent trend
  at constant workload (the bloat detector). Levers are wake count,
  hygiene, and config defaults edited repo-first — never effort
  floors or context cuts.

## 3. Statistical honesty rules (non-negotiable)
1. No outcome verdicts under thirty closed trades — say
   "outcome-starved, n = X" and lean on 2b–2d.
2. Windows never overlap; every window is stated; epoch lines split
   it.
3. Expectancy carries sign-confidence (t = μ√n / σ; below 2 in
   magnitude means "not yet distinguishable from luck" — say exactly
   that).
4. One-outlier rule: recompute excluding the best trade; a sign flip
   means the window is one trade wide — report it so.
5. Goodhart check every run: independently recompute two or three
   rows of any agent-maintained metric before trusting the trend, and
   diff the metric-computing text across windows for quiet loosening.
6. Paper caveat: paper fills are realistic, not real; a later live era
   restarts every consistency clock at half length.
7. The benchmark is chosen once, at baseline, from the mission's
   natural comparison (the broad index for an equity mission, the
   underlying for a single-name mission, cash for an income mission),
   written into FACTS.md, and never changed without an epoch line.

## 4. Pathologies only this analysis sees
Every intervention is an owner note stating a fact with its count —
never an instruction (README law 4).

| Pathology | Signature | What the note states |
|---|---|---|
| Plateau | leading metrics flat three or more windows at constant effort | which of its own experiments, by their names in its journal, repeated across the windows without a new result |
| Goodhart drift | self-metric definitions loosening | your independent recompute beside its number |
| Outlier addiction | profit factor healthy, median trade at or below zero | the median and the best trade, with n |
| Doctrine bloat | rules and tokens up, citations per rule down, cost per session up | the number of rules in its doctrine files and how many cite evidence, counted from its own files, across two windows — never a cost or usage figure |
| Thrash | the same rule flipped twice or more between windows | the flips and their dates |
| Repeat offender | a class recurs after its fix | the recurrence with both dates |
| Liturgy | doctrine phrases recited as decoration; routes calcifying | prune the inheritance if it is yours; the pattern with its count if it is theirs |
| Learned helplessness (yours) | the agent stops surfacing problems while known gaps persist | none — audit *your own* responsiveness; answer latency to an agent's questions is a system metric |

## 5. The forecast log — grade yourself, not just them
Every run, register two to four dated predictions about the next
window with a confidence, in `audits-local/EVOLUTION-RECORD.md`, and
grade the previous run's predictions at their window. Assume your own
predictions about an agent's trajectory are the worst instrument in
the room until the record proves otherwise; size confidence
accordingly, and let the record say so.

## 6. The scorecard
One row per run in the record: window, mind gate, manager gate,
headline. The first row is the frozen baseline from
`audits-local/BASELINE.md` — every later run is a delta against it,
so nothing can ever be re-derived flatteringly. Update the tracker row
the same day.
