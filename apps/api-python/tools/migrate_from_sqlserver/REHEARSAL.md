# Cutover rehearsal and runbook

`docs/10-data-migration.md` section 5 as a numbered, copy-paste procedure. Run it end to end
at least once on copies (part B) before the night (part C). Values in `<angle brackets>` are
the host's; fill them in during the rehearsal and keep the filled copy with the report.
Commands are shown for PowerShell on the migration host; every connection string comes from
the environment, never from a command line.

## A. Decisions to take before the night

Each box is a decision in `docs/13-open-questions.md`; tick it with the owner's answer.

- [ ] **Q11** A SQL Server database holds data that must survive (default: production yes;
      developer databases are provisioned again with `xcode-api provision-user`).
- [ ] **Q12** Trusted devices and refresh tokens move (default yes, so phones stay signed in);
      verification codes do not (default; they live 10 minutes).
- [ ] **Q13** Retention of the frozen SQL Server copy and of the migration work directory
      (default 30 days read-only, then destroyed).
- [ ] **Q16** People with an empty phone number: fixed or removed in SQL Server before the
      extract (the load refuses while one remains).
- [ ] **Q17** Normalised names are re-derived under the `C` collation; the report lists every
      company, category and item whose normalised form changes.
- [ ] **Q18** Windows time-zone ids map to IANA names; an unmapped id is refused and decided
      here.
- [ ] **Q54** Phones on v2.11 keep working: same paths, same JSON, same token format.
- [ ] **Q59, Q60, Q65, Q71** The grant translation: the report's "rights per person" section
      lists, for every person, the keys not carried and the rights gained; the owner accepts
      it or plans the grants to make on the first morning.
- [ ] **Q82** Trusted devices get their trust and last-use dates from their refresh tokens; a
      device with no token needs a code at its next sign-in.
- [ ] **Q83** How the clients reach the new API: the same public host name switched at the
      reverse proxy or DNS (no app release), or a new URL (a mobile release, because
      `EXPO_PUBLIC_API_URL` is compiled into release builds).
- [ ] **Q84** The signing key: the Python API takes the .NET `Auth__SigningKey` (sessions and
      refresh digests survive) or a new key (every client signs in again; refresh tokens and
      trusted devices still move but no refresh token verifies).
- [ ] **Q85** Who may leave refused rows behind: by default the owner signs the refused list
      of the rehearsal's report, and a refused row not on that list stops the night.
- [ ] Central expenses, scheduled-item pauses and their change-log sections need migration
      `0013_expenses` on the target; if the source holds any, the night waits for it (the
      transform stops with "apply migration 0013 to the target first").
- [ ] Optional: the owner's fleet-number list (`registration,fleet_number`, one per vehicle).
- [ ] The freeze window, its announcement to staff, and who decides a rollback.

## B. Rehearsal (days before, on copies only)

1. Restore the latest SQL Server backup onto a rehearsal server (never the production
   server). Note the backup time: `<backup-time>`.
2. Provision an empty PostgreSQL target the way production will be: apply `db/roles`, then

   ```
   $env:XCODE_ENV = "production"
   $env:XCODE_MIGRATION_DATABASE_URL = "<owner URL of the rehearsal target>"
   $env:XCODE_OPERATOR = "<your name>"
   xcode-api db migrate
   xcode-api db verify
   ```

   Expected: `applied: 0001, ..., <latest>`, then one `ok` line per check and exit 0.
3. Run part C steps 4 to 9 against the rehearsal copies, with the timings written down.
4. Fix in SQL Server (on the production database, outside the freeze, through the .NET API
   where possible) whatever the report refuses; take a new backup and repeat until the
   report's "REFUSED ROWS" section is empty or every remaining row is accepted by the owner.
5. Point a staging web build and a test phone at the rehearsal API and run the clients'
   end-to-end checks: web sign-in, a revenue capture, a petty-cash entry, a phone's offline
   capture replayed against the new API.
6. Record the expected figures for the night: rows per table, the revenue of the last full
   month per organization, people per status, devices live. The night's report must match
   them except for the writes made since the backup.

## C. The night

0. **Preconditions (T-60 min).** The Python API is deployed against the empty production
   target and is not reachable by clients. On the migration host:

   ```
   $env:XCODE_ENV = "production"
   $env:XCODE_MIGRATION_DATABASE_URL = "<owner URL of the production target>"
   $env:XCODE_OPERATOR = "<your name>"
   xcode-api db status
   xcode-api db verify
   ```

   Expected: `pending: none`, `routine drift: none`, `migration checksum drift: none`, every
   verify line `ok`, exit 0. Stop here if not.

1. **Freeze the .NET API.** Writes stop; clients get 503.
   - IIS / ASP.NET Core Module: copy `app_offline.htm` into the site root `<site-root>`.
   - Kestrel behind a reverse proxy: stop the service and have the proxy answer
     `503` with `Retry-After: 900` for `<api-host>`.

   Check: `curl.exe -s -o NUL -w "%{http_code}" https://<api-host>/health` prints `503`.
   Phones keep captures in their offline queue and replay them after the switch (the capture
   is idempotent); the web shows the API as unavailable.

2. **Confirm no writer is left.** On SQL Server:

   ```
   SELECT session_id, login_name, last_request_end_time
   FROM sys.dm_exec_sessions WHERE database_id = DB_ID('<database>') AND is_user_process = 1;
   ```

   Expected: only your own session.

