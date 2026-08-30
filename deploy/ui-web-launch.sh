#!/usr/bin/env bash
# =============================================================================
# alpaca-mind UI launcher (ExecStart target of ui-web.service).
#
# Next.js `output: "standalone"` emits a self-contained server at
# .next/standalone/server.js, but by design it does NOT include the static
# assets: .next/static and public/ must sit alongside the server. Syncing
# them here, on every service start, means "rebuild then restart" is the
# whole redeploy story — the UI agent runs `npm run build` and drops a
# restart request; nothing else has to remember the asset step.
#
# Fallback: if no standalone bundle exists (e.g. the build config changed),
# serve with `next start` so the site stays up either way.
# =============================================================================
set -euo pipefail

APP=/srv/ui/app
STANDALONE="$APP/.next/standalone"

if [ -f "$STANDALONE/server.js" ]; then
  # Refresh static assets beside the standalone server.
  rm -rf "$STANDALONE/.next/static"
  mkdir -p "$STANDALONE/.next"
  cp -a "$APP/.next/static" "$STANDALONE/.next/static"
  if [ -d "$APP/public" ]; then
    rm -rf "$STANDALONE/public"
    cp -a "$APP/public" "$STANDALONE/public"
  fi
  cd "$STANDALONE"
  # PORT and HOSTNAME come from the service environment.
  exec node server.js
else
  cd "$APP"
  exec node node_modules/.bin/next start --port "${PORT:-3000}" --hostname "${HOSTNAME:-0.0.0.0}"
fi
