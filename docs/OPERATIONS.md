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

## The owner's controls

- **Kill switch (stop all trading):**
  `sudo -u mind touch /srv/mind/workspace/state/HALT`
  — sessions stop launching immediately; the sentinel keeps watching.
  Remove the file to resume. This is the owner's right, always.
- **The inbox** (in the UI): requests for what to SEE. It steers
  visibility, never trades.
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
  and restore after (BACKUPS.md). In-place engine updates: `git -C /opt/alpaca-mind-src
  pull && cp -r /opt/alpaca-mind-src/engine /opt/alpaca-mind/ &&
  systemctl restart mind-supervisor mind-sentinel ui-supervisor` —
  between sessions, never during one (check the log stream for a
  `session_launch` without a matching `session_finish` first).
- **Claude CLI:** pinned via the stack parameter; upgrade deliberately
  (install the new version as each user, between sessions), never
  automatically.
