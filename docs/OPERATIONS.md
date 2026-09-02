# Operations — day-2 life with a living system

*Written for the AI assistant operating an alpaca-mind deployment. All
management is via AWS SSM (no SSH keys exist). Set `IID` to the
instance id from the stack outputs; the one-liner pattern:*

```bash
run() { aws ssm send-command --instance-ids $IID \
  --document-name AWS-RunShellScript --parameters commands="$1" \
  --query Command.CommandId --output text; }
# then: aws ssm get-command-invocation --command-id <id> --instance-id $IID \
#   --query StandardOutputContent --output text
# (or just: aws ssm start-session --target $IID)
```

## The daily glance (what "healthy" looks like)

1. **The UI itself** — it is the designed surface; if it's fresh and
   the trader's journal entries are current, the system is alive.
2. `systemctl is-active mind-supervisor mind-sentinel ui-supervisor ui-web`
   → all `active`.
3. `cat /srv/mind/workspace/state/status.json` → recent `updated`,
   `halt` as expected, a sane `next_wake`.
4. `journalctl -u mind-supervisor -n 20` → `session_launch` events
   pair with `session_finish exit_code=0` (or read the same stream
   with filters on the UI's Logs page).

## Beyond the glance: the audit books

The daily glance above says "it's up." Whether it is actually working,
learning, and telling the truth — and whether it is still on the
frontier months from now — is the job of the operator's instruments
in [`../audits/`](../audits/README.md): a ten-minute daily monitor, a
weekly audit, an evolution scorecard, and a platform re-research
protocol, each written for you to run cold. They never travel to the
box (the setup script strips them from the on-box clone), and their
first law is the one this page states next: watch, never touch.

## Before you change anything an agent reads

Any edit to a mission file, a charter, or any text that enters an
agent's context — whether at deploy time, from an owner request, or in
day-2 tuning — goes through **PROMPTING.md** first. Its first law is
the one to hold hardest: a suggestion becomes an instruction, a list
becomes a map, and the fastest way to damage a free mind is to help it
with examples.

## The owner's controls

- **Kill switch (stop all trading):**
  `sudo -u mind touch /srv/mind/workspace/state/HALT`
  — sessions stop launching immediately; the sentinel keeps watching.
  Remove the file to resume. This is the owner's right, always.
- **The inbox** (in the UI): requests for what to SEE. It steers
  visibility, never trades.
- **The owner note** (to the trader): the one sanctioned way to tell
  the mind something about its world — a fact about the account, the
  venue, the machine, or a situation it cannot see. As the `mind` user,
  append to `/srv/mind/workspace/state/OWNER_NOTE.md`, then file
  `state/wake_request.json` with a `reason` that names the note (and
  a `wake_as` block if you want to choose the mind and effort that
  reads it). The next wake reads it. Write facts, never routes —
  PROMPTING.md's first law applies to every word, because an owner
  note is the strongest anchor a mind can receive. Never edit
  anything else in the workspace; it is the agent's own.
  The request's shape:
  ```json
  {"requested_at": "<UTC ISO-8601>",
   "reason": "OWNER NOTE: a note from your owner is at the bottom of state/OWNER_NOTE.md — <one line on what it concerns>.",
   "context": {"source": "owner"}, "protective": false,
   "wake_as": {"model": "fable", "effort": "medium"}}
  ```
  Filing the request is an immediate wake: a full session under the
  trading charter, at the mind and effort you name — choose them for
  the stakes of what you are telling it. Timing: file it while the
  mind is asleep, and — if positions are open — while the market is
  closed. The sentinel's wake request is a single slot: a request of
  yours sitting in it while a protective tripwire fires would displace
  that fire. Confirm it was read: `wake_request_serviced` followed by
  a `session_finish` with exit 0 in the log stream (a seat at its plan
  limit can consume the request without a session — re-file). Date
  each note, and once the servicing transcript shows it read, remove
  it (as the `mind` user): an owner-authored file that only grows in
  `state/` is exactly the anchor PROMPTING.md tells you to delete.
  What a note may carry: facts about its world, and observed patterns
  in its own behavior stated as counts over a window — never a route,
  a suggestion, or a number about spend. In showcase mode, assume the
  note will be rendered publicly by the manager.
- **Read the mind directly:** journals
  (`/srv/mind/workspace/journal/`), rendered transcripts
  (`python3 /opt/alpaca-mind/engine/render_transcript.py
  /srv/mind/logs/sessions/<file>.jsonl`), the exact charter any
  session ran under (`/srv/mind/logs/sessions/<stamp>-<type>.prompt.md`),
  and the ledger (`sqlite3 /srv/mind/ledger.db` — SELECTs).
- **Verify ledger vs venue anytime:**
  `sudo -u mind bash -lc 'MIND_CONFIG=/opt/alpaca-mind/engine/config/mind.yaml /opt/alpaca-mind/venv/bin/python /opt/alpaca-mind/engine/trade.py reconcile'`
  → `divergence_count: 0` is the healthy answer.

## Logs

Every component writes structured JSONL, split by UTC day —
`/srv/mind/logs/daily/` and `/srv/ui/logs/daily/` — rendered with
filters and a live tail by the **Logs page in the UI**, disk-safe by
construction, secret-free by design. **LOGGING.md** is the full
reference: streams, the event vocabulary, `jq` patterns, and the
safety bounds. When diagnosing anything, start there.

## Diagnostic patterns

| Symptom | Look at |
|---|---|
| No sessions for hours | `status.json` (halt? next_wake far out?); the supervisor's log stream — a `backstop_fired`, `schedule_guard_wake`, or `halt_active` event explains itself; `heartbeat_alarm` events in the ledger |
| A session failed | the `session_finish` event's `exit_code`/`subtype` (Logs page or journalctl); then read the transcript tail |
| Trigger never fired | `trade events --minutes 120` (as the mind user, env as above) — `trigger_unevaluable` / `trigger_symbol_no_data` events name the cause; the sentinel journal shows quote polling |
| UI stale | `journalctl -u ui-supervisor -n 20` (is it waking?); `journalctl -u ui-web -n 20`; the UI manager never restarts onto a broken build — check its last session transcript in `/srv/ui/logs/sessions/` |
| UI down | `systemctl status ui-web`; rebuild by hand as a last resort: `sudo -u ui bash -lc 'cd /srv/ui/app && npm run build' && systemctl restart ui-web` |
| Anything weird after an instance reboot | services are `Restart=always` and enabled — `systemctl` the four units; state survives on disk |

## Adding a domain (and HTTPS)

The offered final step of a deployment, in the order that makes it
durable. Total time ~10 minutes; certificates are automatic.

1. **Pin the address first.** The default deployment uses an
   auto-assigned public IP that changes on stop/start — a DNS record
   pointing at it would rot. Update the stack:
   ```bash
   aws cloudformation deploy --stack-name <stack> \
     --template-file deploy/cloudformation.yaml \
     --capabilities CAPABILITY_IAM \
     --parameter-overrides AllocateElasticIp=true <your other overrides>
   ```
   This is an additive update (the instance is not replaced), but the
   public IP CHANGES to the new Elastic IP — read it from the stack's
   `PublicIp` output. Pass every parameter override you deployed with
   originally (e.g. `UiPublicMode`), or defaults reassert themselves.
2. **Point DNS at it.** An `A` record for the apex (and `www` if
   wanted) → the Elastic IP, at the human's registrar or Route 53.
   TTL 300 is fine.
3. **Put Caddy in front** (on the instance, via SSM). Caddy provisions
   and renews Let's Encrypt certificates automatically; port 443 is
   already open in the security group. The one subtlety: the default
   deployment redirects port 80 to the app with an iptables rule, and
   Caddy needs to OWN 80/443 — disable the redirect and clear its rule:
   ```bash
   apt-get install -y caddy
   systemctl disable --now ui-port-redirect.service
   while read -r rule; do iptables -t nat $(echo "$rule" | sed 's/^-A/-D/'); done \
     < <(iptables -t nat -S PREROUTING | grep -- '--dport 80' || true)
   cat > /etc/caddy/Caddyfile <<'EOF'
   <the.domain>, www.<the.domain> {
       reverse_proxy 127.0.0.1:3000
   }
   http:// {
       redir https://<the.domain>{uri} permanent
   }
   EOF
   systemctl enable --now caddy && systemctl restart caddy
   ```
   The `http://` catch-all bounces old bare-IP links to the real
   address. (apt's needrestart may bounce agent services during the
   install — gate it like any engine update: HALT both agents, wait
   for open sessions to close, install, un-HALT.)
4. **Verify from outside:** the domain resolves to the Elastic IP;
   `https://` serves 200 with a valid certificate; `http://` redirects;
   the app's auth behavior is unchanged (Basic Auth sits behind the
   proxy untouched). Certificate renewal is Caddy's job forever.

