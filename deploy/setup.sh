#!/usr/bin/env bash
# =============================================================================
# alpaca-mind host setup
# =============================================================================
#
# Runs as root on a fresh Ubuntu 24.04 instance, invoked by the CloudFormation
# user-data after the repository has been cloned to /opt/alpaca-mind-src.
#
# Layout it produces:
#
#   /opt/alpaca-mind          engine + venv + launcher, root-owned ("the law":
#                             agents execute it but can never modify it)
#   /srv/mind                 the trading agent: workspace/, ledger.db, logs/
#   /srv/ui                   the UI-manager agent: workspace/, app/ (Next.js)
#
# Idempotency contract: safe to re-run at any time. Infrastructure (packages,
# engine copy, units, .env files) is refreshed on every run; agent state
# (workspaces, ledger, UI app + its data) is seeded ONCE and never
# overwritten — the workspace is the agent's evolving mind, and clobbering it
# would lobotomize the agent.
#
# Expected environment (all have safe defaults):
#   SRC_DIR             where the repo was cloned      (/opt/alpaca-mind-src)
#   SSM_PREFIX          SSM Parameter Store prefix     (/alpaca-mind)
#   CLAUDE_CLI_VERSION  pinned Claude Code CLI version (see cloudformation.yaml)
#   UI_PORT             public UI port                 (80)
#   AWS_REGION          region for SSM reads           (auto-detected if unset)
# =============================================================================

set -euo pipefail

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

# Re-runs remember the stack's original parameters: user-data passes
# them on first boot, a hand re-run usually doesn't — and a re-run that
# silently falls back to defaults points at the wrong SSM prefix.
# Explicit environment still wins over the remembered values.
SETUP_RERUN=0
if [ -f /etc/default/alpaca-mind-setup ]; then
  # shellcheck disable=SC1091
  . /etc/default/alpaca-mind-setup
  SETUP_RERUN=1
fi

SRC_DIR="${SRC_DIR:-/opt/alpaca-mind-src}"
ENGINE_HOME=/opt/alpaca-mind
SSM_PREFIX="${SSM_PREFIX:-${SAVED_SSM_PREFIX:-/alpaca-mind}}"
CLAUDE_CLI_VERSION="${CLAUDE_CLI_VERSION:-${SAVED_CLAUDE_CLI_VERSION:-2.1.238}}"
UI_PORT="${UI_PORT:-${SAVED_UI_PORT:-80}}"
BACKUP_BUCKET="${BACKUP_BUCKET:-${SAVED_BACKUP_BUCKET:-}}"
UI_PUBLIC="${UI_PUBLIC:-${SAVED_UI_PUBLIC:-false}}"
UI_APP_PORT=3000   # unprivileged port the Next.js server binds; UI_PORT is redirected to it

