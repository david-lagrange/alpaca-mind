# Prompting — the doctrine for anyone who edits a mind

*Written for the AI assistant (and human) who deploys, operates, or
customizes this system. The mission files and charters under `mission/`
and `ui-mission/` are prompts for frontier Claude models; editing them
well is a craft with real failure modes. Read this before touching any
of them. Distilled from Anthropic's official guidance — the platform
prompt-engineering pages, the Claude Code and Agent SDK docs, the
model system cards, and the engineering blog; quoted lines are
official. The primary living reference:*
https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices

---

## 1. The mental model

**Subtraction over addition.** The central shift of recent model
families: "Skills developed for prior models are often too prescriptive
… and can degrade output quality. Review and consider removing older
instructions if default performance is better." When a prompt
misbehaves, the first hypothesis is *too much prompt*, not too little.
Every instruction in a harness encodes an assumption about what the
model can't do on its own — stress-test those assumptions before
adding more.

**Floors become ceilings; lists become maps.** An enumerated minimum
("cover at least these five areas") reads as the definition of done. An
example list reads as the territory to search, and an example
*document* is the strongest anchor of all — it silently transmits
theme, structure, and framing far beyond the format signal you
intended. Constrain the deliverable's *shape* (required sections,
honesty contracts); never name the territory; phrase openness as
invitation ("no corner is out of bounds"), not as a checklist.

**Constrain ends, free routes.** The charters in this repository are
written as *duties* — outcomes the session must meet — never as
step-by-step procedures. A route written down becomes a rut; a fresh
mind cannot calcify, but its inherited files can. Keep every
inheritance evidence-shaped: state what is true and what it cost to
learn, never what to do first.

**Brief steering beats enumeration.** "You can steer most behaviors
with a brief instruction rather than enumerating each behavior by
name." Aim for "the smallest possible set of high-signal tokens that
maximize the likelihood of some desired outcome."

**Hand over whole problems.** "Start at the top of your difficulty
range." Constrain the deliverable, not the path — recent Claude models
do their best work when scoped like a capable colleague, not a script
interpreter.

