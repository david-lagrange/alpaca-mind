#!/usr/bin/env bash
# =============================================================================
# Push the five deployment secrets from a local staging file into AWS SSM
# Parameter Store — without ever printing a value. The staging file exists
# so a human can provide secrets by editing a file instead of running
# terminal commands; this script is the only thing that reads it, and it
# deletes the file after a successful push (--keep to retain).
#
# Usage:
#   bash deploy/push-secrets.sh [--prefix /alpaca-mind] [--file secrets.env] [--keep]
#
# The prefix must match the SsmPrefix the stack is created with, and the
# AWS CLI's configured region must match where the stack will live.
# =============================================================================
set -euo pipefail

# Windows Git Bash rewrites leading-slash arguments into filesystem
# paths before a native executable sees them, which mangles SSM
# parameter names. These exclusions disable that conversion; they are
# inert everywhere else.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

PREFIX=/alpaca-mind
FILE=""
KEEP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2 ;;
    --file)   FILE="$2";   shift 2 ;;
    --keep)   KEEP=1;      shift   ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$FILE" ]; then
  for cand in secrets.env deploy/secrets.env; do
    [ -f "$cand" ] && FILE="$cand" && break
  done
fi
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "no secrets file found — copy deploy/secrets.env.example to" >&2
  echo "secrets.env, fill in the values, and run this again" >&2
  exit 1
fi

KEYS="ALPACA_API_KEY ALPACA_SECRET_KEY ALPACA_PAPER CLAUDE_CODE_OAUTH_TOKEN UI_PASSWORD"

# Last assignment wins; values are taken verbatim after the first `=`
# (no quoting rules for the human to get wrong).
getv() { sed -n "s/^$1=//p" "$FILE" | tail -1; }

ok=1
for k in $KEYS; do
  v="$(getv "$k")"
  case "$v" in
    "" ) echo "missing value: $k" >&2; ok=0 ;;
    \<*\> ) echo "placeholder not filled in: $k" >&2; ok=0 ;;
  esac
done
[ "$ok" = 1 ] || exit 1

for k in $KEYS; do
  aws ssm put-parameter --name "$PREFIX/$k" --type SecureString \
    --overwrite --value "$(getv "$k")" > /dev/null
  echo "pushed $PREFIX/$k"
done

# Optional sixth: the seat gauge — a browser login's credentials file
# (docs/DEPLOYMENT.md §2), pushed from the file so its contents never
# pass through a terminal or a chat.
GAUGE_FILE="$(getv GAUGE_CREDENTIALS_FILE)"
if [ -n "$GAUGE_FILE" ] && [ "${GAUGE_FILE#<}" = "$GAUGE_FILE" ]; then
  if [ -f "$GAUGE_FILE" ]; then
    aws ssm put-parameter --name "$PREFIX/GAUGE_CREDENTIALS" --type SecureString \
      --overwrite --value "file://$GAUGE_FILE" > /dev/null
    echo "pushed $PREFIX/GAUGE_CREDENTIALS (from $GAUGE_FILE)"
  else
    echo "GAUGE_CREDENTIALS_FILE names a file that does not exist: $GAUGE_FILE" >&2
    exit 1
  fi
fi

if [ "$KEEP" = 0 ]; then
  rm -f "$FILE"
  echo "deleted $FILE (staging only — SSM is the home of secrets now)"
fi
echo "all five parameters are in SSM under $PREFIX"
