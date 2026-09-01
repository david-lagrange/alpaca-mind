#!/usr/bin/env bash
# =============================================================================
# alpaca-mind UI launcher (ExecStart target of ui-web.service).
#
# Next.js `output: "standalone"` emits a self-contained server at
# .next/standalone/server.js, but by design it does NOT include the static
# assets: .next/static and public/ must sit alongside the server.
#
# The server NEVER runs from the build output directly. `npm run build`
# rewrites .next/ in place, and a live server reading files a build is
# rewriting serves module-not-found errors mid-build. So every start
# snapshots the bundle to a serve directory the build never touches:
# "rebuild then restart" stays the whole redeploy story for the UI agent,
# and a build in progress can wobble nothing.
#
# Fallback: if no standalone bundle exists (e.g. the build config changed),
# serve with `next start` so the site stays up either way.
# =============================================================================
set -euo pipefail

APP=/srv/ui/app
STANDALONE="$APP/.next/standalone"
SERVE=/srv/ui/serve

if [ -f "$STANDALONE/server.js" ]; then
  rm -rf "$SERVE"
  mkdir -p "$SERVE"
  cp -a "$STANDALONE/." "$SERVE/"
  # Static assets beside the snapshot's server, per standalone layout.
  rm -rf "$SERVE/.next/static"
  mkdir -p "$SERVE/.next"
  cp -a "$APP/.next/static" "$SERVE/.next/static"
  if [ -d "$APP/public" ]; then
    rm -rf "$SERVE/public"
    cp -a "$APP/public" "$SERVE/public"
  fi
  cd "$SERVE"
  # PORT and HOSTNAME come from the service environment.
  exec node server.js
else
  cd "$APP"
  exec node node_modules/.bin/next start --port "${PORT:-3000}" --hostname "${HOSTNAME:-0.0.0.0}"
fi
