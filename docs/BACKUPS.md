# Backups — the mind survives its hardware

*Written for the AI assistant. An instance is replaceable; weeks of
evolved doctrine, journals, memory, and the built interface are not.
This is the protection, and the resurrection procedure.*

## What runs, automatically

Every night at **00:00 UTC**, `mind-backup.timer` (persistent — a
missed night catches up at boot) archives both agents' entire worlds
into the stack's private, encrypted S3 bucket (the `BackupBucketName`
stack output). The bucket's lifecycle rule expires objects after
**7 days**, so the rolling window maintains itself and the cost stays
at pennies.

**Included** — `/srv/mind` and `/srv/ui` wholesale, which covers: each
workspace with its full git history (the evolution record itself),
journals, memory, strategies, scanners, state, the agents' `~/.claude`
session and memory state (their homes are these directories), session
transcripts and prompt snapshots, daily logs, and the built UI app
source. Every SQLite database enters as a CONSISTENT snapshot taken
through the sqlite backup API (`db-snapshots/` inside the archive) —
a raw copy of a database mid-write can be corrupt precisely on the
night it matters. The mind's lab package list rides along as
`db-snapshots/lab-requirements.txt`.

**Excluded** — the rebuildable and the secret: virtualenvs,
`node_modules`, `.next` build output, caches, `__pycache__`; and
`.env` files plus any credential cache. Backups travel to S3; secrets
never do (SSM is their home — a restore re-materializes them).

Every upload is verified read-after-write: a backup that didn't verify
didn't happen, and the failure shows in `systemctl status mind-backup`.

## Operating it

```bash
aws s3 ls s3://<BackupBucketName>/backups/           # what exists
run 'systemctl status mind-backup; journalctl -u mind-backup -n 10'
run '/opt/alpaca-mind/backup.sh'                     # force one now
```

Force a manual backup before anything risky: a stack update, an
instance-type change, an engine upgrade.

## Restore onto a fresh stack (the resurrection)

1. Deploy the stack; wait for setup to finish; stop the agents:
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
   `lab-requirements.txt` lists what it had installed.)
5. Sanity: `run 'systemctl is-active mind-supervisor mind-sentinel ui-supervisor ui-web'`
   → four × `active`; the UI should show the mind's history intact.
   Then, as the mind user, `trade reconcile` — positions at the venue
   may have moved while the mind was down, and the reconciler heals
   the ledger against venue truth.

## The manual brain export

Available anytime (and offered as step one of the removal protocol):

```bash
run 'tar czf /tmp/mind-brain.tar.gz -C /srv/mind workspace ledger.db logs'
```

## Removal

S3 refuses to delete a non-empty bucket, so the removal protocol
empties it before deleting the stack (REMOVAL.md §4) — offer the human
a copy of the newest backup first; it is a complete restorable mind.
