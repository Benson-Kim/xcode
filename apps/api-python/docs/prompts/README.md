# Conversion prompts

Each file in this folder is a complete prompt to paste into a fresh Claude Code session.
Implementation prompts run on Sonnet (or the repository's `remediation-sonnet` agent);
`verify.md` and the design step of `08b` run on Opus. The prompts assume the session starts
in the repository root.

The inventories in `docs/inventory/` are extracts from the .NET code, and they go stale:
the .NET API keeps changing. So every prompt starts with a drift check that reads the .NET
changes made since its inventory was written (see "Drift register" below), and every
prompt ends with the challenge pass of `docs/14-verification.md`. Outside the drift check,
implementers work from the documents, not from C#.

## Status (2026-10-11)

"Validated" here means a separate session checked and fixed the work. None of those checks
left a report in `docs/audit/`, so under `docs/00-principles.md` section 11 every phase
still needs its first `verify.md` run.

| # | Prompt | State |
|---|---|---|
| 00, 01 | bootstrap app, bootstrap database | implemented; validated 2026-10-08 |
| 02, 03 | schema; identity and tenancy routines | implemented; validated 2026-10-09; 02 verified 2026-10-11, pass with findings (`docs/audit/2026-10-11-verify-area-prompt-02.md`; brand host rules open as question 58); 03 verified 2026-10-11 in fix mode, pass with findings (`docs/audit/2026-10-11-verify-area-prompt-03.md`: sign-in verdict race and phone characters fixed, question 67 resolved) |
| 04, 05 | auth service; tenancy and access | implemented; validated 2026-10-10; red-team fixes 2026-10-11 (PIN pool, production TLS rule, `db verify` check 21); 04 verified 2026-10-11 in fix mode, pass with findings (`docs/audit/2026-10-11-verify-area-prompt-04.md`: limiter order on bearer routes and the loopback mail relay fixed; phone characters, question 67, fixed by the 03 verify); 05 verified 2026-10-11 in fix mode, pass with findings (`docs/audit/2026-10-11-verify-area-prompt-05.md`: the people list filters of register row 8 built; two-connection tests for every 05 write). Both on shared full run 1: 4242 passed, exit 0 |
| 06 | setup | implemented 2026-10-11; verified 2026-10-12 in fix mode, pass with findings after the shared full run of 2026-10-12 (`docs/audit/2026-10-12-verify-area-prompt-06.md`: no blocker; a vehicle write racing an archive of its company fixed with a locking read, the scope and cross-tenant evidence added, the company snapshot, the revise sentence and the join-date check corrected; the scheduled-item save remainder is for 08b; question 70) |
| 07 | revenue | implemented 2026-10-11 with `EXPLAIN` evidence at 10x (`docs/perf/revenue.md`); drift register rows 9, 11 and 13 closed; verified 2026-10-12 in fix mode, pass with findings after the full run that followed 07b D4's landing (`docs/audit/2026-10-12-verify-area-prompt-07.md`: no blocker; a capture racing a retirement or join-date change of its vehicle and the amount-overflow 500 of the shared money parser fixed; the percent of a tied week differs from .NET by one, recorded as an accepted deviation) |
| 07b | the design notes v2.29 to v2.33, built ahead of .NET | design (D0) documented 2026-10-11: `docs/15-design-v2-3.md` and the sections it lists; verified the same day in fix mode (`docs/audit/2026-10-11-verify-prompt-07b.md`: pass with findings — 4 major all fixed in the documents (clear-pause recovery gap, a people/sign-in lock-order deadlock, an unknown-number double-count, a new-route legacy-token trust), 3 minor); D1 (build-auth) built 2026-10-12 (migration `0008_sign_in`, the `api.auth_*` routines, the nine number-first routes; report `docs/audit/2026-10-12-build-07b-d1.md`); D2 (build-access) built 2026-10-12 (migration `0009_access`: the 59-right catalogue, legacy and hidden keys, the grant translation, the back-dating columns, question 58's brand rules; S11, S45, S46, the statuses, the back-dating helpers; report `docs/audit/2026-10-12-build-07b-d2.md`; verified 2026-10-12 in fix mode, pass with findings: `docs/audit/2026-10-12-verify-area-prompt-07b-d2.md`, one major fixed (integers outside their column types answered 500 on the people routes), the shared run's D2 modules green); D3 (build-setup) built 2026-10-12 (migration `0010_setup`: target sets, fleet number, initial investment, main categories; S47 to S52, the 59-right gates on the setup routes, the kinds of scheduled items apart; report `docs/audit/2026-10-12-build-07b-d3.md`; the shared full run of 2026-10-12 passed every setup database module, and D3's 33 failures there, all on the test side, were fixed and their modules rerun green; `xcode` migrated to `0012` and `db verify` 21 of 21; verified 2026-10-12 in fix mode, pass with findings: `docs/audit/2026-10-12-verify-area-prompt-07b-d3.md`, every D3 module green on D4's full run); D4 (build-revenue) built 2026-10-12 (migration `0011_revenue`: the low-day threshold and amber band settings, reason-only records, `setup.vehicle_targets` dropped; B14 reasons with separate capture and correct rights, the B15 signed gap and its band, the back-dating check on capture and change with an offline replay checked at its capture time, the week search; report `docs/audit/2026-10-12-build-07b-d4.md`; its full run of 2026-10-12 passed every D4 module, the 3 failures D1's `test_gateway.py` drift; `xcode` migrated to `0011` and `db verify` 21 of 21; verify-07b-d4 in progress) |
| 08 | petty cash | implemented 2026-10-12: migration `0012`, `db/routines/55_pettycash`, use cases, HTTP under `/setup/pettycash`, fake and parity, with the B19 design; its modules pass one at a time and `db migrate`, `db routines`, `db verify` exit 0 on a fresh database; its modules passed on the shared full run of 2026-10-12 (one 08 defect left in `tests/db/test_structure.py`, `docs/audit/2026-10-12-build-08.md` section 7); `db migrate` and `db verify` exit 0 on the CLI database `xcode` after `0010` (21 of 21, 15:42); challenge pass: 8 findings fixed, question 72 for the owner; verified 2026-10-12 in fix mode by a fresh session (`docs/audit/2026-10-12-verify-area-prompt-08.md`): two minors fixed (the create took the vehicle and item shares before the float, against the lock order of `docs/05` 4.9, with no failure reachable; `entries: null` on the ticked approval), `docs/04` 6.2 and `docs/05` 4.9 corrected; pass with findings, its modules green on the shared full run of queue row 7 |
| 08b | expenses, reports, exports, day capture, scheduled runs | design (D0) documented 2026-10-12: `docs/inventory/inventory-expenses-reports.md`, `docs/04` 14, `docs/05` 11, `docs/06` 2.13, `docs/02` ADR-16, `docs/12` 2.8, `docs/09` 4.2, `docs/10` 3.2, `docs/15` B18 and `DEC-30` to `DEC-46`, questions 74 to 80 (report `docs/audit/2026-10-12-design-08b-d0.md`); verified 2026-10-12 in report mode, pass with findings (0 blocker, 0 major, 4 minor; report `docs/audit/2026-10-12-verify-change-08b-d0.md`), its section 7 corrections folded the same evening (a migrated saving keeps its end, question 89 added); build in progress (revenue-17 [60bb7c], from 22:03) |
| 09 to 11 | | not started |
| verify | adversarial verification | new; first runs: `prompt:06` when 06 reports done, then `prompt:00` to `prompt:05` with fresh eyes |

Each `verify.md` run loads the security-skill cluster for the domains in its scope from
`docs/16-security-matrix.md` (API + web-facing surface; mobile out of scope this round),
and pins every finding as a test. That file also lists the independent, non-Claude checks
(.NET response parity, DBA review of `db/routines`, real v2.11 clients) that the final
go/no-go in prompt 11 depends on.

The security-certification sessions and their exact per-session handoffs are in
`docs/prompts/security-waves.md` (Wave 0 baseline and hosting facts; Wave 1 verify of 06, 07
and 07b-D1 under attack; Wave 2 build D2→D4, 08, 08b, 09, 10 each followed by verify; Wave 3
the independent checks). Wave 3 has two standalone prompts: `docs/prompts/parity.md` (.NET
vs Python response-by-response) and `docs/prompts/security-tooling.md` (gitleaks, SAST,
DAST, SBOM, SHA-pinned actions, fuzz).

## Order and parallelism

| # | Prompt | Depends on | May run beside |
|---|---|---|---|
| 00 | `00-bootstrap-app.md`: lock files, settings, domain and application skeletons, layer test, logging, mail queue, rate limiter, HTTP plumbing, health, container, CLI skeleton, image, CI | nothing | nothing |
| 01 | `01-bootstrap-db.md`: roles (`xcode_owner`, `xcode_api_executor`, `xcode_app`, `xcode_operator`, `xcode_readonly`), migration runner, `ops` migration, first routines, pool and gateway, PostgreSQL test harness, structure tests and `db verify` | 00 | nothing |
| 02 | `02-schema.md`: migrations 0002 to 0007 (every `identity`, `tenancy`, `setup`, `revenue` table, code tables, permission catalogue, RLS, indexes, triggers), domain records and enums, structure, parity, isolation, constraint and grant tests | 01 | nothing |
| 03 | `03-identity-tenancy-routines.md`: composite types, common, tenancy and identity helpers, the eleven `api.auth_*` routines, operator user routines, their gateway, CLI user commands, routine tests | 02 | 04 (disjoint files, listed in both prompts) |
| 04 | `04-auth-service.md`: value objects and policies, PBKDF2, digests, JWT, auth use cases, the thirteen `/auth` routes and envelope, bearer principal, mail templates and timing, fakes and parity, auth HTTP contract tests | 02; 03 for the database tests | 03 |
| 05 | `05-tenancy-access.md`: message catalogue, snapshots and reasons, access and people, change-log history, organization settings, logo, appearance, preferences: routines, use cases, HTTP, tests | 03, 04 | nothing (shares `container.py`, `main.py`, `repositories.py`, `fakes.py` with 06) |
| 06 | `06-setup.md`: companies, vehicles, targets, away periods, expense catalogue, scheduled items and allocations, investment, vehicle report | 05 | nothing (same shared files) |
| 07 | `07-revenue.md`: week grid with paging, dashboard, capture and offline replay, `EXPLAIN` evidence | 06 | nothing |
| 07b | `07b-design-v2-3.md`: the design notes v2.29 to v2.33 built ahead of .NET (design register rows B1 to B17 without the report parts): sign-in redesign, people sign-in actions and statuses, the back-dating limit, the full rights catalogue, dated target sets, fleet number, optional investment, three-level categories, savings rights, low-day reasons and the revenue gap. Design session first (Opus), then four build sessions | 07 | nothing |
| 08 | `08-petty-cash.md`: the petty-cash feature (floats, entries, approvals, issues) from `docs/inventory/inventory-petty-cash.md`: migration 0012, routines, use cases, HTTP, tests; design register row B19 | 07b | nothing |
| 08b | `08b-expenses-reports.md`: what the .NET API gained on 9 and 10 October: central expenses, scheduled-item pause, resume, runs and summary, reports and exports, day capture, people filters, fleet postings. Design session first (Opus), then a build session | 08 | nothing |
| 09 | `09-operability-cli-seed.md`: OpenAPI assertions, startup and readiness, metrics, compression, demo seed, CLI completion, hosting facts, image, CI, runbook | 08b | nothing |
| 10 | `10-data-migration.md`: SQL Server extract, transform, load, verification and cutover rehearsal | 02 to 09 | 11 |
| 11 | `11-audit.md`: the final `verify.md` run over everything, read-only | all | 10 |
| verify | `verify.md`: adversarial verification of one prompt, an area, a change or everything; report or fix | the scope it verifies | any prompt whose files it does not edit (`MODE: report` edits nothing) |

Rules from `CLAUDE.md`: at most two sessions write to this tree at once, and only one writer
per set of files. Only 03 beside 04 (and 10 beside 11) satisfies that; every other pair
shares the composition root or the fakes, so run them one after the other. More
parallelism is possible by giving each session its own git worktree and merging, which is
the user's call. A `verify.md` run in `fix` mode is a writer like any other.

The test database cluster is shared too: every session's run uses the template database
`xcode_template` on the same cluster. Dropping it (needed after a migration or routine
change) breaks another session's run in progress; check `pg_stat_activity` first
(`docs/09-testing.md` section 5).

## Drift register

.NET changes that the inventories and `docs/04` to `docs/06` do not describe yet, measured
on 2026-10-11 against `HEAD` 493bf82 plus the uncommitted working tree of
`fix/web-dropdowns`. A row is closed when the inventory and the documents describe it and
the owning prompt built it. This register is itself a claim: each prompt's drift check
re-measures it and adds what it finds.

| # | .NET change | Source | Python owner |
|---|---|---|---|
| 1 | Central expenses: `GET /setup/expenses/ledger`, `/export`, `/options`; `POST /setup/expenses/entries`; `PUT /setup/expenses/entries/{id}`; `POST /setup/expenses/entries/{id}/remove`; table `CentralExpenses` (migration `20261009153259_CentralExpenses`); tag `Central expenses` | `Domain/CentralExpense.cs`, `Application/CentralExpense*.cs`, `Infrastructure/CentralExpense*.cs`, `Api/CentralExpenseEndpoints.cs`, `tests/api/CentralExpenseTests.cs`; commit 9276c51 plus uncommitted edits | 08b: documented by 08b D0 on 2026-10-12 (`docs/inventory/inventory-expenses-reports.md`; `docs/04` 14, `docs/05` 11, `docs/06` 2.13); built by 08b's build session |
| 2 | Reports: `GET /setup/reports`, `/setup/reports/fleet/{report}`, `/setup/reports/pettycash/{report}`, `/setup/reports/{group}/{report}/export`; Excel built in code, PDF with PDFsharp and bundled OFL fonts; tag `Reports` | `Application/Reports/*`, `Infrastructure/Reports/*`, `Assets/Fonts/*`, `Api/ReportEndpoints.cs`, `tests/api/ReportTests.cs`, `packages/shared/src/reports.ts` | 08b: documented by 08b D0 on 2026-10-12 (`docs/inventory/inventory-expenses-reports.md`; `docs/04` 14, `docs/05` 11, `docs/06` 2.13); the export library is `docs/02-stack.md` ADR-16 |
| 3 | Day capture: `GET /setup/revenue/day`, `PUT /setup/revenue/day/{date}`; revenue use cases changed | `Application/RevenueDayContracts.cs`, `Infrastructure/RevenueDayQueries.cs`, `Application/RevenueUseCases.cs`, `tests/api/RevenueDayTests.cs`; a conflicting row of a day save answers 409 with `current` plus `vehicleId` (`Api/RevenueEndpoints.cs:26-30`, `Application/RevenueContracts.cs:139-148`), which a single-cell save never sets; inventory drift log entries 25 and 26 | 08b (07 built the single-cell contract, whose steps a day save repeats per row): documented by 08b D0 on 2026-10-12 (`docs/inventory/inventory-expenses-reports.md`; `docs/04` 14, `docs/05` 11, `docs/06` 2.13); each row runs D4's capture steps (`DEC-42`) |
| 4 | Screen exports: `GET /setup/revenue/export`, `GET /setup/pettycash/export?view=expenses\|cash` (and the central-expenses export of row 1), permission `reports.export` | `Application/Reports/ScreenExports.cs` (uncommitted) | 08b: documented by 08b D0 on 2026-10-12 (`docs/inventory/inventory-expenses-reports.md`; `docs/04` 14, `docs/05` 11, `docs/06` 2.13); rights by module (`DEC-40`) |
| 5 | Scheduled items: `POST /setup/recurring/{id}/pause`, `/resume`; `GET /setup/recurring/summary`; `GET /setup/recurring/{id}/runs`; list rows gain `pausedFrom`, `lastRun`, `lastRunVehicles`, `balance`; table `RecurringPause` (From, Through null while paused; Stop stays final); the change-log snapshot of every scheduled-item write gains `PausedFrom` and `Pauses` (`[{From, Through}]`) after `StoppedFrom` (`Application/Setup/RecurringUseCases.cs:170-175`), which 06's snapshots, built to the earlier contract, do not carry yet | `Domain/Setup/RecurringPause.cs`, migration `20261010194310_RecurringPauses`, `Application/Setup/RecurringUseCases.cs`, `tests/api/RecurringPauseTests.cs` (uncommitted) | 08b (06 builds the earlier contract): documented by 08b D0 on 2026-10-12 (`docs/inventory/inventory-expenses-reports.md`; `docs/04` 14, `docs/05` 11, `docs/06` 2.13); the saving model of design register row B18 with it |
| 6 | Fleet postings: the vehicle report and investment read postings from more sources | `Application/Setup/FleetPostings.cs`, `Infrastructure/Setup/FleetPostings.cs`, `Infrastructure/Setup/SetupRepository.cs` | 08b: documented by 08b D0 on 2026-10-12 (`docs/inventory/inventory-expenses-reports.md`; `docs/04` 14, `docs/05` 11, `docs/06` 2.13); one SQL function, `setup.fleet_postings`, for every source |
| 7 | Petty cash: `POST /setup/pettycash/approve` (ticked `{entries:[{id,version}]}`, all or none, 409 on a changed version, approved ones skipped); `approve-day` takes an optional `to`; overview gains `waiting`/`waitingCount`; a credit note's payee is optional; use cases changed | `Application/PettyCash*.cs`, `Domain/PettyCash.cs`, `Infrastructure/PettyCashRepository.cs`, `tests/api/PettyCashTests.cs`, `packages/shared/src/pettyCash.ts` | 08: inventory corrected by its D0 on 2026-10-12 (`PC-13`, `PC-19` to `PC-21`, `PC-23`, `PC-26`, `PC-31` to `PC-33`, line check 14, sections 4 and 5); 08 builds it |
| 8 | List filters: `GET /setup/people?role=<name>&status=active\|waiting\|none` (`Status must be active, waiting or none.`); `GET /setup/vehicles?companyId=`; `GET /setup/recurring?kind=&companyId=&status=` with running items first. `api.people_list` has none of them; prompt 06 builds the vehicle and recurring filters (its drift-check bullet); `docs/06-http-contract.md` S05, S17 and S24 describe all three | `Api/SetupEndpoints.cs`, `Application/AccessUseCases.cs`, `Application/Setup/*UseCases.cs` in 9276c51; `tests/api/ListFilterTests.cs` | vehicles and recurring: built by 06 (`api.setup_vehicle_list` `p_company_id`, `api.setup_recurring_list` `p_kind`/`p_company_id`/`p_status`); people: closed by the `verify.md` run on `prompt:05` (`api.people_list` `p_role`/`p_status`, `people_filter_status_invalid`; `docs/audit/2026-10-11-verify-area-prompt-05.md`); checked against `ListFilterTests` by 08b D0 on 2026-10-12: nothing missing (`docs/09-testing.md` 4.2) |
| 9 | The dashboard cache changed (the Python design has no cache): check whether a behaviour changed with it | `Infrastructure/RevenueDashboardCache.cs` | closed by 07: the cache only passes the new repository methods through (`Infrastructure/RevenueDashboardCache.cs:99-108`); figures, masking and the cache key are unchanged (inventory drift log entry 27) |
| 10 | Mail to a relay on the same machine without TLS: `Email:EnableSsl=false` turns TLS off for a loopback relay only, which staging uses (its host's mail server on 127.0.0.1). The Python `SmtpMailer` refuses plaintext outside development, so on such a host no code mail would leave and new devices could not sign in | commit 553dd15 (`EmailSenderTests.cs`); `src/xcode_api/infra/mail.py` `SmtpMailer` | closed by the `verify.md` run on `prompt:04` (2026-10-11): `XCODE_EMAIL_TLS=false` sends without TLS and is refused outside development unless `XCODE_EMAIL_HOST` is `localhost` or a loopback address (`settings.is_local_host`, `tests/unit/test_smtp_mailer.py`, `tests/unit/test_settings.py`) |
| 11 | Revenue tests changed after the inventory: `RevenueCaptureTests`, `RevenueComplexityTests`, `RevenueTests`, `RevenueWeekPagingTests` | commit 9276c51 | closed by 07: the changes are row 13 and the rewritten complexity test (`RevenueComplexityTests.cs:63-82`, now a week read, not a save); the inventories cite the renamed tests |
| 12 | Test classes in neither `inventory-tests.md` nor the crosswalk of `docs/09-testing.md` section 4: `CentralExpenseTests`, `CentralExpenseDomainTests`, `EmailSenderTests`, `ListFilterTests`, `RecurringPauseTests`, `ReportTests`, `RevenueDayTests` (match class names, not file names: `Phase1ContractTests.cs` holds three classes that are covered) | `tests/api/` | the prompt that owns each (rows 1 to 10); 11 checks the crosswalk is complete; the 08b classes are in `docs/09-testing.md` 4.2 (08b D0, 2026-10-12) |
| 13 | Revenue days are captured in any order: a new record is no longer refused while an earlier active day has none (the 400 with `earliestMissing` and `RevenueEarlierDayMissingException` are gone), and a `missing` cell is `canEdit` for anyone holding `revenue.capture`; the week still reports `earliestMissing` and `firstGap`; the mobile queue lost its `blocked` state | `Application/RevenueUseCases.cs:130-131`, `Api/RevenueEndpoints.cs:22-34`, `Application/RevenueContracts.cs:54-55`, `RevenueCaptureTests.SavingPastAGapIsAllowedAndTheGapStaysVisible`, `RevenueWeekPagingTests.cs:222-223`; commit 9276c51; inventory drift log entry 24 | closed by 07 (`api.revenue_capture` has no such step; `revenue.cell`) |
| 14 | Change-log sections `centralexpenses` (rows visible to a scoped viewer by their vehicle) and `reports` (visible only to viewers of every company) in the history filter; Python's `ck_change_log_section` and `api.history_list` have neither | `Infrastructure/Setup/SetupRepository.cs:381-386`, `Infrastructure/CentralExpenseRepository.cs:146-151`, `Application/Reports/ReportUseCases.cs:78-79`; found by 08b D0 on 2026-10-12 | 08b: documented (`docs/04` 14.5, `docs/05` 11.8) |

## Design register

Product rules from the running design notes v2.29 to v2.33
(`docs/design/XCODE_Build_Notes_v2.3.md` in the repository root, 10 October 2026, layout in
`XCODE_Web_v2.3.html`) that change the API. The .NET column was measured on
2026-10-11 against `HEAD` 493bf82 plus the uncommitted working tree. The owner decided the
same day that Python builds these rows ahead of .NET (`docs/13-open-questions.md` question
46): for them the notes decide behaviour, not the .NET code (section "When a prompt and
the code disagree"), and the owner column is the build order. Mobile is parked at v2.11
and has none of these rules, so released phones keep calling today's contract (question
54). A row is closed when the documents describe it and its owner built it.

| # | Rule (notes section) | .NET on 2026-10-11 | Python documents it changes | Python owner | Status |
|---|---|---|---|---|---|
| B1 | Sign-in starts with the mobile number alone; the server decides the next step (v2.33 s1) | none: `/auth/sign-in` takes number and PIN together | `docs/06` A01 to A13, `docs/07` section 3 | 07b (D1); question 54 | documented (`docs/15` B1, rules DN-B1-1 to 8) |
| B2 | First sign-in by number and code, then a PIN; new people have no PIN, no default `0000` (v2.33 s1) | at `HEAD` (setup-pin flow; new people have no PIN; no `0000` anywhere); only the number-first entry is missing (B1) | none beyond B1 | built (04); the number-first entry with B1 in 07b (D1) | documented (`docs/15` B2) |
| B3 | Forced PIN reset ("PIN reset required") that goes straight to the code; a people right to force it and to remove devices one by one or all; people statuses Active, Not signed in yet, PIN reset due, Locked, Blocked; the "Sign in" pane (v2.33 s1, s3) | none: no forced-reset flag; `PersonDto` has `active` and `hasPin`; only "sign out of all devices" under the people-manage right | `docs/04` section 3, `docs/06` S01 to S05, `docs/07`, the permission catalogue | 07b (D1 the forced reset, D2 the people actions and statuses) | built: D1 the forced reset, D2 the people actions, statuses and pane (2026-10-12) |
| B4 | Five wrong PINs lock the PIN on every device until a reset with a code (v2.33 s1) | conflicts: a trusted device is paused for `lockout_minutes`; untrusted devices have a cap of 10 per account (`SignInService.cs:10,37-41`) | `docs/07` sections 1 and 4 | 07b (D1); question 47 | documented (`docs/15` B4; decision DEC-1) |
| B5 | PIN of exactly 4 digits; also refuse the last four digits of the person's own number and the PIN being replaced (v2.33 s1) | partial: 4 to 8 digits with a policy minimum; all-equal digits and +1/-1 runs refused (`AuthContracts.cs:39-49`) | `docs/07` section 1, `domain/policies.py` | 07b (D1); question 47 | documented (`docs/15` B5) |
| B6 | Codes: void after 3 wrong tries and a new one sent; at most one a minute and five an hour per person (v2.33 s1) | conflicts: void after 5, none sent; 60 s, 5 an hour and 10 a day (`AuthCodes.cs:12-37`, `Entities.cs:64-70`) | `docs/07` sections 1 and 5 | 07b (D1); question 47 | documented (`docs/15` B6) |
| B7 | Trusted device: a random token stored hashed with device name, date trusted and last used, expiring 90 days after last use; a PIN reset removes every trusted device; the profile lists the person's own devices and changes the PIN (v2.33 s1, s2) | conflicts: keyed by the client's `deviceId`, optional fixed lifetime from the trust date; a reset ends refresh tokens only; no change-PIN or device-list route | `docs/04` section 3, `docs/06` auth rows, `docs/07` sections 5 and 6 | 07b (D1); question 47 | documented (`docs/15` B7) |
| B8 | A sign-in history, and change-log entries for PIN and device events (v2.33 s1) | none | `docs/04`, `docs/05` (`tenancy.record_change` callers) | 07b (D1) | documented (`docs/15` B8) |
| B9 | Dated target sets: a start date (today or later) and seven day figures; started sets are fixed, future ones replaced or removed, a set equal to the one in force refused; its own right; reports sum the set in force on each day (v2.31 s1, v2.32 s1) | partial: dated weekly targets (`FleetVehicle.cs` `VehicleTarget.EffectiveFrom`, `TargetOn`) appended from today on an update; no day figures, no future sets, no own right | `docs/04` vehicle targets, `docs/05` `setup.target_on`, `docs/06` vehicle rows | 07b (D3); the report sums in 08b | documented (`docs/15` B9; the report sums in 08b); built 2026-10-12 (D3): target sets, S47 to S49, `vehicles.target`, the first set from the join date, the list's set in force and next set, the report target as the sum of day targets; the revenue day targets come with D4 |
| B10 | Fleet number: required, unique within a PSV company, editable and logged; drop-downs show registration and fleet number (v2.29 s4) | none | `docs/04` vehicles, `docs/06` vehicle bodies and options | 07b (D3) | documented (`docs/15` B10); built 2026-10-12 (D3): required and unique within a PSV company, logged, in the S03, S04 and S25 options; the R01 search comes with D4 |
| B11 | Initial investment optional, stored empty rather than zero (v2.32 s2) | none (investment is a dated list, `VehicleInvestment`) | `docs/06` vehicle and investment rows | 07b (D3) | documented (`docs/15` B11; the report in 08b); built 2026-10-12 (D3): optional on the vehicle, 0 stored empty, changes logged |
| B12 | A per-person limit on how far back records may be written: none, N days or N months back, an optional fixed date, the later wins, 7 days for new people; checked on the record's date for the writes the notes list (v2.32 s3) | none: writes only refuse the future (`RevenueUseCases.cs:109`, `PettyCashUseCases.cs:371-377`) | `docs/04` memberships, `docs/05` the write routines, `docs/06` people bodies and refusals | 07b (D2 the setting and the helper, D4 the revenue check); 08 and 08b their checks; question 51 | D2 built 2026-10-12: the setting, `tenancy.earliest_writable`, `tenancy.check_writable`, the words, and the rule that a non-Owner gives no looser limit than their own; the checks in the writes come with D4, 08 and 08b |
| B13 | People list and person form (access chips, "Can change" in words, panes); 58 rights, 59 with the sign-in right (v2.32 s4, v2.33 s3) | none: 40 keys (`Domain/PermissionKeys.cs`) | `docs/06` S05, the permission catalogue | 07b (D2) | built 2026-10-12 (D2): the 59 rights, the legacy and hidden keys, the people list fields; question 71 |
| B14 | Revenue: a day below 4,000 needs a reason (Garage, Arrest, No Crew, Other), the threshold is a setting, "Below 4,000" replaces "No revenue days"; separate rights to fill an empty day and to change a saved one (v2.29 s1, v2.30 s1) | none for the reason (an amount cannot carry one, `Domain/Revenue.cs:17-26`); partial for the rights (`revenue.correct` only for a past saved day) | `docs/04`, `docs/05` and `docs/06` revenue rows | 07b (D4) | built 2026-10-12 (07b D4; its modules passed on its full run, `docs/audit/2026-10-12-build-07b-d4.md`) |
| B15 | Revenue gap: a signed figure, green, amber or red, the 10 per cent a setting, measured against the day targets of the days that count so far; headline and export figures (v2.30 s2, v2.31 s2) | none: `Percent` only (`RevenueContracts.cs:77,90`) | `docs/06` revenue rows | 07b (D4); the report and export figures in 08b | built 2026-10-12 (07b D4; its modules passed on its full run, `docs/audit/2026-10-12-build-07b-d4.md`); report and export figures in 08b |
| B16 | Expense categories in three levels (main category, category, item), none built in; "Counts as" and the three built-in groups removed; reports per main category (v2.31 s3) | none: `ExpenseBucket` holds the three groups (`ExpenseCatalog.cs:5-9`) | `docs/04` expense catalogue, `docs/06` catalogue rows, reports | 07b (D3 the catalogue); 08b the reports; question 52 | documented (`docs/15` B16; reports in 08b); built 2026-10-12 (D3): main categories (S50 to S52), a category under one or none, `DEC-17` made them from the buckets in use; the bucket stays for the vehicle report until 08b |
| B17 | Savings apart from scheduled expenses: their own view, add, edit and pause rights, rights copied by a migration, change-log wording "Saving, [name]" and "Scheduled expense, [name]" (v2.30 s3) | partial: pause, resume and summary in the working tree (drift row 5) under the one pair `commitments.view` and `commitments.manage` | `docs/06` S24 onward, the permission catalogue, history wording | 07b (D2 the rights, D3 the routes) | documented (`docs/15` B17); built 2026-10-12 (D3): the routes gated by kind, items of a kind not viewable left out, the new change-log wording; pause and resume with 08b |
| B18 | Saving model: an amount per vehicle, runs every day, week, month or year, a revenue condition, an opening balance per vehicle, no start date, no back posting, no end date (v2.30 s4, the notes' "locked model") | conflicts: `RecurringDefinition` keeps start and end dates and splits one total across vehicles | `docs/04` scheduled items, `docs/06` S24 onward | 08b; question 49 | documented by 08b D0 on 2026-10-12 (`docs/15` B18: DN-B18-1 to 10, `DEC-31` to `DEC-36`; `docs/04` 14.3, `docs/05` 11.1 and 11.3); built by 08b's build session |
| B19 | Petty cash: 20 rights; edit and delete only before approval, delete after approval with a reason; send back as a flag on a waiting entry; delete a cash entry with a reason; add for another manager; the date changed in the edit; no note fields; a credit note without a payee and with an optional reason; a shared purchase recounted after a part changes (v2.29 s3, s5) | partial: send back is a status that needs the approve right; every delete needs a reason; approvers may change approved entries (`PettyCashUseCases.cs:303-312`); payee optional in the working tree (drift row 7) but the reason forced; 6 petty-cash keys; `GroupSize` never recounted (`CentralExpense.cs:123-148`) | `docs/inventory/inventory-petty-cash.md`, `docs/04` section 6.2, `docs/05` section 4.9, `docs/06` section 2.11 | 08 (after 07b, which adds the 20 petty-cash rights) | documented by 08's D0 on 2026-10-12 (`docs/15` B19: DN-B19-1 to 13, DEC-21 to DEC-29; `docs/04` 6.2, `docs/05` 4.9, `docs/06` 2.11); shared purchases with 08b (question 68); 08 builds the rest |
| B20 | Data changes these rows imply: weekly targets into a dated set (a seventh per day), people without a PIN, fleet numbers backfilled, petty-cash and savings rights copied from the old ones, categories without a main category | none | `docs/10-data-migration.md` | 10 | documented in `docs/10-data-migration.md` 3.1; built by 10, and on development data by 07b's migrations |
| B21 | The dashboard has three rights (`dash.net`, `dash.gaps`, `dash.pc`) and every module its own export right (`rev.export`, `exp.export`, `pc.export`, `rep.export`) (v2.32 s4, the prototype's `MODS`); found by the 07b design session | ten dashboard keys; one `reports.export` for every export (drift row 4) | `docs/15` 3.1 and 3.4 (legacy keys for v2.11), `docs/06` R02 | 07b (D2 keys, D4 R02); 08 and 08b the exports | documented (`docs/15` section 3) |
| B22 | Organization settings have no right among the 59 (the prototype has no settings screen); found by the 07b design session | `organization.manage` | `docs/15` 3.3 | 07b (D2) | documented; question 59 |

The notes' own "Not done, flagged" list is in `docs/13-open-questions.md` questions 48 to 53.

## What every prompt contains

1. Role and the reading list (always `CLAUDE.md`, `docs/00-principles.md`,
   `docs/01-architecture.md`, then the design documents and the inventory sections the
   phase draws on).
2. A drift check before any code: the .NET changes since the inventory was written, for
   the routes and rules the prompt builds; the inventory and documents corrected first.
   The same check reads the design register rows the prompt owns.
3. Scope as numbered deliverables, each with its evidence (file + symbol + test).
4. Invariants that must hold at the end.
5. Verify commands with expected results.
6. The challenge pass (`docs/14-verification.md`), reported with the rest.
7. The report format.
8. House rules: naming (`docs/11-naming.md`), no plan or prompt identifiers in code, no
   AI attribution, no commits unless asked, shared-tree rules, never weaken a test.

## Running the tests

Measured, not hoped (`docs/09-testing.md` section 5): the full suite takes about an hour on
a quiet machine and up to two when other sessions run. Run the touched modules first; run
the full suite once, in the background with a log file, and report its counts. After a
migration or routine change, drop `xcode_template` (when nobody else is running), or the
run tests the old routines. The local cluster is PostgreSQL 16 on port 5433; Docker is not
installed.

## When a prompt and the code disagree

Exception, decided by the owner on 2026-10-11 (`docs/13-open-questions.md` question 46):
for the rows of the design register the design notes decide behaviour, and Python builds
them before .NET has them (prompts 07b, 08, 08b, 10). The released clients still hold
(question 54): what a v2.11 phone sends keeps working. Everything below applies to the
rest.

The .NET code and its tests are the source of truth for behaviour; the inventories in
`docs/inventory/` are extracts from them. If an inventory is wrong, the implementer fixes
the inventory file and notes it in the report; the HTTP contract is never changed to match
a convenient implementation. If a design document is wrong, the implementer changes the
document in the same change and says so in the report. Open questions are built with their
recorded default (`docs/13-open-questions.md`) and left open.