log() { echo "[alpaca-mind setup] $*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "setup.sh must run as root" >&2
  exit 1
fi

if [ ! -d "$SRC_DIR" ]; then
  echo "source checkout not found at $SRC_DIR" >&2
  exit 1
fi

# Region: prefer the environment (user-data passes it), fall back to IMDSv2.
if [ -z "${AWS_REGION:-}" ] && [ -n "${SAVED_AWS_REGION:-}" ]; then
  AWS_REGION="$SAVED_AWS_REGION"
fi
if [ -z "${AWS_REGION:-}" ]; then
  IMDS_TOKEN="$(curl -fsS -X PUT http://169.254.169.254/latest/api/token \
    -H 'X-aws-ec2-metadata-token-ttl-seconds: 300')"
  AWS_REGION="$(curl -fsS -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" \
    http://169.254.169.254/latest/meta-data/placement/region)"
fi
export AWS_REGION AWS_DEFAULT_REGION="$AWS_REGION"

# ----------------------------------------------------------------------------
# 1. Base packages: Python venv tooling, sqlite, build tools, Node 20, AWS
#    CLI v2, and uv (which provides uvx for launching MCP servers).
# ----------------------------------------------------------------------------

log "installing base packages"
export DEBIAN_FRONTEND=noninteractive
# Lock timeout: waits out unattended-upgrades instead of failing on the dpkg lock.
APT="apt-get -o DPkg::Lock::Timeout=600"
$APT update
$APT install -y \
  python3-venv python3-pip \
  sqlite3 \
  curl jq unzip \
  build-essential \
  acl \
  git

# Node 20 via NodeSource (Ubuntu's archive ships an older Node). The check
# keeps re-runs from re-adding the apt source needlessly.
if ! command -v node >/dev/null 2>&1 || [ "$(node -v | cut -d. -f1)" != "v20" ]; then
  log "installing Node.js 20"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  $APT install -y nodejs
fi

# AWS CLI v2 (needed for SSM parameter reads; not preinstalled on Ubuntu).
if ! command -v aws >/dev/null 2>&1; then
  log "installing AWS CLI v2"
  ARCH="$(uname -m)"   # aarch64 on Graviton, x86_64 elsewhere
  TMP="$(mktemp -d)"
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${ARCH}.zip" -o "$TMP/awscliv2.zip"
  unzip -q "$TMP/awscliv2.zip" -d "$TMP"
  "$TMP/aws/install" --update
  rm -rf "$TMP"
fi

# uv installed system-wide so `uvx` is on every user's PATH — the trading
# agent's sessions mount MCP servers via `uvx` (e.g. `uvx alpaca-mcp-server`).
if ! command -v uv >/dev/null 2>&1; then
  log "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi

# ----------------------------------------------------------------------------
# 2. Agent users. Two isolated unix identities: `mind` (the trader) and `ui`
#    (the UI manager). System users with real homes and shells — the engine
#    launches interactive-grade agent sessions under each.
# ----------------------------------------------------------------------------

for u in mind ui; do
  if ! id "$u" >/dev/null 2>&1; then
    log "creating user $u"
    useradd --system --create-home --home-dir "/srv/$u" --shell /bin/bash "$u"
  fi
done

# ----------------------------------------------------------------------------
# 3. Engine. Copied out of the source checkout into a root-owned home with a
#    root-owned venv. Agents can read and execute it but never write it: the
#    engine is law, the workspaces are the agents' minds. Refreshed on every
#    run so re-running setup after a repo update deploys the new engine.
# ----------------------------------------------------------------------------

log "installing engine to $ENGINE_HOME"
mkdir -p "$ENGINE_HOME"
rm -rf "$ENGINE_HOME/engine"
cp -a "$SRC_DIR/engine" "$ENGINE_HOME/engine"

if [ ! -x "$ENGINE_HOME/venv/bin/python" ]; then
  python3 -m venv "$ENGINE_HOME/venv"
fi
"$ENGINE_HOME/venv/bin/pip" install --quiet --upgrade pip
"$ENGINE_HOME/venv/bin/pip" install --quiet pyyaml

# UI launcher script (used by ui-web.service; see that unit for rationale).
install -D -m 755 "$SRC_DIR/deploy/ui-web-launch.sh" "$ENGINE_HOME/bin/ui-web-launch.sh"

# World read+execute, root-only write.
chown -R root:root "$ENGINE_HOME"
chmod -R a+rX,go-w "$ENGINE_HOME"

# ----------------------------------------------------------------------------
# 4. Claude Code CLI for BOTH agent users, pinned to CLAUDE_CLI_VERSION.
#    Per-user installs land in ~/.local/bin; each user gets PATH wiring in
#    ~/.profile, and the systemd units export the same PATH for daemons.
# ----------------------------------------------------------------------------

install_claude_for() {
  local u="$1"
  local bin="/srv/$u/.local/bin/claude"
  local have=""
  if [ -x "$bin" ]; then
    have="$(sudo -u "$u" -H "$bin" --version 2>/dev/null || true)"
  fi
  case "$have" in
    *"$CLAUDE_CLI_VERSION"*)
      log "claude $CLAUDE_CLI_VERSION already installed for $u"
      ;;
    *)
      log "installing claude $CLAUDE_CLI_VERSION for $u"
      sudo -u "$u" -H env CLAUDE_CLI_VERSION="$CLAUDE_CLI_VERSION" bash -c \
        'curl -fsSL https://claude.ai/install.sh | bash -s "$CLAUDE_CLI_VERSION"'
      ;;
  esac
  # PATH wiring for interactive shells (SSM sessions, agent subshells).
  if ! sudo -u "$u" -H grep -qs '/.local/bin' "/srv/$u/.profile" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "/srv/$u/.profile"
    chown "$u:$u" "/srv/$u/.profile"
  fi
}

