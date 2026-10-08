#!/usr/bin/env bash
# Uploads a published API to the MonsterASP site over SFTP: takes the site offline (IIS releases the files), syncs the
# changed files, writes web.config with the settings and brings the site back.
# Usage: upload.sh <publish dir>
# Environment: SFTP_HOST, SFTP_PORT, SFTP_USER, SFTP_PASSWORD, SFTP_KNOWN_HOSTS (the server's host keys) and the
# API settings web-config.mjs reads.
set -euo pipefail
PUBLISHED=$1
HERE=$(cd "$(dirname "$0")" && pwd)
TEMP=$(mktemp -d)
trap 'rm -rf "$TEMP"' EXIT

printf '%s\n' "$SFTP_KNOWN_HOSTS" > "$TEMP/known_hosts"
node "$HERE/web-config.mjs" "$TEMP/web.config"
echo "Updating" > "$TEMP/app_offline.htm"
export LFTP_PASSWORD="$SFTP_PASSWORD"

sftp_run() {
  lftp --env-password -u "$SFTP_USER" -e "
    set cmd:fail-exit yes; set net:max-retries 3; set net:timeout 30;
    set sftp:connect-program 'ssh -a -x -o UserKnownHostsFile=$TEMP/known_hosts -o StrictHostKeyChecking=yes';
    $1; bye" "sftp://$SFTP_HOST:${SFTP_PORT:-22}"
}

sftp_run "put $TEMP/app_offline.htm -o wwwroot/app_offline.htm"
sleep 10
sftp_run "mirror --reverse --parallel=4 --exclude-glob *.pdb --exclude-glob web.config $PUBLISHED wwwroot;
  put $TEMP/web.config -o wwwroot/web.config;
  rm wwwroot/app_offline.htm"
echo "uploaded $(find "$PUBLISHED" -type f ! -name '*.pdb' | wc -l) files"
