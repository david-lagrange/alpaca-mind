#!/usr/bin/env bash
# =============================================================================
# Nightly backup: archive both agents' entire worlds to the stack's private
# S3 bucket. An instance is replaceable hardware; an evolved mind is not —
# workspace doctrine, journals, memory, Claude session state, the ledger,
# and the built UI all ride in one dated tarball. The bucket's lifecycle
# rule keeps a rolling window, so this script only ever adds.
#
# Included: /srv/mind and /srv/ui wholesale — which covers each agent's
#   workspace (its git history IS the evolution record), journals, memory,
#   scanners, state, session transcripts + prompt snapshots, daily logs,
#   the agents' ~/.claude state (their homes are these directories), and
#   the built UI app source.
# Excluded (rebuildable or secret):
#   - virtualenvs, node_modules, .next build output, caches, __pycache__
#   - .env files and any Claude credential cache — secrets never leave the
#     box; SSM is their home and a restore re-materializes them
#   - live SQLite files, which are replaced by CONSISTENT snapshots taken
#     via the sqlite backup API (a raw copy of a database mid-write can be
#     corrupt precisely on the night it matters)
#
# Config: /etc/default/alpaca-mind-backup (BACKUP_BUCKET, AWS_REGION),
# written by setup.sh from the stack's values. Runs as root from
# mind-backup.timer; output goes to journald. Exits nonzero on any failure
# so `systemctl status mind-backup` tells the truth.
# =============================================================================
set -euo pipefail

# The config file supplies defaults; explicit environment wins.
ENV_BUCKET="${BACKUP_BUCKET:-}"
ENV_REGION="${AWS_REGION:-}"
[ -f /etc/default/alpaca-mind-backup ] && . /etc/default/alpaca-mind-backup
BACKUP_BUCKET="${ENV_BUCKET:-${BACKUP_BUCKET:-}}"
AWS_REGION="${ENV_REGION:-${AWS_REGION:-}}"
if [ -z "${BACKUP_BUCKET:-}" ]; then
  echo "no BACKUP_BUCKET configured — backups disabled on this deployment"
  exit 0
fi
export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}"

STAMP="$(date -u +%F)"
STAGE="$(mktemp -d /tmp/mind-backup.XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT

# Consistent snapshots of every live database, via the sqlite backup API.
mkdir -p "$STAGE/db-snapshots"
snap_db() {
  local src="$1" dst="$STAGE/db-snapshots/$2"
  [ -f "$src" ] || return 0
  python3 - "$src" "$dst" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
a = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
b = sqlite3.connect(dst)
with b:
    a.backup(b)
b.close(); a.close()
PY
  echo "db snapshot: $2"
}
snap_db /srv/mind/ledger.db      mind-ledger.db
snap_db /srv/ui/ledger.db        ui-ledger.db
snap_db /srv/ui/app/data/ui.db   ui-app.db

# The lab venv is excluded as rebuildable — but record what was in it, so
# a restore can recreate the agent's own toolbox.
if [ -x /srv/mind/lab/bin/pip ]; then
  /srv/mind/lab/bin/pip freeze > "$STAGE/db-snapshots/lab-requirements.txt" \
    2>/dev/null || true
fi

ARCHIVE="$STAGE/alpaca-mind-$STAMP.tar.gz"
tar -czf "$ARCHIVE" \
  --exclude='srv/mind/lab' \
  --exclude='srv/ui/app/node_modules' \
  --exclude='srv/ui/app/.next' \
  --exclude='*/__pycache__' \
  --exclude='*/.cache' \
  --exclude='*/.npm' \
  --exclude='srv/mind/.env' \
  --exclude='srv/ui/.env' \
  --exclude='*/.credentials.json' \
  --exclude='srv/mind/ledger.db*' \
  --exclude='srv/ui/ledger.db*' \
  --exclude='srv/ui/app/data/ui.db*' \
  -C / srv/mind srv/ui \
  -C "$STAGE" db-snapshots

SIZE="$(du -h "$ARCHIVE" | cut -f1)"
KEY="backups/alpaca-mind-$STAMP.tar.gz"
aws s3 cp --only-show-errors "$ARCHIVE" "s3://$BACKUP_BUCKET/$KEY"
echo "backup uploaded: s3://$BACKUP_BUCKET/$KEY ($SIZE)"

# Read-after-write: a backup that didn't verify didn't happen.
aws s3api head-object --bucket "$BACKUP_BUCKET" --key "$KEY" > /dev/null
echo "backup verified"
