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
4. `journalctl -u mind-supervisor -n 20` → `launch` lines pair with
   `session done exit=0`.

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

## Logs — the system's nervous system

Every component writes structured JSONL, split by UTC day, alongside
its human-readable journald stream:

- **Mind side:** `/srv/mind/logs/daily/YYYY-MM-DD.jsonl` — components
  `supervisor`, `sentinel`, `scanners`, `trade`, `venue`, `ledger`.
- **UI side:** `/srv/ui/logs/daily/YYYY-MM-DD.jsonl` — components
  `supervisor` (the UI manager's engine) and `web` (the Next.js app).

Each record: `ts`, `level` (`debug|info|warn|error`), `component`,
`event` (snake_case), plus key-values — errors carry `error` and
`trace`, and trade activity carries `session_id` so a line correlates
to the agent session that caused it. The **Logs page in the UI**
(Mind / UI tabs) renders both streams with filters and a live tail —
start there. From a shell, `jq` over the daily file answers anything:

```bash
run "jq -r 'select(.level==\"error\")' /srv/mind/logs/daily/$(date -u +%F).jsonl"
```

`LOG_LEVEL` (env, default `info`) filters only the journald stream;
the daily files always receive every level, debug included — the
record that explains a failure is usually written before anyone knows
a failure is coming.

**The logs cannot fill the disk — by construction.** Three
self-enforcing bounds (env-overridable): a per-day file cap
(`JSONLOG_MAX_FILE_MB`, 64 — a runaway loop hits the ceiling, one
`log_file_capped` marker is written, the rest of that day's records
drop from the file while journald keeps flowing), a total-directory
cap (`JSONLOG_MAX_TOTAL_MB`, 512 — oldest days deleted first), and
retention (`JSONLOG_KEEP_DAYS`, 7). Retention and the directory cap
enforce themselves on day rollover inside every writer, so no
housekeeping job is a single point of disk-safety failure. journald
(`journalctl -u <unit>`) remains the operator's low-level view — it
has its own systemd size caps — and survives even a broken file sink.

## Diagnostic patterns

| Symptom | Look at |
|---|---|
| No sessions for hours | `status.json` (halt? next_wake far out?); `journalctl -u mind-supervisor` — a `BACKSTOP` or `SCHEDULE GUARD` line explains itself; `heartbeat_alarm` events in the ledger |
| A session failed | `journalctl -u mind-supervisor -n 40` → the `session done` line's subtype; then read the transcript tail |
| Trigger never fired | `trade events --minutes 120` (as the mind user, env as above) — `trigger_unevaluable` / `trigger_symbol_no_data` events name the cause; the sentinel journal shows quote polling |
| UI stale | `journalctl -u ui-supervisor -n 20` (is it waking?); `journalctl -u ui-web -n 20`; the UI manager never restarts onto a broken build — check its last session transcript in `/srv/ui/logs/sessions/` |
| UI down | `systemctl status ui-web`; rebuild by hand as a last resort: `sudo -u ui bash -lc 'cd /srv/ui/app && npm run build' && systemctl restart ui-web` |
| Anything weird after an instance reboot | services are `Restart=always` and enabled — `systemctl` the four units; state survives on disk |

## Backups (automatic, nightly, rolling 7 days)

Every night at midnight UTC, `mind-backup.timer` archives both agents'
entire worlds — workspaces with their full git evolution history,
journals, memory, Claude session state, transcripts and prompt
snapshots, daily logs, the built UI app — plus consistent SQLite
snapshots of every database, into the stack's private S3 bucket
(`BackupBucketName` output). The bucket's lifecycle rule expires
objects after 7 days, so the window rolls itself and the cost stays at
pennies. Secrets are deliberately absent from every archive (.env and
credential caches are excluded — SSM is their home).

```bash
aws s3 ls s3://<BackupBucketName>/backups/          # what exists
run 'systemctl status mind-backup; journalctl -u mind-backup -n 10'
run '/opt/alpaca-mind/backup.sh'                    # force one now
```

**Restore onto a fresh stack** (new instance, same or new stack name):
1. Deploy the stack; wait for setup to finish; then stop the agents:
   `run 'systemctl stop mind-supervisor mind-sentinel ui-supervisor ui-web'`
2. Pull and unpack the chosen archive over the seeded state:
   ```bash
   run 'aws s3 cp s3://<bucket>/backups/<file>.tar.gz /tmp/b.tar.gz && \
        tar xzf /tmp/b.tar.gz -C / srv/mind srv/ui && \
        tar xzf /tmp/b.tar.gz -C /tmp db-snapshots'
   ```
3. Put the consistent databases back and fix ownership:
   ```bash
   run 'cp /tmp/db-snapshots/mind-ledger.db /srv/mind/ledger.db; \
        cp /tmp/db-snapshots/ui-ledger.db /srv/ui/ledger.db 2>/dev/null; \
        cp /tmp/db-snapshots/ui-app.db /srv/ui/app/data/ui.db 2>/dev/null; \
        chown -R mind:mind /srv/mind; chown -R ui:ui /srv/ui; \
        chgrp ledger-readers /srv/mind /srv/mind/ledger.db'
   ```
4. Rebuild the rebuildables, then start:
   ```bash
   run 'sudo -u ui bash -lc "cd /srv/ui/app && npm ci && npm run build"; \
        systemctl start mind-supervisor mind-sentinel ui-supervisor ui-web'
   ```
   (The mind's lab venv recreates itself as the agent needs it;
   `db-snapshots/lab-requirements.txt` lists what it had installed.)

The manual **brain export** remains available anytime (also step one of
the removal protocol):

```bash
run 'tar czf /tmp/mind-brain.tar.gz -C /srv/mind workspace ledger.db logs'
```

## Upgrades

- **Engine/UI-scaffold updates from the repo:** redeploying the stack
  replaces the instance (new AMI resolution) — export the brain first,
  restore after. In-place engine updates: `git -C /opt/alpaca-mind-src
  pull && cp -r /opt/alpaca-mind-src/engine /opt/alpaca-mind/ &&
  systemctl restart mind-supervisor mind-sentinel ui-supervisor` —
  between sessions, never during one (check `journalctl` for a
  `launch` without a `session done` first).
- **Claude CLI:** pinned via the stack parameter; upgrade deliberately
  (install the new version as each user, between sessions), never
  automatically.