3. **Back up SQL Server** (the rollback point): `BACKUP DATABASE [<database>] TO DISK =
   '<path>\cutover.bak' WITH COPY_ONLY, CHECKSUM;` Expected: `BACKUP DATABASE successfully
   processed`.

4. **Extract.**

   ```
   $env:XCODE_MIGRATION_SOURCE_URL = "<SQL Server connection string>"
   cd apps/api-python/tools/migrate_from_sqlserver
   python -m migrate_from_sqlserver extract --output <work>\extract --frozen
   ```

   Expected: `extracted <N> rows into <work>\extract at <instant>`. Without SNAPSHOT
   isolation `--frozen` is required, which step 1 makes true.

5. **Transform.**

   ```
   python -m migrate_from_sqlserver transform --input <work>\extract --output <work>\run [--fleet-numbers <list.csv>]
   ```

   Expected: `transformed into <work>\run: <r> refused, <d> dropped, <c> changed; run report,
   then load --dry-run`. `<r>` must equal the rehearsal's accepted count.

6. **Report.** `python -m migrate_from_sqlserver report --input <work>\run`. Compare the
   TABLES section with the rehearsal figures; read every REFUSED and DROPPED line.

7. **Dry run.**

   ```
   python -m migrate_from_sqlserver load --dry-run --input <work>\run [--accept-rejected <r>]
   ```

   Expected: every verification `[ok  ]` and the last line `RESULT: every verification
   passed; nothing was written (dry run)`, exit 0.

8. **Apply.**

   ```
   python -m migrate_from_sqlserver load --apply --input <work>\run [--accept-rejected <r>]
   ```

   Expected: `RESULT: committed; every verification passed`, exit 0, and the check
   `xcode-api db verify (after the commit)` `[ok  ]`. Exit 1 means nothing was written:
   read the FAIL lines, fix, and go back to step 4 or decide a rollback (part D).

9. **Check the target by hand.**

   ```
   xcode-api db verify
   xcode-api db status
   ```

   Expected: all `ok`; `pending: none`. `ops.operator_actions` holds one
   `data_migration_load` row naming you.

10. **Start the Python API for real.** Settings that keep sessions alive:
    `XCODE_AUTH_SIGNING_KEY` = the .NET `Auth__SigningKey` (Q84),
    `XCODE_AUTH_ISSUER` = `xcode-api`, `XCODE_AUTH_AUDIENCE` = `xcode-clients` (the .NET
    defaults; use the .NET values if they were changed), `XCODE_AUTH_TRUST_LIFETIME_DAYS` =
    the .NET `Auth__TrustLifetimeDays` (empty when null).
    Check: `curl.exe -s https://<new-api-host>/health/ready` prints `Healthy`; the startup log
    shows the contract version accepted and the unassigned-user count (compare with the .NET
    startup warning).

11. **Smoke test before the switch**, against `<new-api-host>` directly: sign in as the test
    person of the rehearsal on a known phone, open the revenue week, the petty-cash screen
    and the people list; refresh the session. Any failure: part D, case 1.

12. **Switch the clients.**
    - Web: set `API_URL=https://<new-api-host>` for the Next.js app on `<web-host>` and
      restart it. Check: the web sign-in page loads and signs in.
    - Mobile, same host name (Q83): switch `<api-host>` at the reverse proxy or DNS to the
      Python API. Check: a phone already signed in refreshes its session without a code.
    - Mobile, new URL (Q83): release the build with `EXPO_PUBLIC_API_URL=https://<new-api-host>`;
      phones on the old build stay on the frozen .NET API until they update.

13. **Freeze SQL Server for good.**
    `ALTER DATABASE [<database>] SET READ_ONLY WITH ROLLBACK IMMEDIATE;` Leave the .NET API
    stopped. Keep the database and the `cutover.bak` for the retention period (Q13).

14. **Watch** for the first two hours, then at every shift change of day one:
    - `GET /health/ready` stays `Healthy`;
    - error rate: `http_requests_total{status=~"5.."}` against the total;
    - `auth_refusals_total{reason}`: a jump in `unknown` or `capped` means phones point at
      the wrong data or the signing key differs;
    - replay outcomes of the phones' offline captures (identical replays answer 200, changed
      ones 409): a burst of 409s needs a look;
    - the startup log line of unassigned users, `db_pool_connections`, `mail_queue_depth`;
    - staff reports of missing people, vehicles or rights (the report's "rights per person"
      section answers most).

## D. Rollback

The decision belongs to the person named in part A. There is no reverse copy from PostgreSQL
to SQL Server (`docs/10` section 5.6): the freeze window is the safety.

1. **Before step 12 (no client switched).** Nothing moved to the new API.
   - Stop the Python API.
   - Lift the .NET freeze: delete `app_offline.htm`, or restart the service and remove the
     proxy's 503.
   - Check `https://<api-host>/health` answers 200.
   - Keep the PostgreSQL target for the post-mortem, or drop it. Re-run the night later.
2. **After step 12 (clients on the new API).** Writes made since the switch exist only in
   PostgreSQL.
   - Put the Python API in maintenance (503 with `Retry-After`).
   - Export what changed since the switch: `tenancy.change_log` rows with
     `occurred_at > '<switch instant>'` and the matching rows of their sections.
   - `ALTER DATABASE [<database>] SET READ_WRITE;`, then lift the .NET freeze.
   - Switch the web `API_URL` and the host name back, and restart the web.
   - Re-enter the exported changes through the .NET API, or record them for the owner.
3. **After step 13 with the retention period running.** The same as case 2. Restoring
   `cutover.bak` is the fallback only if the database was changed after it was set read-only.
