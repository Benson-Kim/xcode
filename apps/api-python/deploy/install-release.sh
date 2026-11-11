#!/bin/bash
# Installs the newest API release on a droplet instance. Runs as root from a systemd timer:
#   XCODE_INSTANCE=xcode-stg XCODE_PORT=8020 \
#   XCODE_RELEASE_BASE=https://github.com/Benson-Kim/xcode/releases/download/staging-api install-release.sh
# With an archive path it installs that file instead: the first install, or going back to an older build by hand.
#
# The instance lives in /opt/$XCODE_INSTANCE (uv, Python, releases/<commit>, current), its settings in
# /etc/$XCODE_INSTANCE (admin.env holds the owner's database URL) and it runs as the service $XCODE_INSTANCE-api.
# A build that fails is recorded and not tried again until another is published (or .update/failed is removed).
# Once a build is ready its commit is written to release.txt, which the proxy serves at /release.
set -euo pipefail
: "${XCODE_INSTANCE:?}" "${XCODE_PORT:?}"
BASE=/opt/$XCODE_INSTANCE
ETC=/etc/$XCODE_INSTANCE
SERVICE=$XCODE_INSTANCE-api
WORK=$BASE/.update
log() { echo "$(date -u +%FT%TZ) $*"; }

mkdir -p "$WORK"
exec 9> "$WORK/lock"
flock -n 9 || exit 0
trap 'rm -rf "$WORK/download"' EXIT

if [ $# -eq 1 ]; then
  archive=$1
  name=$(basename "$archive")
  wanted=$(sha256sum "$archive" | cut -d' ' -f1)
else
  : "${XCODE_RELEASE_BASE:?}"
  read -r wanted name < <(curl -fsSL --max-time 60 "$XCODE_RELEASE_BASE/xcode-api.tar.gz.sha256" || true) || true
  [[ "${wanted:-}" =~ ^[0-9a-f]{64}$ ]] || { log "no release published"; exit 1; }
  [ "$wanted" = "$(cat "$WORK/installed" 2> /dev/null || true)" ] && exit 0
  [ "$wanted" = "$(cat "$WORK/failed" 2> /dev/null || true)" ] && exit 0
  [[ "$name" =~ ^xcode-api-[0-9a-f]{12}\.tar\.gz$ ]] || { log "unexpected archive name: not installed"; exit 1; }
  mkdir -p "$WORK/download"
  archive=$WORK/download/$name
  curl -fsSL --max-time 600 -o "$archive" "$XCODE_RELEASE_BASE/$name"
  echo "$wanted  $archive" | sha256sum -c --status || { log "checksum mismatch: not installed"; exit 1; }
fi
[[ "$name" =~ ^xcode-api-([0-9a-f]{12})\.tar\.gz$ ]] || { log "unexpected archive name: not installed"; exit 1; }
commit=${BASH_REMATCH[1]}
REL=$BASE/releases/$commit
previous=$(readlink -f "$BASE/current" 2> /dev/null || true)
fail() {
  log "release $commit not installed: $*"
  echo "$wanted" > "$WORK/failed"
  exit 1
}

if [ "$previous" = "$REL" ]; then
  log "release $commit is already current"
  echo "$wanted" > "$WORK/installed"
  exit 0
fi

log "installing $commit"
export UV_PYTHON_INSTALL_DIR=$BASE/python UV_CACHE_DIR=$BASE/.cache/uv
rm -rf "$REL" && mkdir -p "$REL"
tar -xzf "$archive" -C "$REL" || fail "the archive does not unpack"
{
  "$BASE/bin/uv" venv --quiet --python 3.13 "$REL/venv" &&
    "$BASE/bin/uv" pip install --quiet --python "$REL/venv/bin/python" --require-hashes -r "$REL/requirements.lock.txt" &&
    "$BASE/bin/uv" pip install --quiet --python "$REL/venv/bin/python" --no-deps "$REL"
} || fail "dependencies"
chown -R root:root "$REL" && chmod -R a+rX,go-w "$REL"

# The database moves forward before the switch; the previous build keeps serving meanwhile.
(
  set -a
  . "$ETC/admin.env"
  set +a
  export XCODE_ENV=production XCODE_OPERATOR=installer XCODE_DB_DIR=$REL/db
  "$REL/venv/bin/xcode-api" db migrate > "$WORK/migrate.log" 2>&1 &&
    "$REL/venv/bin/xcode-api" db verify > "$WORK/verify.log" 2>&1
) || fail "db migrate or verify (see $WORK/migrate.log and verify.log)"

ln -sfn "$REL" "$BASE/current.new" && mv -T "$BASE/current.new" "$BASE/current"
systemctl restart "$SERVICE"
ready=no
for _ in $(seq 1 30); do
  if curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:$XCODE_PORT/health/ready"; then
    ready=yes
    break
  fi
  sleep 2
done
if [ "$ready" != yes ]; then
  if [ -n "$previous" ] && [ -d "$previous" ]; then
    ln -sfn "$previous" "$BASE/current.new" && mv -T "$BASE/current.new" "$BASE/current"
    systemctl restart "$SERVICE" || true
  fi
  fail "not ready within 60 s; back on $(basename "${previous:-none}") (journalctl -u $SERVICE)"
fi

echo "$commit" > "$BASE/release.txt.new" && chmod 644 "$BASE/release.txt.new" && mv -T "$BASE/release.txt.new" "$BASE/release.txt"
echo "$wanted" > "$WORK/installed"
rm -f "$WORK/failed"
# Replaced by a rename, never in place: bash is still reading this file.
install -m 0755 "$REL/deploy/install-release.sh" "$BASE/bin/install-release.sh.next" &&
  mv -T "$BASE/bin/install-release.sh.next" "$BASE/bin/install-release.sh"
for dir in "$BASE"/releases/*; do
  [ "$dir" = "$REL" ] || [ "$dir" = "$previous" ] || rm -rf "$dir"
done
log "installed $commit"