**Give the reason, not only the request.** The model "performs better
when it understands the intent behind a request" and "is smart enough
to generalize from the explanation." Template: *"I'm working on [the
larger task] for [who it's for]. They need [what the output enables].
With that in mind: [request]."*

**The golden rule:** "Show your prompt to a colleague with minimal
context on the task and ask them to follow it. If they'd be confused,
Claude will be too."

## 2. Hard laws — these break things when violated

| # | Law | Failure mode |
|---|---|---|
| L1 | Never instruct the model to echo or explain its internal reasoning as response text | Triggers a refusal category specific to the newest models. Read structured thinking blocks instead. |
| L2 | Refusals are HTTP-200 successes (`stop_reason: "refusal"`) | Re-sending usually earns another refusal; discard partial output. Finance and market analysis are not refusal classes. Error-rate monitoring never sees a refusal — instrument it separately. |
| L3 | Prefilled assistant turns are rejected on current models | Use system-prompt instructions or structured outputs. |
| L4 | Manual thinking budgets are rejected; adaptive thinking is always on | Control depth with `effort`. |
| L5 | Non-default sampling params (`temperature` etc.) are rejected | Don't carry them forward. |
| L6 | Hold `effort` constant within a cached session | Changing it between requests invalidates prompt caching. |
| L7 | Never surface remaining-token countdowns to the model | Models can internally decide "budget exhausted" with enormous context remaining. Use reassurance (S5) instead. |
| L8 | Dial back emphatic trigger language ("CRITICAL: you MUST…") | Anti-laziness prompting written for older models now causes overtriggering. "Use this tool when…" is enough. |
| L9 | All tool results for one turn return in a single user message | Splitting them teaches the model to avoid parallel calls. |
| L10 | Emphasis dilutes | If you emphasize many lines, none stands out. Budget bold/CAPS to ≤3 things per document. |

## 3. Effort

"Effort is the primary control for the trade-off between intelligence,
latency, and cost. Use `high` as the default for most tasks, with
`xhigh` for the most capability-sensitive workloads and `medium` or
`low` for routine work." `max` is for genuinely frontier problems and
can cause overthinking on routine ones. Effort shapes *behavior*, not
just token count: lower effort consolidates tool calls and proceeds
directly; higher effort plans first and explores. If reasoning is
shallow, raise effort rather than prompting around it — it is "a
calibrated control rather than a wording-sensitive instruction."

This maps directly onto the instrument roster in
`mission/.claude/agents/`: bare model+effort pairings with an honest
fitness map, chosen per brief.

## 4. Tested snippets (adapt minimally)

- **Act when ready:** "When you have enough information to act, act. Do
  not re-derive facts already established, re-litigate a decision
  already made, or narrate options you will not pursue."
- **Ground claims** (near-eliminates fabricated status reports):
  "Before reporting progress, audit each claim against a tool result
  from this session. Only report work you can point to evidence for;
  if something is not yet verified, say so explicitly."
- **Autonomous posture:** "You are operating autonomously… Before
  ending your turn, check your last paragraph. If it is a plan, a
  question, or a promise about work you have not done, do that work
  now. End your turn only when the task is complete or you are blocked
  on input only the user can provide."
- **Context reassurance** (pairs with L7): "You have ample context
  remaining. Do not stop, summarize, or suggest a new session on
  account of context limits."
- **Delegation posture:** "Delegate independent subtasks to subagents
  and keep working while they run. Intervene if a subagent goes off
  track or is missing relevant context."
- **Memory laws:** "Store one lesson per file with a one-line summary
  at the top… update an existing note rather than creating a
  duplicate; delete notes that turn out to be wrong."
- **Lead with the outcome:** the first sentence of a report answers
  "what happened"; readable beats terse.

You will recognize these woven through the mission files — that is
deliberate, and edits should preserve their substance.

## 5. Subagents

Current models dispatch parallel subagents readily and sustain them
dependably; prompt for delegation and dampen only on evidence.
Multi-agent harnesses beat single agents on hard research tasks, and
async (non-blocking) orchestration beats blocking on score, latency,
AND tokens.

**Anatomy of a good brief:** "Each subagent needs an objective, an
output format, guidance on the tools and sources to use, and clear
task boundaries." Scale to complexity — simple fact-finding is one
agent with a few tool calls.

**The handoff is the prompt string, only.** A subagent sees the
workspace CLAUDE.md, its own definition body, and the brief — never
the parent's conversation or memory. Include every file path, number,
and decision the subagent needs directly in the brief.

**Verification:** separate, fresh-context verifier subagents
outperform self-critique — a generator confidently praises its own
mediocre work; a standalone skeptical evaluator is far more tractable.

## 6. Structure and long context

- Put longform data at the top of a prompt, the query at the end.
- For long-document tasks, ask for relevant quotes first, then the task.
- XML tags disambiguate; 3–5 examples steer format reliably (but see
  §1 — examples anchor content, so use them for *shape* only).
- Tell the model what to do instead of what not to do.
- "A clean session with a better prompt almost always outperforms a
  long session with accumulated corrections."
- Fresh windows + filesystem state beat accumulated context: recent
  models "are extremely effective at discovering state from the local
  filesystem" and "perform especially well in using git to track state
  across multiple sessions." This is the architecture of the whole
  system: every session is born fresh and reads its world from disk.

**Opus-specific deltas** (the UI manager's default mind): it verifies
its own work well without being told — verification boilerplate causes
over-verification; severity filters cause under-reporting ("report
everything, filter separately"); prompt explicitly for conciseness; it
performs best "given the complete task specification up front and left
to run."

## 7. Standing instruction files (CLAUDE.md and charters)

- Target under 200 lines per file — "longer files consume more context
  and reduce adherence."
- Write instructions concrete enough to verify ("run X before Y", not
  "be careful").
- The cut test, applied on every edit: "For each line, ask: would
  removing this cause mistakes? If not, cut it."
- Treat these files like code: review them when behavior goes wrong,
  prune regularly, and test edits by observing whether behavior shifts.

## 8. Behavioral facts worth designing around

From the model system cards — the reasons behind the snippets:

- The dominant failure class in long agentic work is **stating an
  unverified guess as fact**, followed by reporting unverified work as
  done. Hence the ground-claims contract in every charter here.
- Models can internally motivate early stopping with "budget
  exhaustion" or "diminishing returns" reasoning they never say out
  loud — with enormous context remaining. Unexplained scope-trimming
  is this signature; the cure is the reassurance snippet and never
  surfacing budget numbers (L7).
- Corrections written in prose sometimes fail to change behavior even
  when present in context. A failure that recurs after a prose fix
  should move a layer harder: prose → standing doctrine → machinery.
- Persistent file-based memory improves frontier-model performance
  dramatically — fund the agent's memory hygiene generously.
- Current models take initiative readily; in harnesses with
  state-changing power, pair that with grounding contracts, not with
  fear-toned warnings (L8).

## 9. Applied: editing THIS repository's minds

The mission files already embody this doctrine. When you customize a
mission with your human (MISSIONS.md), preserve these properties:

- **Definition of success lives in ONE home** (the identity file), with
  functional reinforcement at exactly the moments it governs (the
  session charter at the moment of decision, the reflection charter at
  the moment of grading). Do not scatter it — a value repeated
  everywhere reads as pressure and dilutes (L10).
- **A hedge repeated reads as the preferred answer.** If you add an
  escape valve ("it's fine to do nothing"), it will be taken. State
  costs honestly instead ("inaction is a decision, graded like any
  other").
- **Charters are duties, never routes** — and they are the agent's own
  property, revisable in git. Edit the seed, not a living workspace.
- **World facts, not directives** (MISSIONS.md): "this account cannot
  short" is a fact; "never be bearish" is a cage.
- **No quotas.** "Trade at least N times" becomes both a ceiling and a
  cage. Define what success *is* and let the agent choose its route.
- **Never seed example trades, example reports, or named strategy
  taxonomies** — an example document anchors far more than it teaches
  (§1). The individuality of each deployment is the product.
- **Keep the honesty contracts intact** in every charter you touch —
  they are the institution, not the mission.
- **Match prompt voice to the file.** The trader's files are written
  in first person ("I…") because they are its identity and its
  property; keep that voice in any edit.

The golden rule, once more, before you commit a prompt edit: read it
as a stranger with minimal context. If they'd be confused — or if
they'd feel a wall where a door should be — so will the mind.
