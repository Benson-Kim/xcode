#!/usr/bin/env bash
# Packages the standalone web build for the cPanel account: app/ (with its static files and release.json),
# start.js and update.sh, and a checksum file beside the archive.
# Usage, from the repository root after `NEXT_OUTPUT=standalone npm run build -w apps/web`:
#   package.sh <commit> <api url> <out dir>
set -euo pipefail
COMMIT=$1
API_URL=$2
OUT=$3
HERE=$(cd "$(dirname "$0")" && pwd)
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

cp -r apps/web/.next/standalone "$STAGE/app"
cp -r apps/web/.next/static "$STAGE/app/apps/web/.next/static"
[ ! -d apps/web/public ] || cp -r apps/web/public "$STAGE/app/apps/web/public"
node "$HERE/relocate.mjs" "$PWD" "$STAGE/app"
COMMIT="$COMMIT" API_URL="$API_URL" node -e '
  const { COMMIT: commit, API_URL: apiUrl } = process.env;
  process.stdout.write(JSON.stringify({ commit, apiUrl, builtAt: new Date().toISOString() }) + "\n");
' > "$STAGE/app/release.json"
cp "$HERE/start.js" "$HERE/update.sh" "$STAGE/"

mkdir -p "$OUT"
tar -czf "$OUT/xcode-web.tar.gz" -C "$STAGE" app start.js update.sh
(cd "$OUT" && sha256sum xcode-web.tar.gz > xcode-web.tar.gz.sha256)
echo "packaged $COMMIT: $(du -h "$OUT/xcode-web.tar.gz" | cut -f1)"