install_claude_for mind
install_claude_for ui

# ----------------------------------------------------------------------------
# 5. uvx for the `mind` user: nothing further to do — uv/uvx were installed
#    system-wide in /usr/local/bin above, so `uvx alpaca-mcp-server` resolves
#    for the trading agent's sessions with no per-user install.
# ----------------------------------------------------------------------------

command -v uvx >/dev/null || { echo "uvx missing after uv install" >&2; exit 1; }

# ----------------------------------------------------------------------------
# 6. Workspaces — seeded ONCE from the repo's mission seeds, then owned
#    forever by the agents. A workspace is an evolving mind: re-running setup
#    must NEVER overwrite one that exists. Each is a local git repo so the
#    agent (and the audit trail) can track its own changes; identities are
#    local, machine-only names.
# ----------------------------------------------------------------------------

seed_workspace() {
  local u="$1" seed="$2" ws="/srv/$1/workspace"
  if [ -d "$ws" ]; then
    log "workspace $ws exists — leaving it untouched"
    return
  fi
  log "seeding $ws from $seed"
  cp -a "$seed" "$ws"
  chown -R "$u:$u" "$ws"
  chmod 700 "$ws"   # a mind is private; cross-access is granted explicitly below
  sudo -u "$u" -H git -C "$ws" init -q
  sudo -u "$u" -H git -C "$ws" config user.name "$u"
  sudo -u "$u" -H git -C "$ws" config user.email "$u@localhost"
  sudo -u "$u" -H git -C "$ws" add -A
  sudo -u "$u" -H git -C "$ws" commit -q --allow-empty -m "genesis"
}

seed_workspace mind "$SRC_DIR/mission"
seed_workspace ui "$SRC_DIR/ui-mission"

# Pre-trust each workspace for the Claude CLI. Headless sessions can't
# click a trust dialog, and an untrusted workspace silently ignores the
# permission rules in .claude/settings.json — the deny rules there are
# law and must load.
for u in mind ui; do
  sudo -u "$u" -H python3 - "/srv/$u/.claude.json" "/srv/$u/workspace" <<'PY'
import json, sys
path, ws = sys.argv[1], sys.argv[2]
try:
    with open(path) as f:
        data = json.load(f)
except (OSError, ValueError):
    data = {}
data.setdefault("projects", {}).setdefault(ws, {})["hasTrustDialogAccepted"] = True
with open(path, "w") as f:
    json.dump(data, f, indent=2)
PY
done

# The trader's LAB: its own interpreter, its own packages — the mission
# grants it a python it may extend with pip. Seeded once with a starter
# stack; from then on the agent owns it.
if [ ! -x /srv/mind/lab/bin/python3 ]; then
  log "creating trader lab venv"
  sudo -u mind -H python3 -m venv /srv/mind/lab
  sudo -u mind -H /srv/mind/lab/bin/pip install --quiet --upgrade pip
  sudo -u mind -H /srv/mind/lab/bin/pip install --quiet numpy pandas requests
fi

