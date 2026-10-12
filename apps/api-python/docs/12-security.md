# Security model: zero trust

Normative companion to `docs/00-principles.md` section 10. Every control below names its
mechanism and the test or check that proves it. Controls marked "platform" are the
deployment's job and are listed so that the runbook and the release checklist carry them.

## 1. Assets, actors and trust boundaries

Assets: sign-in secrets (PIN hashes, refresh-token digests, verification-code digests),
personal data (names, phone numbers, emails), each organization's financial records,
the signing key, database credentials, the audit trail.

Actors: anonymous callers (sign-in surface), authenticated users on a device, organization
owners and members with granted permissions, operators running the CLI, DBAs, the API
process itself, the reverse proxy.

Trust boundaries, each verified explicitly on every crossing:

```
internet --(TLS, proxy)--> API process --(TLS verify-full, xcode_app)--> PostgreSQL api.* routines
                                                                        --(SECURITY DEFINER, RLS)--> tables
operator --(CLI, XCODE_OPERATOR)--> api.ops_* routines --> ops.operator_actions
DBA --(xcode_owner)--> migrations, roles
```

The API process is treated as compromisable: nothing it can do grants access to a tenant
it has not entered through a verified actor, to a table directly, or to secret material in
clear text.

## 2. Tenets by pillar

### 2.1 Identity

| Control | Mechanism | Proven by |
|---|---|---|
| Every request is authenticated against current state | `current_principal` verifies the JWT (HS256 pinned, `iss`, `aud`, `exp`, zero leeway) then calls `api.auth_resolve_session(user, device, version, now)`; no cache | `tests/api/test_auth_contract.py`: a token stops working the request after a `security_version` bump, a device revocation and a removal (`test_the_session_check_ends_tokens_after_a_version_bump_and_a_removal`, `test_revoking_the_own_device_stops_its_token_at_once`); `tests/db/test_auth_routines.py` (the `resolve_session` cases) |
| Tokens carry identity, not authority | authorization reads `sub`, `version` and `device` only; the other claims (`org`, `role`, the names, `permission`) are echoed by `GET /auth/session` and decide nothing: memberships and permissions are read per request | `tests/unit/test_tokens.py` asserts the claim set exactly; `tests/api/test_people.py` (`test_a_role_change_ends_the_access_token_but_the_refresh_token_renews_it`) |
| The database re-verifies the actor | every tenant-scoped routine starts with `tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, p_permission)`, which checks active membership and permission and raises `XC403` | `tests/db/test_tenancy_isolation.py`; `db verify` (`tenant routines enter their organization`: every `api.*` routine taking `p_organization_id` calls it) and `tests/db/test_structure.py` |
| Permissions are explicit grants with anti-escalation | `tenancy.check_person_grant` (called by `tenancy.save_person`): only an Owner grants or changes an Owner; nobody edits their own membership; only held roles and permissions can be granted; single permissions and approval limits need `access.manage` | `tests/db/test_access_routines.py` (`test_step_11_*` to `test_step_15_*`) |
| Sign-in secrets are never visible to the database or logs | PIN verified in Python with PBKDF2 (parameters from `Security.cs`, `docs/07-auth.md`), constant-time compare, dummy hash for unknown accounts; codes and refresh tokens stored as HMAC-SHA256 digests keyed with the signing key | `tests/unit/test_pin_hasher.py` (format, a published PBKDF2 vector, the full iteration count), `tests/unit/test_digests.py` (an RFC 4231 vector); `tests/db/test_structure.py` asserts no column named `pin`, `code`, `token` or `secret` exists unless it ends in `_hash` or `_digest` |
| Refusals are uniform and paid for | unknown number, paused account, capped device, wrong PIN return the same status, body and headers; unknown accounts still run the dummy hash | `tests/api/test_auth_contract.py` (`test_the_sign_in_refusals_are_byte_for_byte_identical` with the `Seen` exclusions, `test_every_sign_in_attempt_runs_exactly_one_derivation`); nothing beyond the one derivation is time-equalised (`docs/07-auth.md` section 7) |
| Lockout is owned by one place | `api.auth_account_lookup` returns the material to verify; `api.auth_sign_in` records the verdict and moves the counters under `identity.lock_user` (`SELECT ... FOR UPDATE`), so concurrent attempts on one account queue in the database; caps reset only on PIN change or a verified new device | `tests/db/test_auth_routines.py` (`test_concurrent_wrong_pins_on_one_account_are_both_counted`, `test_revoking_a_device_waits_for_the_accounts_other_auth_work`); `tests/db/test_ops_routines.py` (`clear_pause` leaves the untrusted cap) |
| Operators are identified | every CLI command records `XCODE_OPERATOR` (default: OS user name) and the action in `ops.operator_actions` through the `api.ops_*` routine it calls | `tests/api/test_cli.py` asserts the audit row |

### 2.2 Endpoints (devices)

