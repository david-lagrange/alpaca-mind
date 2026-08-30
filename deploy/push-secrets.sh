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

if [ "$KEEP" = 0 ]; then
  rm -f "$FILE"
  echo "deleted $FILE (staging only — SSM is the home of secrets now)"
fi
echo "all five parameters are in SSM under $PREFIX"