# ----------------------------------------------------------------------------
# 7. UI app — seeded ONCE, like a workspace: after first deploy the UI agent
#    owns the app (it edits code and runs its own `npm run build`), so setup
#    must not clobber it on re-runs. First build happens here so the site is
#    up before the agent's first session.
# ----------------------------------------------------------------------------

if [ ! -d /srv/ui/app ]; then
  log "seeding UI app"
  cp -a "$SRC_DIR/ui" /srv/ui/app
  chown -R ui:ui /srv/ui/app
fi

# Runtime data lives inside the app tree so the UI agent and web server share it.
install -d -o ui -g ui -m 750 /srv/ui/app/data

if [ ! -d /srv/ui/app/.next ]; then
  log "installing UI dependencies and building"
  sudo -u ui -H bash -c '
    set -euo pipefail
    cd /srv/ui/app
    if [ -f package-lock.json ]; then npm ci; else npm install; fi
    npm run build
  '
fi

# ----------------------------------------------------------------------------
# 8. Secrets → .env files. Read the SecureString parameters placed under
#    SSM_PREFIX before stack creation and materialize them as owner-only env
#    files. The repo and the stack never contain a secret; these files are
#    the only place secrets exist on disk, mode 600.
# ----------------------------------------------------------------------------

get_param() {
  aws ssm get-parameter \
    --name "${SSM_PREFIX}/$1" \
    --with-decryption \
    --query Parameter.Value \
    --output text
}

log "materializing .env files from SSM prefix $SSM_PREFIX"
ALPACA_API_KEY="$(get_param ALPACA_API_KEY)"
ALPACA_SECRET_KEY="$(get_param ALPACA_SECRET_KEY)"
ALPACA_PAPER="$(get_param ALPACA_PAPER)"
CLAUDE_CODE_OAUTH_TOKEN="$(get_param CLAUDE_CODE_OAUTH_TOKEN)"
UI_PASSWORD="$(get_param UI_PASSWORD)"

# install -m 600 creates (or truncates) the file with tight permissions BEFORE
# any secret is written into it, so there is no readable window.
install -o mind -g mind -m 600 /dev/null /srv/mind/.env
cat > /srv/mind/.env <<EOF
ALPACA_API_KEY=${ALPACA_API_KEY}
ALPACA_SECRET_KEY=${ALPACA_SECRET_KEY}
ALPACA_PAPER=${ALPACA_PAPER}
CLAUDE_CODE_OAUTH_TOKEN=${CLAUDE_CODE_OAUTH_TOKEN}
LEDGER_PATH=/srv/mind/ledger.db
MIND_CONFIG=${ENGINE_HOME}/engine/config/mind.yaml
EOF

install -o ui -g ui -m 600 /dev/null /srv/ui/.env
cat > /srv/ui/.env <<EOF
UI_PASSWORD=${UI_PASSWORD}
ALPACA_API_KEY=${ALPACA_API_KEY}
ALPACA_SECRET_KEY=${ALPACA_SECRET_KEY}
ALPACA_PAPER=${ALPACA_PAPER}
CLAUDE_CODE_OAUTH_TOKEN=${CLAUDE_CODE_OAUTH_TOKEN}
LEDGER_PATH=/srv/mind/ledger.db
UI_DB_PATH=/srv/ui/app/data/ui.db
UI_RUN_REQUEST_PATH=/srv/ui/app/data/run_request.json
MIND_LOGS_DIR=/srv/mind/logs
UI_LOGS_DIR=/srv/ui/logs
UI_PUBLIC=${UI_PUBLIC}
EOF

unset ALPACA_API_KEY ALPACA_SECRET_KEY CLAUDE_CODE_OAUTH_TOKEN UI_PASSWORD

