#!/usr/bin/env bash
# Uploads a published API to the MonsterASP site over SFTP: takes the site offline (IIS releases the files), syncs the
# changed files, writes web.config with the settings and brings the site back.
# Usage: upload.sh <publish dir>
# Environment: SFTP_HOST, SFTP_PORT, SFTP_USER, SFTP_PASSWORD, SFTP_KNOWN_HOSTS (the server's host keys) and the
# API settings web-config.mjs reads.
set -euo pipefail
PUBLISHED=$1
HERE=$(cd "$(dirname "$0")" && pwd)
SFTP_PORT=${SFTP_PORT:-22}
[[ $SFTP_HOST =~ ^[A-Za-z0-9.-]+$ ]] || { echo "SFTP_HOST must be a bare host name, such as site12345.siteasp.net"; exit 1; }
[[ $SFTP_PORT =~ ^[0-9]+$ ]] || { echo "SFTP_PORT must be a number"; exit 1; }
[[ $SFTP_USER =~ ^[A-Za-z0-9._-]+$ ]] || { echo "SFTP_USER must be the site's SFTP login name"; exit 1; }
TEMP=$(mktemp -d)
trap 'rm -rf "$TEMP"' EXIT

printf '%s\n' "$SFTP_KNOWN_HOSTS" > "$TEMP/known_hosts"
node "$HERE/web-config.mjs" "$TEMP/web.config"
echo "Updating" > "$TEMP/app_offline.htm"
export LFTP_PASSWORD="$SFTP_PASSWORD"

# The commands go in a file: lftp reparses -e text as part of an "open" command, and a newline there ends the command
# even inside quotes, so the site was never opened.
sftp_run() {
  {
    echo "set cmd:fail-exit yes; set net:max-retries 3; set net:timeout 30"
    echo "set sftp:connect-program \"ssh -a -x -o UserKnownHostsFile=$TEMP/known_hosts -o StrictHostKeyChecking=yes\""
    echo "open --env-password --user $SFTP_USER sftp://$SFTP_HOST:$SFTP_PORT"
    printf '%s\n' "$@"
  } > "$TEMP/commands"
  lftp -f "$TEMP/commands"
}

sftp_run "put $TEMP/app_offline.htm -o wwwroot/app_offline.htm"
sleep 10
sftp_run "mirror --reverse --parallel=4 --exclude-glob *.pdb --exclude-glob web.config $PUBLISHED wwwroot" \
  "put $TEMP/web.config -o wwwroot/web.config" \
  "rm wwwroot/app_offline.htm"
echo "uploaded $(find "$PUBLISHED" -type f ! -name '*.pdb' | wc -l) files"