| Control | Mechanism | Proven by |
|---|---|---|
| Device identity is untrusted input | `DeviceId` value object: opaque, 1 to 128 code points (no U+0000, which PostgreSQL text cannot hold), no meaning assigned; the same bound in the request pre-validation and the column `CHECK` | `tests/unit/test_domain_values.py`, `tests/api/test_auth_contract.py` |
| Trust is server-side and revocable | `identity.trusted_devices` rows with an optional expiry from `XCODE_AUTH_TRUST_LIFETIME_DAYS`, revoked by the person's own device revoke, an admin sign-out, deactivation and a change of sign-in details (`docs/07-auth.md` section 6) | `tests/db/test_auth_routines.py` (expiry through `p_now`, the revocation matrix) |
| Untrusted devices cannot brute-force | per-account untrusted attempt cap (value in `docs/07-auth.md`), past the cap the answer equals "unknown number" | `tests/api/test_auth_contract.py` (`test_untrusted_devices_are_capped_at_ten_and_trusted_ones_are_not`) |
| A new device needs proof of email | verification code (6 digits from `secrets`, its HMAC digest stored, 10 minute expiry, consumed by the fifth wrong try); the issue caps of 60 s, 5 per hour and 10 per day per account are silent: the answer stays the same (`docs/07-auth.md` section 1) | `tests/db/test_identity_helpers.py` (`code_caps`), `tests/db/test_auth_routines.py`, `tests/api/test_auth_contract.py` (`test_a_new_device_is_verified_by_the_mailed_code`) |
| Tokens are bound to the device | the `device` claim must name a trusted, unexpired device of the user when the session resolves; a refresh token is refused from another device | `tests/api/test_auth_contract.py` (`test_refresh_from_another_device_is_refused`, `test_revoking_the_own_device_stops_its_token_at_once`); `tests/db/test_auth_routines.py` (`test_verify_device_cannot_trust_another_device_with_a_code`) |
| Client storage | the mobile secure store and web cookie shapes are preserved unchanged (`docs/06-http-contract.md`); the API sets `Cache-Control: no-store` on every response | `tests/api/test_http_plumbing.py` (`test_security_headers_present`, `test_security_headers_on_500`) |

### 2.3 Data

| Control | Mechanism | Proven by |
|---|---|---|
| Tenant isolation does not depend on Python | RLS on every table with `organization_id`, single policy `tenant_isolation TO xcode_api_executor`, GUC set only by `tenancy.enter_organization`, transaction-local | `tests/db/test_tenancy_isolation.py`: a routine that skips `enter_organization` sees nothing; actor from A cannot read or write B |
| The app role cannot touch data | `xcode_app` has `CONNECT`, `USAGE` on `api`, `EXECUTE` on `api.*` except `api.ops_*`; nothing else. `xcode_operator` (CLI only, never held by the API process) has `EXECUTE` on `api.ops_*` and `api.meta_*` only | `db verify`; `tests/db/test_structure.py` queries `information_schema.role_table_grants` for `xcode_app` and expects zero rows |
| Routines cannot be hijacked | `SECURITY DEFINER` with `SET search_path = pg_catalog, pg_temp`, every name schema-qualified, owned by `xcode_api_executor` (not the table owner, so RLS applies), `PUBLIC` has no `EXECUTE`, no dynamic SQL built from parameters | `db verify`; structure test greps routine bodies for `EXECUTE` and `format(` and fails unless the file is allow-listed with a reason |
| RLS binds every service role | no table forces its policies (migrations and the two cross-organization helpers run as the owner on purpose), so the guarantee is that no role the service runs as is a superuser, has `BYPASSRLS`, or is or belongs to a table owner: `xcode_api_executor`, `xcode_app`, `xcode_operator`, `xcode_readonly`. A deployment that connects the API as the owner, or one database user for everything (the shared-host shortcut), fails it | `db verify` check `row-level security binds every service role`; `tests/db/test_structure.py::test_verify_reports_a_service_role_that_row_security_does_not_bind` |
| Read-only access is deny-by-default | `xcode_readonly` has no privilege on `identity`, no RLS policy on tenant tables (so no rows), and column-level `SELECT` only where a DBA grants it in a reviewed migration | structure test: `xcode_readonly` has no grant on `identity.*` |
| Encryption in transit | `XCODE_DATABASE_URL` must carry `sslmode=verify-full` (with `sslrootcert`) in production, unless every address it reaches stays on the machine (a Unix socket or the loopback interface, a database beside the API on one host; `PGHOST`, `PGHOSTADDR` and a numeric `hostaddr` are read as libpq reads them, and a named service never counts). The URL is read as libpq reads it: the last of a repeated key wins and keys are percent-decoded, so `?sslmode=verify-full&sslmode=disable` is refused. SMTP uses STARTTLS or implicit TLS and refuses plaintext outside development | `tests/unit/test_settings.py` matrix, with the URL reading held against libpq's own parser |
| Secret material at rest | hashes and digests only; the signing key, database passwords and SMTP password exist only in the environment | structure test (column names), `tests/unit/test_settings.py` (secrets excluded from the startup summary) |
| No leakage through errors or logs | routine `DETAIL` never carries another tenant's data; problem details never carry exception text; the redaction processor drops `pin`, `code`, `token`, `authorization`, `password`, `phone`, `email` keys | `tests/api/test_auth_contract.py` (`test_no_pin_code_token_phone_or_email_reaches_the_log`), `tests/unit/test_logging.py`, `tests/api/test_http_plumbing.py` (`test_500_body_has_request_id_and_no_exception`) |
| Encryption at rest and backups | platform: encrypted volumes, encrypted backups, restore drill documented in the runbook | release checklist |

