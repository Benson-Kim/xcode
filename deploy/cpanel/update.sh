#!/bin/bash
# Installs the newest staging web build on the cPanel account. Runs from cron every few minutes:
#   */5 * * * * bash $HOME/xcode-web/update.sh >> $HOME/xcode-web/logs/update.log 2>&1
# The staging deploy publishes the build on GitHub (release "staging-web"). This only downloads: nothing needs to
# reach into the account, so the host's bot protection never stands in the way.
set -euo pipefail

BASE="${XCODE_RELEASE_BASE:-https://github.com/Benson-Kim/xcode/releases/download/staging-web}"
ROOT="$HOME/xcode-web"
WORK="$ROOT/.update"
log() { echo "$(date -u +%FT%TZ) $*"; }

mkdir -p "$ROOT/logs" "$ROOT/tmp" "$WORK"
# One run at a time; a lock left by a run that died is cleared after 30 minutes.
if ! mkdir "$WORK/lock" 2>/dev/null; then
  [ -n "$(find "$WORK/lock" -maxdepth 0 -mmin +30)" ] || exit 0
  rm -rf "$WORK/lock" && mkdir "$WORK/lock"
fi
trap 'rm -rf "$WORK/lock" "$WORK/new" "$WORK/xcode-web.tar.gz"' EXIT

wanted=$(curl -fsSL --max-time 60 "$BASE/xcode-web.tar.gz.sha256" | cut -d' ' -f1)
[[ "$wanted" =~ ^[0-9a-f]{64}$ ]] || { log "no build published"; exit 1; }
[ "$wanted" = "$(cat "$WORK/installed" 2>/dev/null || true)" ] && exit 0

log "installing $wanted"
curl -fsSL --max-time 900 -o "$WORK/xcode-web.tar.gz" "$BASE/xcode-web.tar.gz"
echo "$wanted  $WORK/xcode-web.tar.gz" | sha256sum -c --status || { log "checksum mismatch: not installed"; exit 1; }
rm -rf "$WORK/new" && mkdir -p "$WORK/new"
tar -xzf "$WORK/xcode-web.tar.gz" -C "$WORK/new"
[ -f "$WORK/new/app/release.json" ] && [ -f "$WORK/new/start.js" ] || { log "incomplete build: not installed"; exit 1; }

# The previous build stays as app.old until the next install, to go back to by hand if needed.
rm -rf "$ROOT/app.old"
[ -d "$ROOT/app" ] && mv "$ROOT/app" "$ROOT/app.old"
mv "$WORK/new/app" "$ROOT/app"
cp "$WORK/new/start.js" "$ROOT/start.js"
# Replaced by a rename, never in place: bash is still reading this file.
cp "$WORK/new/update.sh" "$ROOT/update.sh.next" && mv "$ROOT/update.sh.next" "$ROOT/update.sh"
# The API no longer runs here; start.js stops a copy that is still running.
rm -rf "$ROOT/api"
touch "$ROOT/tmp/restart.txt"
echo "$wanted" > "$WORK/installed"
log "installed $(tr -d '\n' < "$ROOT/app/release.json")"