Removal note: the Elastic IP is a stack resource (deletes with the
stack); the DNS records and Caddy die with the zone and instance
respectively — nothing here outlives the removal protocol except the
domain registration itself, which belongs to the human.

## Backups (automatic — the mind survives its hardware)

Nightly at 00:00 UTC, the whole of both agents' worlds — workspaces
with their git evolution history, journals, memory, Claude session
state, transcripts, logs, the built UI, plus consistent SQLite
snapshots — lands in the stack's private S3 bucket on a self-expiring
7-day window; secrets never ride along. **BACKUPS.md** is the full
reference: what's included and excluded, forcing a backup before risky
changes, and the complete restore-onto-a-fresh-stack procedure.

```bash
aws s3 ls s3://<BackupBucketName>/backups/          # what exists
run '/opt/alpaca-mind/backup.sh'                    # force one now
```

## Upgrades

- **Engine/UI-scaffold updates from the repo:** redeploying the stack
  replaces the instance (new AMI resolution) — force a backup first
  and restore after (BACKUPS.md). In-place engine updates, gated by
  the kill switches so no session can start underneath you: touch
  `/srv/mind/workspace/state/HALT` and `/srv/ui/workspace/state/HALT`;
  wait until both ledgers show no session without an end time; then
  `git -C /opt/alpaca-mind-src pull && cp -r
  /opt/alpaca-mind-src/engine /opt/alpaca-mind/ && systemctl restart
  mind-supervisor mind-sentinel ui-supervisor`; remove both HALT
  files; confirm the next wakes are intact.
- **Claude CLI:** pinned via the stack parameter; upgrade deliberately
  (install the new version as each user, HALT-gated as above), never
  automatically. **A CLI upgrade is a model upgrade**: the engine names
  models by alias (`fable`, `opus`, `sonnet`), and aliases resolve inside
  the CLI — a new pin can move the mind onto a newer model of the same
  tier. So treat the pin as the version control for the mind's brain:
  upgrade at a clean session boundary, run a one-turn canary as the
  agent user (`claude -p --model fable --max-turns 1 --output-format
  stream-json --verbose "ok"` — the `init` event's `model` field is the
  truth), confirm the workspace is still trusted (`hasTrustDialogAccepted`
  in the user's `~/.claude.json`), update the saved pin in
  `/etc/default/alpaca-mind-setup`, and tell the agent as a world fact
  through its owner-note channel. Every session's `model_resolved` event
  in the ledger records which model actually answered.