# ----------------------------------------------------------------------------
# 9. Read-only cross-access. The UI reads the trader's ledger and session
#    logs but must never write them. Mechanism:
#      - group `ledger-readers` (ui is a member) may traverse /srv/mind
#      - ledger.db is group-readable (640, group ledger-readers)
#      - a default ACL on /srv/mind keeps files the trader creates there
#        (ledger sidecar files like -wal/-shm included) group-readable
#      - /srv/mind/logs is group-readable recursively, with a default ACL so
#        new transcripts inherit readability
#    The .env file stays private because its explicit 600 mode caps the ACL
#    mask — group access to it is nil regardless of the default ACL.
#    The workspace stays private because its 700 dir mode blocks traversal.
# ----------------------------------------------------------------------------

log "configuring read-only cross-access"
groupadd -f ledger-readers
usermod -aG ledger-readers ui

chown mind:ledger-readers /srv/mind
chmod 750 /srv/mind
setfacl -d -m "g:ledger-readers:r" /srv/mind

# The ledger: create empty if absent (an empty file is a valid new SQLite
# database) so permissions are right before the engine first opens it.
if [ ! -f /srv/mind/ledger.db ]; then
  install -o mind -g ledger-readers -m 640 /dev/null /srv/mind/ledger.db
else
  chgrp ledger-readers /srv/mind/ledger.db
  chmod 640 /srv/mind/ledger.db
fi

# Session logs: setgid so new files keep the group; default ACL so they are
# born group-readable.
install -d -o mind -g ledger-readers -m 2750 /srv/mind/logs
install -d -o mind -g ledger-readers -m 2750 /srv/mind/logs/daily
setfacl -R -m "g:ledger-readers:rX" /srv/mind/logs
setfacl -R -d -m "g:ledger-readers:rX" /srv/mind/logs

# The UI side keeps the same structured daily logs (web server and
# UI-manager supervisor both write there as the ui user).
install -d -o ui -g ui -m 750 /srv/ui/logs /srv/ui/logs/daily

# The trader's execution hand: `trade` on its PATH. The wrapper is a
# convenience pointer; the law it invokes stays root-owned under
# /opt/alpaca-mind. It defaults MIND_CONFIG so the hand works in any
# shell the mind opens, not only under the service environment.
install -d -o mind -g mind -m 755 /srv/mind/.local/bin
cat > /srv/mind/.local/bin/trade <<EOF
#!/bin/sh
export MIND_CONFIG="\${MIND_CONFIG:-${ENGINE_HOME}/engine/config/mind.yaml}"
exec ${ENGINE_HOME}/venv/bin/python ${ENGINE_HOME}/engine/trade.py "\$@"
EOF
chown mind:mind /srv/mind/.local/bin/trade
chmod 755 /srv/mind/.local/bin/trade

# ----------------------------------------------------------------------------
# 10. Engine configuration — root-owned copies from the source checkout so a
#     compromised or confused agent cannot rewrite its own operating rules.
# ----------------------------------------------------------------------------

install -d -m 755 "$ENGINE_HOME/engine/config"
for cfg in mind.yaml ui.yaml; do
  # Configs live at the repo root's config/. install fails loudly if a
  # source is missing — a silently absent config becomes three services
  # crash-looping with nothing to say for themselves.
  install -m 644 "$SRC_DIR/config/$cfg" "$ENGINE_HOME/engine/config/$cfg"
done

# ----------------------------------------------------------------------------
# 11. systemd units, installed from the repo's real unit files (deploy/units)
#     rather than heredocs, so what runs is exactly what is reviewed in
#     version control.
#
#     ui-restart.path + ui-restart.service: the ui user cannot restart
#     services itself, so the UI agent asks for a restart by creating
#     /srv/ui/app/data/restart_request.json. A root-owned path unit notices
#     the file, removes it, and bounces ui-web. No rebuild happens here — the
#     UI agent runs its own `npm run build` before requesting the restart.
# ----------------------------------------------------------------------------

