# Ops book — is it up, and how do I touch it safely?

*Written for the AI assistant. This is the foundation every other
book stands on: the instance facts you keep locally, the toolkit for
reaching the machine, the quirks that corrupt evidence when violated,
the layered health checks, the security sweep, and disaster recovery.
For "is it working, learning, honest?" read
[`AUDIT-PLAYBOOK.md`](AUDIT-PLAYBOOK.md); for the curve,
[`EVOLUTION-PLAYBOOK.md`](EVOLUTION-PLAYBOOK.md); for platform
currency, [`PLATFORM-RESEARCH-PLAYBOOK.md`](PLATFORM-RESEARCH-PLAYBOOK.md).*

## 1. Standing facts (kept in `audits-local/FACTS.md`)

Fill the template on first run and re-resolve after any stack change:
stack name and region, instance id, public address and domain, backup
bucket, SSM prefix, the stack parameters currently in force (every
`cloudformation deploy` must repeat all of them or defaults reassert),
the repository and its on-box clone path, the auth mode of the site,
the units in play, the CLI pin for both users, the models in force
per config, the mission's benchmark, and the owner's risk line if
one is set. Key paths that never change: workspaces
`/srv/{mind,ui}/workspace` (the brains — never write); ledgers
`/srv/{mind,ui}/ledger.db`; transcripts and prompt snapshots
`/srv/{mind,ui}/logs/sessions/`; daily logs `…/logs/daily/`; the app
`/srv/ui/app` (manager-owned, a git repository) and its serve snapshot
`/srv/ui/serve` (launcher-owned); envs `/srv/{mind,ui}/.env` (mode
600, never read through an agent); the engine `/opt/alpaca-mind`
(root-owned); the source clone `/opt/alpaca-mind-src` (root-only, and
the audit books are excluded from it — the README's third law). The
two kill switches: `/srv/mind/workspace/state/HALT` and
`/srv/ui/workspace/state/HALT` — one per agent.

## 2. The toolkit

All management is SSM; no SSH exists. For anything beyond a trivial
one-liner use the **script pattern**: write a shell script on your
own machine, base64-encode it, and send `echo <b64> | base64 -d |
bash` as the command. Keep the scripts locally — they are the
reproducible record of what you ran. Remote output that must be
captured to a file goes to a root-only temporary path, is read back,
and is deleted in the same script; nothing an audit produces stays on
the box. `docs/OPERATIONS.md` has the `run()` shape.

### Quirks (violating one corrupts your own evidence)
1. Quoting nested quotes, `$`, or backticks inline through any shell
   runner breaks silently or loudly — script pattern, always.
2. If your terminal is on Windows: force UTF-8 output and read remote
   results back from a file — some glyphs in agent output crash the
   console encoding.
3. If your local shell is Git Bash or similar: it rewrites
   leading-slash arguments into local paths (SSM parameter names,
   `--path` values); disable that conversion or script the call.
4. `journalctl --since "…"` and `sqlite3` with embedded quotes never
   work inline through a runner — script them.
5. On the box, **`sqlite3 -readonly`** for every inspection: a
   mistyped path otherwise *creates* an empty database.
6. Workspace git as root prints nothing (git's safe-directory rule) —
   always `sudo -u <user> git -C /srv/<user>/workspace …`.
7. Manual `trade` invocations need the mind's environment:
   `sudo -u mind -H bash -lc 'set -a; . /srv/mind/.env; set +a; trade …'`
   — source it inside the shell so the token never appears on a
   command line the journal records.
8. If your own harness refuses bare `sleep N && cmd` chains, put
   waits inside remote scripts or use until-loops.
9. `apt-get install` on the box can restart agent services
   (needrestart). Check both ledgers for open sessions before any apt
   operation.
10. **Engine updates, the safe sequence:** touch both HALT files (no
    new session can launch); wait until both ledgers show no open
    session; pull the source clone, copy the changed engine files,
    restart the affected units; remove both HALT files; confirm the
    next wakes are intact. The trade CLI needs no restart (it runs per
    call); supervisors and the sentinel do. The supervisor probes the
    CLI version per launch, so a CLI upgrade needs no restart either.
11. Setup re-runs remember their parameters from
    `/etc/default/alpaca-mind-setup`; after any hand-edit, verify the
    backup bucket and CLI pin survived.
12. Transcripts: `python3 /opt/alpaca-mind/engine/render_transcript.py
    <jsonl>` renders a session; filter token-count noise when
    reading.
13. **The law: agents' workspaces are their own.** Owner channels only
    — the mind's owner note and the manager's inbox, both defined in
    `docs/OPERATIONS.md` (the note is written as the `mind` user, its
    wake request has a fixed JSON shape, and it is filed while the
    mind sleeps and the market is closed if the book is open — the
    sentinel's own wake request holds one slot, and yours must not
    displace a protective fire). Engine, config, and scaffold fixes:
    repository first, then the box per the sequence above.
14. **A CLI upgrade is a model upgrade.** Aliases resolve inside the
    CLI; a new pin can move an agent onto a newer model of its tier.
    Upgrade per unix user at a clean session boundary (HALT-gated as
    above); canary with a one-turn headless run and read the init
    event's `model`; confirm the workspace is still trusted; update
    the saved pin; tell the agent as a world fact through its owner
    channel. Update the stack parameter only for *future* deployments
    — a stack update can replace the instance (§5). The ledger's
    `model_resolved` events record which model actually answered
    every session.

## 3. Layered health checks (H1–H7 ride every audit)

**H1 — cloud and repository:** stack status complete; instance
running; SSM online; local main, origin, and the box clone agree; the
engine matches the clone (`diff -rq` on the engine directory,
excluding caches and config).

**H2 — services:** every unit active; a two-hour error grep per unit
ideally empty; the proxy serving if one exists; the serve snapshot
present.

**H3 — liveness:** `state/status.json` recent with a sensible next
wake; newest daily-log lines recent on both streams; sentinel quote
polls flowing during market hours.

**H4 — the agents' loops:** last sessions exit 0 on both ledgers; one
workspace commit per session; transcripts non-empty with prompt
snapshots present; a journal entry for every trading day.

**H5 — trading truth:** positions against the ledger's open trades
agree; reconcile zero (never `--heal`); `state/unrecorded_fills.jsonl`
absent; `trade status` shows the orders-per-hour counter well under
its cap.

**H6 — the window:** the site answers per its auth mode; the
watermark advanced after the latest pass; the last build logged
clean; no restart request stuck.

**H7 — protections and safety nets:** open positions carry their
decided protection; the owner's risk line, if set, not crossed; last
night's backup verified (journal line and the object in the bucket);
disk under seventy percent; log caps unhit.

## 4. Security sweep (weekly with the audit; monthly in full)
- Engine root-owned, and an agent write test *fails*
  (`sudo -u mind test -w /opt/alpaca-mind/engine/trade.py`); the
  source clone unreadable to agents (`sudo -u mind ls
  /opt/alpaca-mind-src` fails).
- Workspace deny rules live; trust flags present for both users
  (`hasTrustDialogAccepted` under the workspace path in the user's
  `~/.claude.json`); an "ignoring permission rules" line in any
  session stream is a regression.
- Secrets: grep sample transcripts, both daily streams, and the built
  site for key shapes — the venue's key format, the model provider's
  token prefix, long base64-looking runs. Any hit: rotate first, then
  fix.
- The mind's lab packages: each established and traceable to a named
  use in a transcript; an unexplained obscure package is severity 1.
- Public surface: middleware mode as intended; mutating routes
  refuse anonymous requests (probe with a POST); no order-path code in
  the app; if a domain is configured, the certificate valid and
  auto-renewing.
- Security group unchanged (the web ports only); SSM-only management;
  no SSH keys anywhere.

## 5. Backups and disaster recovery
- Nightly backup to the stack's bucket on a self-expiring window,
  verified read-after-write. Check daily (H7).
- **Restore drill: quarterly**, and once soon after birth while the
  stakes are low — the full `docs/BACKUPS.md` restore onto a scratch
  stack, timed. The drill is the only proof the insurance pays.
  Never on the live stack, and **never with this deployment's
  account — paper included**: a paper login has one paper account, and
  a scratch mind trading it plants positions the live mind never
  placed (its next reconcile reports a divergence you caused). The
  scratch stack gets its own SSM prefix holding keys for a different
  brokerage account, revoked after the drill; a stack's genesis
  awakening fires the moment its services start.
- Before any stack update or risky change: run the backup manually
  and verify the object.
- **The base-image law:** the template resolves the newest OS image
  by pointer (so fresh deployments are always current), which means a
  stack update after a new image is published **replaces the
  instance and its disk**. Treat every stack update as a potential
  migration: back up first; confirm the instance id unchanged after.
  If a replacement ever happens unplanned: stop the services on the
  new box before its genesis agents act, restore, and delete any
  re-materialized wake request before starting services.

## 6. Cost, usage, and plan limits (operator-only — the standing law)
Agents never receive spend, caps, or usage as a message. The
`cost_usd` in the ledgers is API-equivalent shape data on a flat-rate
seat, read by you for bloat detection, never a bill, never a message
to an agent. **What a seat limit looks like from outside:** a session
that hits the plan's limit ends early with the limit named in its
result; the supervisor retries with backoff and then sleeps an hour —
so you see a cluster of short failed sessions, then a gap, then normal
life. That is not a defect and not a finding against the agent — and
during such a window a `refusal_retry` in the log is the supervisor's
fallback logic reacting to the failure text, not a model boundary.
Record the observed result subtype in FACTS.md the first time you see
one. The levers, all yours: **before birth**, the seeded
`state/schedule.json` (its slots name their own effort, which
overrides the config defaults) and the config's model and effort
defaults for everything else — edited in your fork before deploying
(`docs/MISSIONS.md`); **after birth**, wake hygiene only — the rhythm
is the mind's own. Never a note about usage, limits, or cost, and
never "use less."

## 7. Incident handling
Every incident goes into `audits-local/INCIDENTS.md` the day it
happens — what broke, how it was found, what fixed it, and which
class in the audit playbook's table it belongs to (add the class in
your fork's copy of the book, and upstream it). An incident whose fix
is structural leaves the books except as its class; an incident that
recurs after a fix goes one layer harder. And the improvement loop
applies: a base-repo fix is contributed upstream so nobody else meets
it.
