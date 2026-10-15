# Runbook

The operator's procedures for `xcode-api` (`docs/08-operability.md` section 10). Every
command runs where the API's environment is set (`XCODE_ENV=production`) with the one URL
it needs: `db` commands `XCODE_MIGRATION_DATABASE_URL` (`xcode_owner`), the user commands
`XCODE_DATABASE_OPERATOR_URL` (`xcode_operator`). Set `XCODE_OPERATOR` to your own name
first; every command that changes state records it in `ops.operator_actions`. Commands print
ids and counts on stdout and log to stderr. Exit codes: 0 done, 1 refused or failed, 2 bad
settings or usage.

Log lines are JSON; search them by `event`.

## 1. Readiness is failing

1. Confirm the symptom: `curl -s -i http://127.0.0.1:5000/health/ready` answers
   `503 Unhealthy`, while `curl -s http://127.0.0.1:5000/health/live` answers `Healthy`
   (the process runs).
2. Read the reason: the log line `health.ready.failed`, field `reason`. It is
   `startup has not finished its checks`, `database probe timed out` (no answer within 10 s),
   `routine contract version N != expected M`, or an exception type and message.
3. Startup never finished: look for `startup.database_unreachable` (no connection within
   30 s; the process exits 1), `startup.contract_version_mismatch` (the database and the
   package disagree: run section 5's `db status`, then deploy the matching release or
   `db migrate`), and `db.role_unexpected` (the API connected as another role than
   `xcode_app`; fix `XCODE_DATABASE_URL`).
4. A timeout: when metrics are on, read `db_pool_connections{state="waiting"}` and
   `{state="busy"}` from `curl -s http://127.0.0.1:5000/metrics`; a full pool with waiters
   means slow routines (`db_routine_duration_seconds`) or too small a pool
   (`XCODE_DATABASE_POOL_MAX`, below the role's connection limit, `deploy/README.md`).
5. PostgreSQL itself: `psql "$XCODE_MIGRATION_DATABASE_URL" -c "select 1"`; then
   `select rolname, rolconnlimit from pg_roles where rolname like 'xcode%'` and
   `select usename, count(*) from pg_stat_activity group by 1` for connection exhaustion,
   and the role timeouts with `select rolname, rolconfig from pg_roles where rolname like 'xcode%'`.
6. With the shared limiter (`XCODE_RATE_LIMIT_BACKEND=postgres`) readiness also writes its
   own window `health:ready`; a failure there appears as the exception in the reason.

## 2. A user cannot sign in

1. `xcode-api account-state --email <email>`: status, `has_pin`, `pin_reset_required`,
   `sign_in_status`, `failed_attempts`, `untrusted_failed_attempts`, trusted devices, live
   refresh tokens, `active_membership`. It never prints a hash.
2. `status=removed` or `active_membership=no`: the person was removed; an Owner restores
   them in the app, or `xcode-api provision-user --email <email> --phone <phone>`
   re-activates them (they then set a PIN with an email code).
3. A sign-in pause (`failed_attempts` at the organization's threshold):
   `xcode-api clear-pause --email <email>`. It never lifts the untrusted-device cap.
4. The untrusted-device cap (`untrusted_failed_attempts` at the cap): only a PIN reset by the
   person (an email code) or a verified new device lifts it (`docs/07-auth.md` section 4);
   no command does.
5. `has_pin=no`: the person sets a PIN with an email code from the app. No code arrives: look
   for `mail.failed` with that `request_id` (the recipient appears only as a hash) and
   `mail.queued`/`mail.sent` around it.
6. The answer to the person is the same for an unknown number, a paused account and a capped
   untrusted device by design; do not tell them which it was.

## 3. Rate-limit hits from one address

1. `rate_limit_rejections_total` grows on `/metrics`, and `request.completed` lines show
   `status` 429 on `/auth` routes.
2. Confirm `XCODE_TRUSTED_PROXIES` lists the proxy's address: `xcode-api settings-check`
   prints `trusted_proxies`. If the proxy is missing, every client shares the proxy's address
   and one busy office locks everyone out.
3. With more than one replica, `XCODE_RATE_LIMIT_BACKEND` must be `postgres`
   (`startup.rate_limit_backend` logs the backend at startup).

## 4. Migration failed midway

1. `xcode-api db status`: `applied`, `pending`, `routine drift` and
   `migration checksum drift`. Each migration file is its own transaction, so the failed one
   is still pending and the ones before it are applied.
2. Read the error the failed `db migrate` printed and the `db.migrate.pending` log line.
3. Fix forward: write a new migration that corrects the problem; never edit an applied file
   (`migration checksum drift` would name it). Then `xcode-api db migrate`, `xcode-api db
   status` (exit 0) and `xcode-api db verify` (every line `ok`).
4. `xcode-api db down <version> --i-know-this-destroys-data` only when the release notes say
   that migration reverses without data loss; it logs `db.down.destructive` at WARNING with
   your operator name.

## 5. Routine drift

1. `xcode-api db status` lists routine files whose checksum differs from the database
   (`routine drift: ...`), or `none`.
2. `xcode-api db routines` re-applies every routine file (idempotent) and fixes ownership and
   grants; `db.routines.orphan` warns about an old overload a signature change left behind
   (it stays ungranted; drop it by hand after checking nothing calls it).
3. `xcode-api db status` again (exit 0), then `xcode-api db verify`.

## 6. Rotate the signing key

1. Generate a new key of at least 32 bytes: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. In the secret store, move the current `XCODE_AUTH_SIGNING_KEY` into
   `XCODE_AUTH_PREVIOUS_SIGNING_KEYS` (comma-separated) and set the new key.
3. `xcode-api settings-check` (exit 0; the summary shows `auth_signing_key: <set>` and the
   count of previous keys, never a value), then restart or roll the replicas.
4. After the longest access-token lifetime of any organization's policy has passed, remove
   the old key from `XCODE_AUTH_PREVIOUS_SIGNING_KEYS` and restart again. Sessions survive the
   rotation; a token forged with the old key dies with it.

## 7. Suspected account compromise

1. `xcode-api revoke-sessions --email <email>`: bumps the security version and revokes every
   device trust and refresh token; access tokens stop working at their next request.
2. The person signs in again with an email code and re-trusts their devices.
3. The action is in `ops.operator_actions` (`action = 'revoke-sessions'`, your operator name).
4. If the email account itself is compromised, change the person's email in the app first.

## 8. Who did what

1. Organization changes: `tenancy.change_log` (the app's change log page, or
   `select * from tenancy.change_log where organization_id = ... order by version desc` as the
   read-only role).
2. CLI and migration actions: `select recorded_at, operator, action, target, detail from
   ops.operator_actions order by id desc limit 50`.
3. Sign-in history: `identity.sign_in_attempts` (one row per attempt with its outcome).
4. All three are append-only; keep them as long as the owners decide (`docs/13`
   question 10).

## 9. Startup refuses to start

1. Exit 2 before any socket: the settings named on stdout are missing or refused (every bad
   variable at once). `xcode-api settings-check` prints the same list.
2. Exit 1 after logging `startup.database_unreachable` or `startup.contract_version_mismatch`:
   sections 1 and 4.
3. `startup.unassigned_users` (a warning, not a refusal) counts active users without an
   organization membership: they cannot sign in until provisioned (section 2).