log "installing systemd units"
for unit in "$SRC_DIR"/deploy/units/*.service "$SRC_DIR"/deploy/units/*.path \
            "$SRC_DIR"/deploy/units/*.timer; do
  install -m 644 "$unit" "/etc/systemd/system/$(basename "$unit")"
done

# Nightly S3 backup: root-owned script + config from the stack's values.
# No BACKUP_BUCKET (an older stack) means the script no-ops harmlessly.
install -m 750 "$SRC_DIR/deploy/backup.sh" "$ENGINE_HOME/backup.sh"
cat > /etc/default/alpaca-mind-backup <<EOF
BACKUP_BUCKET=${BACKUP_BUCKET:-}
AWS_REGION=${AWS_REGION:-}
EOF
chmod 600 /etc/default/alpaca-mind-backup

# The port-redirect unit reads its ports from this file (see step 12).
cat > /etc/default/alpaca-mind-redirect <<EOF
UI_PORT=${UI_PORT}
APP_PORT=${UI_APP_PORT}
EOF
chmod 644 /etc/default/alpaca-mind-redirect

systemctl daemon-reload

systemctl enable --now mind-supervisor.service
systemctl enable --now mind-sentinel.service
systemctl enable --now ui-supervisor.service
systemctl enable --now ui-web.service
systemctl enable --now ui-restart.path
systemctl enable --now mind-backup.timer

# Re-runs may have changed engine code, config, or .env contents; restart
# the daemons so they pick the changes up. On FIRST boot the enable above
# just started everything — an immediate restart here would kill a freshly
# launched genesis session and orphan its ledger row.
if [ "$SETUP_RERUN" = 1 ]; then
  systemctl restart mind-supervisor.service mind-sentinel.service ui-supervisor.service ui-web.service
fi

# ----------------------------------------------------------------------------
# 12. Public port → app port redirect. The Next.js server binds an
#     unprivileged port; iptables redirects the public UI port to it. Chosen
#     over granting the node binary CAP_NET_BIND_SERVICE because a file
#     capability would (a) apply to every node process on the host and
#     (b) silently vanish whenever the node binary is upgraded. The rule is
#     (re)applied at boot by a oneshot unit, so no iptables-persistence
#     package is needed.
# ----------------------------------------------------------------------------

if [ "$UI_PORT" != "$UI_APP_PORT" ]; then
  log "enabling port redirect ${UI_PORT} -> ${UI_APP_PORT}"
  systemctl enable --now ui-port-redirect.service
else
  systemctl disable --now ui-port-redirect.service 2>/dev/null || true
fi

# ----------------------------------------------------------------------------
# 13. Completion banner.
# ----------------------------------------------------------------------------

IMDS_TOKEN="$(curl -fsS -X PUT http://169.254.169.254/latest/api/token \
  -H 'X-aws-ec2-metadata-token-ttl-seconds: 300' || true)"
PUBLIC_IP="$(curl -fsS -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" \
  http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo '<no public ip>')"

if [ "$UI_PORT" = "80" ]; then
  UI_URL="http://${PUBLIC_IP}/"
else
  UI_URL="http://${PUBLIC_IP}:${UI_PORT}/"
fi

# Remember this run's parameters for future hand re-runs.
cat > /etc/default/alpaca-mind-setup <<EOF
SAVED_SSM_PREFIX=${SSM_PREFIX}
SAVED_CLAUDE_CLI_VERSION=${CLAUDE_CLI_VERSION}
SAVED_UI_PORT=${UI_PORT}
SAVED_AWS_REGION=${AWS_REGION}
SAVED_BACKUP_BUCKET=${BACKUP_BUCKET}
SAVED_UI_PUBLIC=${UI_PUBLIC}
EOF
chmod 644 /etc/default/alpaca-mind-setup

log "============================================================"
log " alpaca-mind setup complete"
log "   public ip : ${PUBLIC_IP}"
log "   ui url    : ${UI_URL}"
log "   services  : mind-supervisor mind-sentinel ui-supervisor ui-web"
log "   shell     : aws ssm start-session --target <instance-id>"
log "============================================================"