### 2.4 Applications

| Control | Mechanism | Proven by |
|---|---|---|
| Three validation gates | Pydantic (shape, types, lengths), domain value objects (normalisation: phone, email, PIN shape, page bounds), routine preconditions and constraints (truth) | per-endpoint tests send malformed, oversized and boundary inputs at each gate |
| No injection surface | only `SELECT * FROM api.<routine>(%s, ...)` with server-side binding; no string formatting of SQL; no `EXECUTE format()` with inputs in routines | `tests/unit/test_layers.py` (`test_routine_sql_literals_are_api_calls_only`: SQL literals in `db/routines/*.py` are routine calls); the one formatted statement, `db/session.py` `call`, takes only a routine name matching its regex; the runner's formatted DDL (`db/migrate.py`) takes catalogue names through `_quote_ident`; structure test on routine bodies. No test yet fails on a new f-string next to `execute(` |
| Resource limits per request | body cap 1 MiB (413; the logo data URL alone is about 350 KB), statement timeout 5 s and lock timeout 2 s on the role, pool bounded, PBKDF2 on its own pool of 2 threads with 16 waiting and a 503 past that (an unknown number still costs one derivation, so this is what keeps an unauthenticated burst from exhausting the threads a shared host allows the account) | `tests/api/test_http_plumbing.py` (`test_body_cap_returns_413`, `test_chunked_body_over_cap_returns_the_same_413`), role settings in `db/roles/010_roles.sql` checked by the structure test, `tests/unit/test_pin_hasher.py` (a burst of 100 creates at most 2 threads and refuses the overflow) |
| Headers | `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Request-ID`; no `Server` header | `tests/api/test_http_plumbing.py` (`test_security_headers_present`, `test_security_headers_on_500`) |
| Origins and hosts | `XCODE_CORS_ORIGINS` exact list, `XCODE_ALLOWED_HOSTS` list; `*` refused outside development | `tests/unit/test_settings.py` |
| Surface minimisation | OpenAPI route off in production unless `XCODE_OPENAPI_ENABLED=true`; `/metrics` off unless enabled; no debug endpoints; uvicorn access log off (our middleware logs) | `tests/api/test_http_plumbing.py` (`test_openapi_absent_when_disabled`); `/metrics` and the access log: prompt 09 (`tests/api/test_operability.py`) |
| Dependency hygiene | `requirements.lock.txt` pinned, `pip-audit` in CI, lock drift check in CI | CI jobs `audit`, `lint` |
| Sign-in surface throttled | fixed window per client address, 30 per minute, 429 with `Retry-After`, charged for every `/auth` request including bodies that do not parse; backend `postgres` when more than one replica | `tests/api/test_auth_contract.py` (the rate-limit tests), `tests/unit/test_rate_limiter_contract.py` (both adapters), `tests/db/test_rate_limit_postgres.py` |

### 2.5 Infrastructure

| Control | Mechanism | Proven by |
|---|---|---|
| Minimal, pinned, scanned image | `python:3.13-slim` pinned by digest; built from the lock file; CI `image` job runs a vulnerability scan and fails on critical findings | CI |
| Least-privilege process | user `xcode` (uid 10001), read-only root filesystem, `/tmp` tmpfs, no capabilities, `PYTHONDONTWRITEBYTECODE=1` | `deploy/Dockerfile` (`USER 10001`); no CI step runs the container or asserts `id -u` yet, and CI has never run |
| Secrets injected, never stored | environment variables from the platform's secret store; `.env` is read only when `XCODE_ENV=development`; its presence elsewhere is logged as a warning and ignored | `tests/unit/test_settings.py` |
| Separate credentials | `xcode_owner` for migrations (one-off job), `xcode_app` for the service, `xcode_operator` for the CLI's user and seed commands, `xcode_readonly` for people; connection limits per role sized to replicas x pool max | `db/roles/010_roles.sql`, structure test on `rolconnlimit` |
| Start-up refuses unsafe configuration | missing key, wrong `sslmode`, wildcard CORS/hosts, log mailer or development codes outside their environments: exit code 2 before any socket opens | `tests/unit/test_settings.py` |
| Health reveals nothing | readiness answers `Healthy` or `Unhealthy` (`text/plain`) without error text; the reason goes to the log line `health.ready.failed` | `tests/api/test_operability.py`, `tests/api/test_health_hosts_and_request_log.py` (`test_a_failed_readiness_probe_logs_its_reason_and_answers_without_it`) |
| Supply chain of SQL | routine files are checksummed (`ops.routine_versions`); `db status` reports drift; migrations refuse edited history | `tests/db/test_migrate.py` |

### 2.6 Network

| Control | Mechanism | Proven by |
|---|---|---|
| TLS termination and HSTS | platform: the reverse proxy; the API never listens on a public interface without it | release checklist |
| Client address is believed only from trusted hops | `XCODE_TRUSTED_PROXIES` (addresses or CIDRs) and nothing else (`serve` turns uvicorn's own proxy-header handling off); every `X-Forwarded-For` line read as one list in order, right-to-left, first untrusted hop wins; any other peer uses the socket address | `tests/api/test_http_plumbing.py` (the forwarded-address cases, parity with the .NET `ForwardedClientTests`), `tests/unit/test_client_address.py`, `tests/api/test_auth_contract.py` (`test_the_forwarded_address_is_ignored_from_an_untrusted_peer`) |
| Host header checked | `XCODE_ALLOWED_HOSTS` on every route except `/health/live`, `/health/ready` and `/health`, which the image's HEALTHCHECK and load balancers call by address and which answer constant bodies (`http/middleware.py` `HostCheckMiddleware`) | `tests/api/test_http_plumbing.py` (`test_a_host_outside_the_allowed_hosts_is_refused`), `tests/api/test_health_hosts_and_request_log.py` |
| Egress | PostgreSQL and SMTP only; the API makes no outbound HTTP calls; routines make no network calls (no `dblink`, no `http` extension) | structure test: extension allow-list (`pgcrypto` only if used) |
| Database network | platform: PostgreSQL accepts `scram-sha-256` over TLS only; `pg_hba` denies the owner role from application networks | `db/roles/README.md` DBA checklist |

### 2.7 Sign-in, devices and access under the design notes v2.33 (prompt 07b)

Decided in `docs/07-auth.md` section 12 and `docs/15-design-v2-3.md`; the tests are those of
`docs/09-testing.md` section 4.1, which the build sessions add. The sign-in rows (the number
step, the lock, device tokens, codes, the PIN throttle, secrets out of the log) are built and
tested since 2026-10-12 (D1); the people, access and back-dating rows since the same day
(D2), except that the writes which call `tenancy.check_writable` come with D4 (revenue),
08 (petty cash) and 08b (central expenses): until each lands, its own write is not limited.

| Control | Mechanism | Proven by |
|---|---|---|
| The number step leaks only what the flow needs | `api.auth_start`: an unknown number answers `pin_required` like a real account with a PIN; its PIN step, "Forgot PIN" and code step are simulated from the sign-in history by `phone_digest` (`identity.unknown_pin_tries`, `identity.unknown_code_tries`); only no-PIN, forced-reset and blocked numbers answer differently (12.14 a) | `tests/api/test_auth_steps.py::test_the_number_step_answers_an_unknown_number_like_an_account_with_a_pin` (byte for byte), `::test_an_unknown_number_counts_down_and_locks_like_a_real_one` |
| Five wrong PINs lock, in two scopes | `api.auth_pin`, `api.auth_sign_in`, `api.auth_change_pin` under `identity.lock_user`; the lock is a counter at five; only a code (or `clear-pause`, which clears both scopes) clears it (12.5) | `tests/db/test_auth_routines.py::test_five_wrong_pins_on_a_trusted_device_lock_every_device`, `::test_five_wrong_pins_from_untrusted_devices_leave_trusted_devices_working`, `::test_a_right_pin_on_a_trusted_device_does_not_clear_the_untrusted_count`, `::test_two_wrong_pins_at_once_both_count_toward_the_lock` |
| Device trust is a hashed random token | `identity.trusted_devices.token_hash` = SHA-256 of 32 random bytes, returned once; a row with a token is never trusted by its `device_id` alone (12.8) | `tests/db/test_auth_routines.py::test_a_device_trusted_with_a_token_is_not_trusted_by_its_id_on_the_old_routes`; `tests/db/test_schema_structure.py` (the column name ends in `_hash`); `tests/unit/test_device_tokens.py` |
| Trust ends after 90 days unused, and after a reset or a block | `identity.device_live`; `api.auth_complete_pin` removes every device on a reset; `api.people_set_active` and `api.people_pin_reset` remove all | `::test_a_device_unused_for_90_days_needs_a_code`, `::test_a_pin_reset_removes_every_other_device`, `tests/db/test_access_routines.py::test_making_a_person_reset_ends_their_sessions_at_once` |
| Codes: three tries, replaced, capped per person | `identity.matching_code`, `identity.issue_code`, `identity.code_caps` (12.6) | `tests/db/test_auth_routines.py::test_the_third_wrong_code_voids_it_and_issues_a_replacement`, `tests/db/test_identity_helpers.py::test_codes_are_capped_at_one_a_minute_and_five_an_hour_per_person` |
| "Send a new code" cannot mail a person without their PIN | `api.auth_resend_code` issues `new_device` only after a right PIN on that device in the last ten minutes | `::test_a_new_device_code_is_resent_only_after_a_right_pin` |
| PIN checks throttled per address and per device | rate-limit policy `auth_pin` (12.1) on A01, A02, N02, N07 | `tests/api/test_auth_steps.py::test_pin_checks_are_throttled_per_address_and_per_device` |
| The new people right cannot escalate | `tenancy.check_person_grant` (only held catalogue keys are granted), `people_self_sign_in`, `people_owner_edit` in S45, S46, S11 | `tests/db/test_access_routines.py::test_people_sign_in_cannot_be_granted_without_holding_it`, `::test_people_sign_in_cannot_be_used_on_oneself`, `::test_only_an_owner_resets_an_owner`, `::test_the_sign_in_actions_need_the_sign_in_right`, `::test_a_scoped_editor_cannot_act_on_a_person_outside_their_view`, `::test_a_device_row_that_is_gone_or_someone_elses_is_not_found` (a non-Owner learns nothing about an Owner's devices: the Owner rule comes before the device lookup) |
| Legacy and hidden keys are never granted | `tenancy.permissions.catalogue`; the person save refuses non-catalogue keys; the migration's `DO` block | `tests/db/test_access_routines.py::test_a_legacy_key_cannot_be_granted`, `::test_the_hidden_organization_key_cannot_be_granted_even_by_an_owner`, `::test_only_owners_manage_organization_settings`, `tests/db/test_tenancy_helpers.py::test_legacy_keys_are_derived_never_granted`, `::test_only_owners_hold_the_hidden_organization_key`, `tests/db/test_migrate.py::test_the_grant_translation_keeps_what_each_person_could_do`, `tests/unit/test_permission_keys.py` |
| The back-dating limit holds on the server | `tenancy.check_writable` in every write of DN-B12-5, on the record's date, after the permission check | `tests/db/test_back_limit.py` (the boundary cases of `docs/09-testing.md` 4.1); revenue (D4, 2026-10-12): `tests/db/test_revenue_routines.py::test_capture_and_change_respect_the_back_limit`, `::test_an_offline_replay_is_checked_at_its_capture_time_within_72_hours`; the other callers' tests come with 08 and 08b |
| Nobody widens the back-dating limit through someone else | `tenancy.save_person`: a non-Owner gives no limit looser than their own (`people_back_limit_not_held`), on create and when a limit changes; nobody edits their own (`people_self_edit`) | `tests/db/test_access_routines.py::test_a_limited_editor_cannot_give_a_looser_limit`, `::test_a_limited_editor_keeps_a_looser_limit_they_do_not_change`, `::test_an_owner_gives_any_limit_whatever_their_own` |
| New secrets stay out of logs | the redaction processor drops `deviceToken`, `device_token`, `currentPin`, `newPin` | `tests/api/test_auth_contract.py::test_no_pin_code_token_phone_or_email_reaches_the_log` (extended) |

### 2.8 Expenses, reports and exports (prompt 08b)

Decided in `docs/05-routines.md` section 11 and `docs/06-http-contract.md` 2.13; tests named are those of
`docs/09-testing.md` 4.2, which the 08b build adds. Until it lands, none of these routes exists in Python.

| Control | Mechanism | Proven by |
|---|---|---|
| Every report and export has its own right, checked in SQL | fleet reports `reports.view`, investment `reports.investment`, petty-cash reports `reports.view` and `pettycash.reports`, report exports `reports.export`, screen exports `revenue.export`, `expenses.export`, `pettycash.export`, each with the screen's own read right (`DEC-40`) | `tests/db/test_report_routines.py::test_each_report_and_export_refuses_without_its_right` (one case per route and right) |
| Scoped viewers' totals hold only their vehicles | every figure comes from `setup.fleet_postings`, `revenue.vehicle_days` and `expenses.entries` over `setup.visible_vehicles()`; headlines, figures, footers, ledger figures, summary figures and the savings balance are sums of those rows; nothing is summed in Python | `tests/db/test_report_routines.py::test_a_scoped_viewer_sees_no_hidden_vehicle_in_any_figure`, `tests/db/test_expense_routines.py::test_the_ledger_figures_of_a_scoped_viewer_leave_out_hidden_vehicles`, `tests/api/test_reports.py::test_a_scoped_viewers_export_holds_no_hidden_vehicle` (the file opened and every cell read) |
| Petty-cash reports follow the floats a person may see | the holders are the person's own float, or every float with `pettycash.view_all`; a `holderId` outside them is 404, never another float's figures | `tests/db/test_report_routines.py::test_a_petty_cash_report_of_another_float_is_not_found` |
| Bounded exports | at most 10 000 rows per file (`export_too_many_rows`, checked on the matching rows before any byte is built); a report read is bounded by the period (367 days) and paged (100 rows at most); the role's statement timeout bounds the time; the file is built in a worker thread so a large export cannot stall the event loop | `tests/api/test_reports.py::test_an_export_past_the_row_bound_is_refused_with_its_sentence`; the timeout by `db verify` (role settings) |
| Every export leaves an audit row | the routine that reads the rows writes the change-log row (section `reports`, the rows count, the format, the filters) and the audit event `reports.exported` in the same transaction; a failure after the commit leaves a row for a file not delivered, never a file without a row | `tests/db/test_report_routines.py::test_an_export_writes_one_change_log_row_with_its_count`, and one API test per export route reading the row back |
| No spreadsheet formula injection | every text cell is written with `write_string` and the workbook refuses to turn strings into formulas, numbers or links; a text starting with `=`, `+`, `-`, `@`, a tab or a carriage return also gets the `quote_prefix` format, so Excel keeps it text when the cell is edited; the value itself is not changed | `tests/unit/test_export_files.py::test_a_cell_starting_with_equals_stays_text` (the produced sheet's XML: an inline or shared string, never an `<f>` element, the quote-prefix style) and `tests/api/test_expenses.py::test_an_exported_note_starting_with_equals_stays_text` |
| The export's rows are the screen's rows | each export reads through the same SQL as its screen (the ledger, the week, the petty-cash list, the report builders), with the same filters and the person's scope | `tests/api/test_reports.py::test_screens_export_what_they_list` |
| Central-expense writes respect the back-dating limit | `tenancy.check_writable` on record (the date), change (the old and the new date) and remove (the date) (`DEC-30`) | `tests/db/test_expense_routines.py::test_a_central_expense_before_the_limit_is_refused_on_record_change_and_remove` |
| A day save cannot bypass the single capture's rules | `api.revenue_day_save` runs `revenue.capture_entry`, the single capture's own steps (threshold, rights, limit, version) | `tests/db/test_revenue_day_routines.py::test_each_row_runs_the_single_capture_rules` (one case per rule) |
| Retried and racing purchases make one purchase | the purchase id's advisory lock before the retry lookup; `UNIQUE (organization_id, group_id, vehicle_id)` | `tests/db/test_expense_routines.py::test_two_connections_recording_one_purchase_make_one_set_of_rows` |
| A decided saving run never changes | `setup.saving_runs` is `INSERT`-only for the executor; `ON CONFLICT DO NOTHING` on the run's key; the per-vehicle advisory lock orders deciders | `tests/db/test_recurring_pause_routines.py::test_two_connections_deciding_one_run_store_one_row`, `tests/db/test_grants.py` (no `UPDATE` or `DELETE`) |

Residual risks of this section are in section 7 (exports of figures a person may see, a client's file name, rows a
failed export left).

## 3. Secrets and rotation

| Secret | Where it lives | Rotation |
|---|---|---|
| JWT signing key | `XCODE_AUTH_SIGNING_KEY` | set the new key, move the old one into `XCODE_AUTH_PREVIOUS_SIGNING_KEYS`, roll replicas, remove the old key after the access-token lifetime; tokens issued with the old key keep verifying until then; refresh tokens are unaffected (database digests) |
| Database passwords | platform secret store, referenced by the URLs | rotate in PostgreSQL, update the secret, roll replicas; the pool reconnects |
| SMTP password | `XCODE_EMAIL_PASSWORD` | update the secret, roll replicas |
| A user's sessions | `identity.users.security_version` | `xcode-api revoke-sessions --email` bumps it (routine `api.ops_revoke_sessions`), every token and refresh token of that user dies at once |
| A device's trust | `identity.trusted_devices` | logout-all or the user's own device management, per the HTTP contract |

Keys are never logged, never in the startup summary, never in problem details, never in
test fixtures committed with real values.

## 4. Audit trail

| Event | Table | Written by |
|---|---|---|
| Sign-in attempts and outcomes (no secrets) | `identity.sign_in_attempts` | every `api.auth_*` routine, one row per call (`docs/07-auth.md` section 2) |
| Organization settings and access changes | `tenancy.change_log` | the routine performing the change (append-only) |
| Operator actions (provision, remove, clear pause, revoke sessions, seed, migrate, down) | `ops.operator_actions` | `api.ops_*` routines and the migration runner |
| Routine and schema versions | `ops.schema_migrations`, `ops.routine_versions` | the runner |

Audit tables are append-only for `xcode_api_executor` (no `UPDATE`/`DELETE` grant) and have
no RLS policy for `xcode_readonly`. Retention is a DBA decision recorded in
`docs/13-open-questions.md`.

## 5. Detection and response (runbook pointers)

- Spikes in `auth_refusals_total{reason}` or `rate_limit_rejections_total`: see
  `docs/08-operability.md` section 10 ("A user cannot sign in", "Rate limit hits").
- Suspected signing-key disclosure: rotate as in section 3; sessions survive, forged
  tokens die once the old key leaves the previous-keys list.
- Suspected account compromise: `revoke-sessions`, then the user signs in again with a
  code (new device trust required).
- Suspected API-process compromise: rotate the `xcode_app` password; the blast radius is
  bounded to what routines allow for actors that were authenticated during the window
  (the process holds no `xcode_operator` credential, so provisioning and removal of users
  stay out of reach);
  review `tenancy.change_log` and `ops.operator_actions` for the window.
- Suspected database credential disclosure: rotate; `xcode_owner` credentials never leave
  the migration job's secret scope.

## 6. Explicitly out of scope for the API

- Web and mobile client hardening (secure store, cookie flags set by the Next.js proxy,
  certificate pinning): unchanged by this rewrite; the HTTP contract they rely on is
  preserved exactly.
- Network segmentation, WAF, DDoS protection, backup encryption: platform controls, listed
  in the release checklist in `docs/08-operability.md`.

## 7. Residual risks to record

- `That mobile number or email already belongs to someone.` on a people save confirms that
  a phone or email exists somewhere in the system, across organizations (parity with .NET;
  `docs/13-open-questions.md` question 29).

- HS256 is a shared-secret scheme: every replica holds the key. Moving to an asymmetric
  algorithm would let non-issuing services verify tokens; none exist today. Recorded in
  `docs/13-open-questions.md`.
- PBKDF2 parameters are inherited from .NET so migrated hashes verify; a hash upgrade on
  successful sign-in is a documented extension, not built now.
- The fixed-window rate limiter admits short bursts at window edges; the per-account caps in
  the database are the real brute-force control.
- Every sign-in, unlock and PIN completion costs one PBKDF2 derivation before any decision
  (a known and an unknown number must cost the same), and the PIN pool admits 18 at once
  (2 running, 16 waiting). One derivation took 1.2 s on the loaded development machine, so a
  few dozen client addresses, each inside its 30 requests a minute, can keep the pool full;
  every other sign-in then gets 503 until they stop. Nothing is counted or spent, and .NET
  slowed down instead under the same load. Owner: operations (prompt 09 sizes the pool
  against the host's measured derivation time and thread cap; a per-account limit before
  the derivation would leak which numbers exist).
- The code caps (5 an hour, 10 a day) are per account across purposes and devices, and A04
  and A07 need only a phone number. Anyone who knows a number can spend its daily budget
  with PIN-reset requests, so the owner's next new-device sign-in gets
  `verification_required` without a code for up to a day (parity with .NET, which counts
  the same way; `identity.code_caps`). Each spent code also sends a mail to the owner.
  Owner: product (a separate budget for `new_device` codes would end the denial, at the
  cost of more mail per account).
- `identity.sign_in_attempts.phone_digest` is an unkeyed SHA-256. Kenyan mobile numbers
  span about 2 x 10^8 values, so anyone who can read the table recovers every number in
  minutes; the digest keeps numbers out of casual reads and logs, not out of a breach.
  Owner: security (an HMAC keyed outside the database would need the key in every routine
  that writes the trail).
- `ops.operator_actions.operator` is whatever `XCODE_OPERATOR` says; every operator shares
  the `xcode_operator` role, so the row names a claimed person, not an authenticated one.
  Owner: operations (one database role per operator, recorded with `session_user`, would
  make it evidence).
- The number step of the v2.33 sign-in tells an outsider that a number belongs to a person
  who has no PIN yet, has a forced reset pending, or is blocked, and each probe of the first
  two mails that person a code (capped at one a minute and five an hour). Accounts with a
  PIN cannot be told from unknown numbers (`docs/07-auth.md` 12.14 a). Owner: product
  (the notes require these three answers).
- A stranger who knows a number can lock that person out of new devices with five wrong
  PINs; a person with a live trusted device keeps working and a code reset unlocks, but a
  person with no live trusted device (trust expired after 90 days unused, or never kept) is
  then locked everywhere, and if their email is not reachable (question 53) recovers only
  through the operator's `clear-pause`, which clears both scopes (DN-B4-2). A thief holding
  a person's trusted phone can lock them out of every device the same way. A thief who also
  tries from untrusted devices gets ten guesses in all before both scopes lock (12.14 b).
  Owner: product (question 47 lets the owner choose the notes' literal single lock).
- Since the one-a-minute code rule spans purposes, a stranger asking for a reset code delays
  the owner's new-device code by up to a minute, on top of the daily budget risk above.
  Owner: product.
- Rows trusted the v2.11 way (by `deviceId` alone) stay trusted by that id on the old routes:
  anyone who learns a phone's device id (it is the access token's `device` claim) can claim
  a PIN-only sign-in there, as today. It ends when phones move to the device token
  (12.14 e). Owner: mobile.
- An offline capture is checked against the back-dating limit at the capture time the
  client claims, held to at most 72 hours before the request (`DEC-12`): a client that lies
  about its clock can write up to three days further back than its limit allows. A v2.11
  phone sends no time and is checked at the request. Owner: product.
- A stranger can make the server mail any person a reset code whose "Device:" line carries
  up to 60 characters the stranger chose (N05 needs only the number; at most five such mails
  an hour per person). The alphabet keeps links and addresses out, not words: "Call 0700
  000 000" fits. Owner: product (a fixed line such as "a new device" for codes asked
  without a PIN would close it, against the notes' "the device name").
- The simulated account of an unknown number (12.14 a) is locked from immutable
  `identity.sign_in_attempts` rows and never clears, while a real account's
  `untrusted_failed_attempts` resets on a verified new device or a PIN change (12.5). An
  outsider who locks a set of numbers at the PIN step and re-probes over days learns which
  re-open to `pin_required`: those are real, active accounts. The number step therefore
  separates "account with a PIN" from "unknown number" slowly and over time, though it
  still reveals only existence, not the PIN, and depends on the owner's activity. Owner:
  product (closing it would require the simulation to mimic an owner's resets, which cannot
  be done without an owner).

- The simulated code of an unknown number follows the request rows, not the code caps: once a
  stranger has spent a real person's hourly or daily code budget (five or ten reset requests),
  that person's code step answers "no code" (`triesLeft` null) after the next voided code,
  while an unknown number keeps simulating a fresh one. Telling the two apart takes a dozen
  requests per number inside the `auth` limit. Owner: security (with the long-term
  distinguisher above; mimicking the caps would need per-digest cap rows).
- Concurrent PIN tries on one unknown number are not serialised like a real account's (the
  lookup records each try in its own transaction before the decision reads the count), so two
  simultaneous tries can show the same `triesLeft`, where a real account's row lock gives
  consecutive values. A timing probe, worth one bit per number. Owner: security (counting the
  try in the decision routine under a lock on the number's digest would close it).
- The cost estimate above is low: the one-a-minute rule separates the two in five requests
  within a minute (forgot PIN, two wrong codes, forgot PIN again, one wrong code: the real
  code is unchanged and its third try answers `code_resent`; the unknown number restarts at
  `triesLeft` 2), and an N04 resend after the minute issues a fresh real code that the
  simulation does not model. Each probe of a real number mails its owner one reset code.
  Owner: question 69 (a shadow state per number instead of a history replay).
- Setup writes run in READ COMMITTED, where .NET ran them serializable, so a rule that
  reads one row and writes another holds only while the routine locks the row it read.
  The company rules are locked (`docs/audit/2026-10-12-verify-area-prompt-06.md` V-D3-1).
  Not yet `setup.save_recurring`: a scheduled item saved in the same moment as a share's
  vehicle retires, its company is archived or its expense item stops can be saved with
  that share or item, which .NET refused; postings stay inside each vehicle's own days, so
  no money is counted after a vehicle leaves. Owner: prompt 08b, which rebuilds the
  scheduled-item routines (`FOR KEY SHARE` on the share vehicles, their companies and the
  expense item, in id order).
- A revenue capture reads the capturing person's back-dating limit without locking their
  membership, so a limit tightened while a capture is in flight may let that one capture
  through. This is accepted, not a gap: the person save reads no revenue, so the two writes
  have no shared read to skew, and committing the capture first is a valid order of two
  concurrent changes. The same holds for the low-day threshold read by a capture while the
  Owner changes it (a record judged under the old threshold counts in "Below 4,000" by its
  amount against the new one). Owner: none.

- An exported file leaves every control: the scope, the rights and the back-dating limit apply when it is built, not
  to whoever it is sent to afterwards (prompt 08b). Owner: product (the change-log row names who exported what, with the
  filters and the row count).
- An export's change-log row is written before the file is built, in the same transaction as the read: if building
  the file fails after the commit, the log shows an export the person never received. The reverse (a file without a
  row) cannot happen. Owner: operations.
- The `reports` rows of the change log are visible only to people who see every company (parity with .NET, RP-18): a
  scoped auditor cannot see who exported. Owner: product.
- A person's own petty-cash float can hold spending on a vehicle outside their scope; the petty-cash reports show that
  vehicle's registration on those rows, without its company (parity with .NET, RP-12). Owner: product.
- A saving's run whose window misses a revenue record stays held until the record is captured, without limit (the
  notes' rule); a vehicle whose days are never captured never saves. The savings report counts such runs as "Waiting
  for revenue". Owner: product.
- `reports.view` opens every fleet report but the investment one (`DEC-40`, the prototype's `MODS`), so a person without
  `savings.view` or `scheduled.view` reads the savings and money-out figures of their vehicles through the reports. The
  vehicle report has shown both kinds to `vehicles.view` holders since 06 (question 73). Owner: product.
