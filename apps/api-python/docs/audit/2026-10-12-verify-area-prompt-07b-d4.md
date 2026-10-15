# Verification of prompt 07b D4 (revenue), 2026-10-12

`SCOPE: area:prompt 07b D4`, `MODE: fix`, `DEPTH: standard`. Method: `docs/14-verification.md`.
Session revenue-a8 [c5ed4b] (the name of the finished verify-07b-d2 session, after `/clear`; not
the D4 builder), registered on the coordination board at 17:53. D4 landed at 17:12; the D4
builder's full run (queue row 7, `pytest -n 2`, a fresh `xcode_template_d4full` built from the
live tree at 17:35) froze `src/`, `db/` and `tests/` for the whole reading pass. This report
reads that run's log as both the baseline and the one full run of the scope; the test fix of
this report was proven fail-first in scratchpad copies beside the run and landed after it.

## 1. Verdict

**pass with findings.** No blocker survives. The full suite ran to completion once on a fresh
template built from the files under test (D4's queue row 7, 17:35 to 19:31, 5733 passed and 3
failed); every D4 module in it is green, and the three failures are D1's `test_gateway.py`
drift, reported to D1's next session. One major (V-D10-1: a scoped viewer's search and D4's
whole-grid figures had no test) is fixed with tests that fail on two mutations of the routine
and pass on the routines as built, landed and rerun on the live tree (92 passed). The other
major (V-D11-1) and the two minors are document corrections; four notes are recorded.

| Verdict | Claims |
|---|---|
| holds | 22 |
| fails | 2 (C16, C23; both corrected) |
| unproven | 1 (C24) |
| n/a | 0 |
| not checked | 0 |

| Severity | Surviving findings |
|---|---|
| blocker | 0 |
| major | 2 (V-D10-1 fixed with tests; V-D11-1 documents corrected) |
| minor | 2 (V-D11-2, V-D11-3; documents corrected) |
| note | 4 (N-1 to N-4) |

No code defect in the D4 routines, migration or Python layer survived. Both majors are about
evidence and instructions: a scoped viewer's view of D4's new search and whole-grid figures had
no test, and the documents let the 08b session build the revenue day capture without the
back-dating limit and the low-day rule.

## 2. Thesis and claims

Thesis (steelmanned): prompt 07b D4 delivers design-register rows B14 and B15, and B12's revenue
check, ahead of .NET. A day below the organization's low-day threshold (a setting, 4,000 by
default) cannot be saved without one of the four no-revenue reasons. A record holds an amount, an
amount with a reason, or a reason alone. "Below 4,000" counts low and no-revenue days, and every
total still counts a low day's amount. Filling an empty day needs `revenue.capture`, and changing
a saved one needs `revenue.correct`, today's included. A cell the person cannot change is not
editable. The week carries a signed gap against the day targets of the days that count so far,
coloured by an amber band that is also a setting. Capture and change are checked against the
person's back-dating limit on the record's date, and an offline replay at its capture time held to
the last 72 hours. Every figure is computed in SQL, an identical replay is answered `replayed`
whatever the threshold, limit or rights, a v2.11 phone keeps working except where
`docs/15-design-v2-3.md` section 4 lists a deliberate change, and the behaviour equals the
documents (`docs/04` 13.5, `docs/05` 10.5, `docs/06` 2.12 and section 3).

| # | Claim | Stated in | Code that carries it | Verdict | Grade |
|---|---|---|---|---|---|
| C1 | A day below the threshold needs a reason; at or above it takes none (DN-B14-1, DEC-16) | `docs/15` B14; `docs/05` 10.5 step 4b | `revenue_capture.sql:116-133` | holds | A (`test_a_low_day_needs_a_reason`, `test_the_threshold_is_checked_after_the_vehicle_and_before_the_date`, D4's mutation A) |
| C2 | The threshold and the amber band are organization settings, defaults 4,000 and 10 | DN-B14-2, DN-B15-2; `docs/04` 13.5 | `0011_revenue.sql` table; `settings_defaults.sql:57-60`; `settings_document.sql:78-86`; `check_revenue_settings.sql` | holds | A (`test_the_revenue_settings_default_save_and_log_in_the_organization_section`, `test_revenue_settings_out_of_range_or_of_the_wrong_kind_are_refused`) |
| C3 | A record holds an amount, an amount with a reason, or a reason alone; a note only with Other | DN-B14-3; `docs/04` 13.5 | `0011_revenue.sql:19-24` (`ck_records_entry`), `ck_records_amount` of `0006` | holds | A (`tests/db/test_constraints.py` rows, capture tests) |
| C4 | "Below 4,000" counts low and no-revenue days; a low day counts in every total | DN-B14-4 | `vehicle_week.sql:37-43`; `revenue_week_get.sql:152-160` | holds | A (`test_below_threshold_days_count_low_and_no_revenue_days`, `test_low_days_are_judged_by_their_amount_against_the_threshold`) |
| C5 | Capture fills a day with no record; correct changes a saved one, today's included | DN-B14-5 | `revenue_capture.sql:145-150` | holds | A (`test_capture_fills_and_correct_changes`, released-client 403 row) |
| C6 | A cell the person cannot change is not editable (rights and the back-dating limit) | DN-B14-6 | `cell.sql:38-44` | holds | A (`test_who_may_open_a_cell_follows_its_status_day_and_limit`, `test_capture_fills_and_correct_changes`) |
| C7 | The gap is revenue less the day targets of the days that count so far | DN-B15-1 | `vehicle_days.sql:72`; `vehicle_week.sql:50`; `revenue_week_get.sql:212` | holds | A (`test_the_gap_counts_the_days_so_far`, `test_the_week_carries_the_gap_and_its_band`) |
| C8 | Green at or above target, amber within the band, red beyond; no band when nothing is expected | DN-B15-2 | `gap_band.sql` | holds | A (`test_gap_band`, edges at exactly 10 per cent) |
| C9 | R01 carries the headline figures, the settings in force, fleet numbers; every whole-grid figure covers only what the viewer may see | DN-B15-3; `docs/06` 2.12 R01; `docs/14` D1 | `revenue_week_get.sql:83-93`, `:152-160`, `:185-216` | holds after V-D10-1 | A after the fix (before: B, no scoped assertion on the four new figures) |
| C10 | A cell's `expected` is that day's target | DN-B15-4 | `cell.sql:34`; `vehicle_days.sql:68-71` | holds | A (`test_the_week_carries_the_gap_and_the_day_targets`, `test_vehicle_days_agree_with_the_setup_predicates_day_by_day`) |
| C11 | Capture and change are checked against the back-dating limit on the record's date, after the permission and before the version | DN-B12-5; `docs/05` 10.2, 10.5 step 7b | `revenue_capture.sql:152-154` | holds | A (`test_capture_and_change_respect_the_back_limit`) |
| C12 | An offline replay is checked at its capture time, held to now and 72 hours back; a v2.11 replay at the request | DEC-12 | `revenue_capture.sql:152-154`; `SaveRevenue.captured_at` (aware only) | holds | A (`test_an_offline_replay_is_checked_at_its_capture_time_within_72_hours`, `test_the_capture_time_is_read_on_the_organizations_calendar`, API naive-time refusal) |
| C13 | An identical replay is answered `replayed` whatever the date, threshold, limit or rights | `docs/05` 10.5 paragraph after the table | `revenue_capture.sql:109-114` before `:116` | holds | A (`test_an_identical_replay_is_answered_whatever_the_threshold`, `..._whatever_the_limit`, released-client retry row) |
| C14 | The search matches registration or fleet number, escaped, at most 40 characters, before paging | DN-B10-4; `docs/05` 10.5 | `revenue_week_get.sql:72-75`, `:88` | holds | A (`test_the_week_search_matches_registration_or_fleet_number` db and api; escape probe, section 8) |
| C15 | R02 is gated by `dash.net` or `dash.gaps`, each card by its own right | `docs/05` 10.5 | `revenue_dashboard_get.sql:41-45`, `:92-99` | holds | A (`test_each_card_needs_its_own_permission`) |
| C16 | `docs/05`, `docs/06` and `docs/09` describe what was built, and the next prompt cannot read them into a weaker build | `docs/14` D11 | the documents | fails, corrected | V-D11-1, V-D11-2 |
| C17 | The old signatures are dropped and the contract version is 5 | `docs/05` 10.5 | `0011_revenue.sql:6-13`; `meta_contract_version.sql` | holds | A (`tests/db/test_ops_routines.py` contract test in row 7; `db verify` section 8) |
| C18 | The revenue settings are the Owner's, logged once in the `organization` section with `{CUR} {amount}` and `{n} per cent` | `docs/05` 10.5 last rows | `organization_settings_set.sql:364-394`; `setting_word.sql`, `setting_value.sql` | holds | A (`test_only_owners_change_the_revenue_settings`, `test_the_revenue_settings_are_read_and_saved_by_the_owner`) |
| C19 | A v2.11 phone's capture, replay and week read keep working; the deliberate changes answer with a sentence | prompt invariant; `docs/15` section 4; question 66 | the routines above; `http/schemas/revenue.py` field order | holds | A (`test_a_v211_phone_captures_and_replays_its_queue`, `..._reads_the_week_with_a_low_day_on_it`, `test_what_a_v211_phone_can_no_longer_save_answers_with_a_sentence`, session keys) |
| C20 | Every figure is computed in SQL; Python maps documents only | prompt D4 | `db/routines/revenue.py`, `http/schemas/revenue.py` (no arithmetic) | holds | B (read; the API tests read figures only SQL computes) |
| C21 | Every `Raises:` code of a changed routine has a test, and every routine is in `docs/05` | `docs/14` D10; `tests/unit/test_routine_catalogue.py` | headers | holds | A (`test_raises_matches_the_refusals_of_the_body`, `test_every_routine_and_helper_is_named_in_the_routine_document`, name grep) |
| C22 | The fakes match the routines | `tests/support/revenue_cases.py` | `FakeRevenueRepository` | holds | A (`test_fakes_match_routines.py` 663 passed in row 7, the revenue protocol case and `capture_a_week` among them) |
| C23 | The README status and the earlier reports are current | `docs/14` D11 | `docs/prompts/README.md` row 07b | fails, corrected | V-D11-3 |
| C24 | Capture and the revenue settings save cannot deadlock | `docs/14` D3 | lock order (section 4, D3) | unproven | C (analysis: the save locks the organization row then upserts the settings row; capture never locks the settings row and takes the organization row last) |
| C25 | Lint, format and types clean; `db verify` exit 0; no TODO or plan identifiers; the full suite green | prompt invariants | | holds for D4 | A (section 8: ruff and ruff format clean, mypy clean on 189 files, `db verify` 21 of 21, sweeps empty; the full suite completed with every D4 module green, its 3 failures D1's) |

## 3. Findings

| Field | V-D10-1 |
|---|---|
| mode | falsification, red team (clerk in tenant A) |
| claim attacked | C9 and `docs/14` D1 "hidden vehicles do not leak through totals, counts..."; the D4 build report's V-D4-4 ("the week search shows only what the viewer may see", conceded) |
| challenge | A routine that computes D4's new whole-grid figures (`gap`, `gap_band`, `below_threshold_days`, `missing_days`) without `setup.visible_vehicles()`, or appends the search unparenthesised after the other filters, shows a company-scoped clerk fleet-wide figures and lists a hidden vehicle by its registration or fleet number. Expected: some test fails. Actual: every test passed. |
| evidence | `tests/db/test_revenue_routines.py::_figures` compared six figures, none of D4's four; no test ran `q` as a scoped viewer. Mutation trees in the scratchpad (section 8): the narrow search slip (`mutA`) and the new figures over every vehicle of the organization (`mutB`): the unchanged file passed 9 of 9 selected tests on each. The D4 report's V-D4-4 cites `test_the_week_search_matches_registration_or_fleet_number`, which only the Owner runs. |
| refutation tried | Read the routine: the search sits inside the parenthesised filter with `setup.visible_vehicles()` (`revenue_week_get.sql:83-93`), and the four figures come from the `days` CTE over `v_grid`, so today's code is right. The cross-tenant half of the challenge is defeated: `api.*` routines run as `xcode_api_executor`, which row-level security binds (`docs/03-database.md` roles table), and the cross-tenant assertions alone passed on `mutA`. A broader slip that also detaches the week clause is caught today by `test_an_actor_of_another_organization_is_not_a_member` (first `mutA`, 1 failed). The scoped half survives: scope is routine logic, not a policy. |
| verdict | survives, major (a missing test for a tenancy-scope claim) |
| synthesis | fixed with tests: `_figures` gains the four keys, the whole-grid test pins their values (`gap` -4800, `red`, 1 low day, 4 missing days, worked from `_history` by hand), and `test_the_search_finds_only_vehicles_the_viewer_may_see` (scoped clerk by registration and fleet number; another organization finds and counts only its own). Fail-first on both mutations, 92 passed on the unmutated copy; landed at 20:39 and the module rerun on the live tree, 92 passed; `docs/09` 4.1 DN-B10-4 row names it |

| Field | V-D11-1 |
|---|---|
| mode | pre-mortem, Socratic |
| claim attacked | C16; DN-B12-5 ("applies to capturing or changing revenue"); `docs/05` 10.2 ("the writes that call it are exactly those of DN-B12-5: `api.revenue_capture` ...; prompt 08b the central expense add and edit") |
| challenge | The 08b build of `PUT /setup/revenue/day/{date}` (the route the web's fleet-day dialog saves through, `apps/web/lib/endpoints/revenue.ts` `saveFleetDay`) follows its prompt: "the same replay, conflict and earliest-missing rules as the single-cell capture where the .NET code shares them". .NET's `Apply` (`apps/api/Application/RevenueUseCases.cs:105-127`) has no threshold, no back-dating check, needs `revenue.no_earnings` for a reason and lets capture change today's record. `docs/05` 2.4 and 4.7 and `docs/06` 2.8 still state 07's rules with no pointer to 10.5 and 2.12. Expected: the documents make each row run D4's steps. Actual: nothing says so, and 10.2 lists the callers as "exactly" a set without the day capture. |
| evidence | `docs/prompts/08b-expenses-reports.md:172-174` and `:42-45` (B12 named for central expenses only); `docs/05-routines.md` 10.2 callers paragraph, 2.4 and 4.7 headings; `docs/06-http-contract.md` 2.8 |
| refutation tried | Looked for any document that applies B12 or B14 to the day capture (`docs/15`, `docs/05`, `docs/06`, `docs/12`, `docs/13`, the 08b prompt): none. `docs/12` row "The back-dating limit holds on the server ... in every write of DN-B12-5" is right in principle but names no route. |
| verdict | survives, major (documentation that would make the next session build the wrong thing: a second revenue write without the back-dating limit) |
| synthesis | documents corrected: `docs/05` 10.2 names the day capture and says each row runs `api.revenue_capture`'s steps, .NET deciding only the batch; one pointer sentence each under `docs/05` 2.4 and 4.7 and after `docs/06` 2.8 and 2.9. Told the 08b designer (revenue-ff, 08b D0, 18:40), who agreed and amends the 08b prompt's day-capture bullet itself, with D4's per-row body moved into one helper for both routes |

| Field | V-D11-2 |
|---|---|
| mode | falsification |
| claim attacked | `docs/09` 4.1 DN-B9-2 row |
| challenge | The row cites `tests/db/test_revenue_helpers.py::test_vehicle_days_agree_with_day_target`; no such test exists |
| evidence | script over every `::test_` reference in `docs/09`, `docs/12`, `docs/05`, `docs/15`, `docs/13` against the test names (section 8): the only miss in D4's rows |
| refutation tried | The test that carries the rule is `test_vehicle_days_agree_with_the_setup_predicates_day_by_day` (it compares `revenue.vehicle_days` with `setup.day_target` day by day) |
| verdict | survives, minor |
| synthesis | document corrected |

| Field | V-D11-3 |
|---|---|
| mode | Socratic |
| claim attacked | C23; `docs/prompts/README.md` status row 07b |
| challenge | The status row still ends "D4 not started" while the register rows B14 and B15 say "built 2026-10-12" |
| evidence | `docs/prompts/README.md:27` |
| refutation tried | none possible; the builder updated the register rows only |
| verdict | survives, minor |
| synthesis | document corrected: revenue-d5, then coordinator, replaced "D4 not started" with the D4 build at 20:42. This report's verdict is not added: the file changed less than 30 minutes before the report closed (20:49), so the clause is in section 10 for the next edit |

Notes (no failure scenario in the scope, or outside it):
- N-1: the OpenAPI document lists `422` on R01 to R03 and the settings routes, which answer 400
  (FastAPI's default validation response). Known app-wide as 06:V-D4-3; owner prompt 09.
- N-2: `.github/workflows/xcode-api.yml` is untracked, so CI has never run; it uses
  `postgres:18` while the development cluster is 16.15. D4 uses no feature newer than 14.
  Owner: the user (commit the workflow).
- N-3: a settings value of the kind `decimal` (the two revenue settings) must be a JSON number:
  `"4000"` answers `settings_wrong_type`, while `docs/06` 1.2 says numeric strings in input are
  accepted. The integer settings of the older sections behave the same way, so this is the
  settings convention, not a D4 slip. Owner: prompt 09 (one clause in `docs/06` 1.2).
- N-4: `counted` is "in the fleet and before the business date, or recorded". When an Owner
  holds the business date back, a record already saved on a later day counts in the totals and
  the gap while its cell says `future`. The definition is 07's, and no client can create such a
  record while the date is held. Owner: none (recorded).

## 4. Per domain

D2 (identity and sessions) is `n/a`: D4 changes no identity routine, token or sign-in path.
D9 is covered by N-2 only (no dependency, host or secret change in D4).

D1 Tenancy and authorization
| Probe | Verdict | Evidence |
|---|---|---|
| enter_organization before the first tenant read | holds | `revenue_capture.sql:62`, `revenue_week_get.sql:58`, `revenue_dashboard_get.sql:39`, settings get/set; `db verify` "tenant routines enter their organization" (section 8) |
| new tenant table with RLS and the policy | holds | `tenancy.organization_revenue_settings` (`0011_revenue.sql:39-42`); `schema_spec.py:96` puts it in the parametrized isolation tests (29 tenant tables) |
| scoped viewers: totals, counts, search | holds after V-D10-1 | `test_a_scoped_viewer_counts_only_the_vehicles_they_may_see` with the four figures; `test_the_search_finds_only_vehicles_the_viewer_may_see` |
| `{id}` routes answer 404 for a foreign or hidden vehicle | holds | `test_an_actor_of_another_organization_is_not_a_member`, `test_an_unknown_or_unseen_vehicle_is_not_found_before_the_date_is_read` |
| anti-escalation (settings are the Owner's) | holds | `test_only_owners_change_the_revenue_settings`; O02 403 in `test_the_revenue_settings_are_read_and_saved_by_the_owner` |
| catalogue: a v2.11 phone keeps `revenue.no_earnings` | holds | `docs/15` 3.4 row; `test_the_session_keeps_the_keys_a_v211_phone_gates_on` (clerk and Office admin rows) |

D3 Data integrity and concurrency
| Probe | Verdict | Evidence |
|---|---|---|
| version bumped and compared; 409 with `current` | holds | capture unchanged from 07 (`revenue_capture.sql:156-180`); `test_a_stale_version_is_a_conflict_carrying_the_stored_cell` |
| lock order | unproven (C24) | analysis only, section 2 |
| replays rest on a unique constraint | holds | `test_two_first_captures_of_a_day_race_to_one_record_and_a_unique_conflict` |
| append-only tables | n/a | no new append-only table |
| money types and rounding | holds | threshold `numeric(14,2)` with `ck_revenue_settings_low_day_threshold`; sums plain `numeric`; `round(..., 2)` once per figure |
| one call one transaction; only reads retried | holds | `db/routines/revenue.py` (`idempotent=True` on the reads only) |

D4 Contract parity
| Probe | Verdict | Evidence |
|---|---|---|
| routes in .NET, `docs/06`, the routers and OpenAPI | holds | route sweep (section 8): the revenue rows agree in method, path, operationId and tag; the .NET-only revenue routes are `/day` and `/export`, drift rows 3 and 4 (08b) |
| bodies: order, nullability, numbers | holds | new fields last (`RevenueVehicleDto`, `RevenueWeekDto`, `SaveRevenue`, `OrganizationSettingsResponse`); `test_the_week_in_wire_order_with_its_cells_and_figures` |
| errors: sentences and statuses | holds | `tests/unit/test_messages.py` pins `docs/06` section 3 to `http/messages.py` both ways |
| clients | holds | mobile `queue.ts:89-101` accepts a `current` cell with amount and reason; v2.11 rows in `test_contract_released_clients.py` |
| drift | holds | no commit to `apps/api` or `tests/api` since 2026-10-11; the uncommitted `RevenueEndpoints.cs` change is `/export` (drift row 4) |

D5 Domain rules and time
| Probe | Verdict | Evidence |
|---|---|---|
| business date from the organization zone and `p_now` | holds | sweep: no `now()`, `current_date`, `clock_timestamp()` in `db/routines`; `test_bodies_raise_only_through_refuse_and_never_read_now` |
| midnight, zones, month ends | holds | `test_the_capture_time_is_read_on_the_organizations_calendar` (Nairobi, New York); month arithmetic is D2's `tests/db/test_back_limit.py` |
| automatic reasons | holds | `Recorded revenue for KDA 482M on 9 Oct 2026: Garage`; `Changed the low-day threshold to KES 3,500.50 and the amber band to 10 per cent` (tests) |
| normalisation | holds | reason spellings as .NET, case-sensitive (`test_reason_spellings_are_the_labels_with_or_without_their_space`) |

D6 Database craft
| Probe | Verdict | Evidence |
|---|---|---|
| `db verify` exit 0 | holds | the CLI database `xcode` after `db routines` (268 files): exit 0, 21 of 21; contract version 5; no older `api.revenue_*` overload (section 8) |
| `SECURITY DEFINER` with `search_path`; no `PUBLIC` execute | holds | sweep: none missing; `gap_band`, `cell`, `vehicle_week`, `check_revenue_settings` revoke `PUBLIC`; the runner grants `api.*` (`migrate.py` `_fix_api_routine_grants`) and `db verify` checks `PUBLIC` |
| no dynamic SQL | holds | sweep: no `EXECUTE` or `format(` in `db/routines` |
| migrations: forward-only, reviewed down | holds | `0011_revenue.down.sql` states what it loses (a low day's reason) |
| an index per query | holds, note | the settings row by primary key; the search is an `ILIKE '%q%'` scan of one organization's vehicles (hundreds), as the D4 report's pre-mortem 4 says |
| features newer than the oldest supported PostgreSQL | holds | none newer than 14 (`trim_scale` 13, multiranges 14 in 07's `earliest_missing`) |
| the template matches the files tested | holds | `xcode_template_d4full` comment `4b6cf4cc...e9dd314` equals `template_fingerprint(db/)` during the run and again at 20:41 (no file under `db/` newer than 17:35) |

D7 Performance
| Probe | Verdict | Evidence |
|---|---|---|
| statement budgets | holds | `tests/api/test_revenue.py` `statements(...)` on capture (2), week, paging |
| no query per row | holds | D4 adds function calls (`revenue.gap_band`) and counters per vehicle, no query |
| `EXPLAIN` at 10x | n/a at this depth | D4 adds one filter to the vehicle scan and integer counters to existing loops; 07's plan work stands |

D8 Reliability and operability
| Probe | Verdict | Evidence |
|---|---|---|
| logs carry no body, phone, PIN, code or token | holds | no log call in the revenue modules or the settings schemas |
| `XCODE_*` names in four places | holds | the four grep hits (`ALLOW_REQUIRE_SSLMODE`, `POOL_MAX`, `EMAIL_FROM`, `EMAIL_PORT`) are written in short or field form in `docs/08` and `test_settings.py` |

D10 Tests as evidence
| Probe | Verdict | Evidence |
|---|---|---|
| no fake of the capability under test | holds | the rules are proven in `tests/db`; the fake is checked by the parity case |
| skip, xfail, sleep, bare except in the scope's tests | holds | none in the revenue modules (sweep; `# fmt: skip` only) |
| a test named after a rule distinguishes it | holds after V-D10-1 | D4's mutations A1 to A11, B, C, D (its report) and this report's `mutA`, `mutB` |
| every `Raises:` code has a test | holds | C21 |
| the full suite ran once on a fresh template | holds | row 7: `xcode_template_d4full` from the live tree, 5736 tests in 1:55:20, 5733 passed, 3 failed (D1's); every D4 module green (section 8) |

D11 Documents and prompts
| Probe | Verdict | Evidence |
|---|---|---|
| documents match the code; references resolve | fails, corrected | V-D11-1, V-D11-2 |
| status and earlier reports current | fails, corrected | V-D11-3; the D4 report's V-D4-4 conceded on evidence that does not distinguish (section 9) |

## 5. Per mode

Assumption inventory
| Assumption | Where stated | Enforced by |
|---|---|---|
| The search stays inside the viewer's vehicles | D4 report V-D4-4 | `revenue_week_get.sql:83-93`; a test only since V-D10-1 |
| An entry already stored is answered the same whatever the setting says now | `docs/05` 10.5 | step order `revenue_capture.sql:109-116`; tests |
| `api.*` routines read under row-level security | `docs/03` roles table | ownership by `xcode_api_executor`; the cross-tenant part on `mutA` |
| The 08b day save repeats the capture's per-row checks | drift register row 3 | nothing before V-D11-1's documents |
| A v2.11 phone keeps its reason buttons | `docs/15` 3.4 | `tenancy.permission_sources` row; session-keys test |

Falsification: the claims table of section 2 (falsifier per claim in its evidence column).

Pre-mortem (three months after cutover)
1. The web's fleet-day save lets a clerk limited to "today only" change last week's revenue, and
   a low day is saved without a reason; found when an auditor compares the change log with the
   limits. Inversion: guaranteed if the documents send the 08b builder to .NET for the per-row
   rules. That condition existed; corrected (V-D11-1).
2. A refactor (08b's export reusing the week) drops the visibility filter from one new figure; a
   scoped clerk's "Below 4,000" shows the fleet's. Nothing would notice; now the tests would
   (V-D10-1).
3. An Owner raises the threshold mid-week and "Below" moves for days already saved. As
   designed (`docs/05` 10.5); the label shows the current threshold.
4. v2.11 phones keep low days as not saved (question 66, accepted); early sign `missingDays`.

Red team
| Persona | Vector | Defence or gap |
|---|---|---|
| clerk | searches a hidden vehicle's registration or fleet number | the filter; a test since V-D10-1 |
| clerk | another tenant's registration through `q` and `totalVehicles` | row-level security for `xcode_api_executor` (conceded) |
| clerk | a low amount for a hidden vehicle to learn the threshold or the vehicle's existence | 404 comes first (`test_the_threshold_is_checked_after_the_vehicle_and_before_the_date`) |
| gamer | `capturedAt` 72 hours back to write past a "today only" limit | DEC-12 residual risk, `docs/12` section 7, owner product |
| dismissed employee | replays the old queue after deactivation | `not_member` before anything (07's tests) |
| calendar | a capture at 00:30 Nairobi, 21:30 UTC | `test_the_capture_time_is_read_on_the_organizations_calendar` |
| hurried DBA | runs `0011` down on real data | the down file states it drops a low day's reason |

Dialectic
| Decision | Strongest counter | Verdict |
|---|---|---|
| The threshold after the identical replay | refusing a low amount first gives a cleaner order | kept: a released phone must see a stored entry as stored |
| DEC-12's 72-hour clamp | ignore `capturedAt`; a lying clock gains three days | kept, residual risk recorded |
| "Below" judged by the amount against today's threshold | judge by the stored reason, frozen at save time | kept: the label names today's threshold, and reason-only days always count |
| Section 10 of `docs/05` as an overlay on 2.4 and 4.7 | rewrite 4.7 so one table is true | changed in part: pointers added (V-D11-1); the overlay stays, as D2 and D3 left theirs |

## 6. Conceded

| Challenge | Guard that defeated it |
|---|---|
| v2.11 phones lose the no-revenue buttons when `revenue.no_earnings` is retired | derived from `revenue.capture` or `revenue.correct` (`docs/15` 3.4); `test_the_session_keeps_the_keys_a_v211_phone_gates_on` |
| a search slip counts another tenant's vehicles | `api.*` routines run as `xcode_api_executor` under row-level security; the cross-tenant assertions passed on `mutA` |
| a broad slip that also detaches the week clause | `test_an_actor_of_another_organization_is_not_a_member` failed on it |
| `%`, `_` or a trailing backslash in `q` lists everything or errors | the escape probe on PostgreSQL 16 (section 8) |
| a retry of an entry saved before the rule or under another threshold is refused | the replay precedes the threshold; tests and the released-client row |
| stale overloads keep a wider grant | `0011` drops the four old signatures; `db verify` checks `PUBLIC` |
| `Infinity` or `1e999` in a settings body becomes a 500 | `_finite` in `http/schemas/organization.py`; `test_a_settings_number_no_json_holds_is_refused_before_the_routine` |
| an amount of 0 with a reason is refused as money | it becomes the reason alone (`revenue_capture.sql:75-77`); `test_a_low_day_needs_a_reason` |
| the 409 `current` of a low day breaks the v2.11 queue | `validSaved` accepts an amount with a reason; `test_a_v211_phone_reads_the_week_with_a_low_day_on_it` |

## 7. Fixes

| Finding | Files changed | Test that failed before and passes now |
|---|---|---|
| V-D10-1 | `tests/db/test_revenue_routines.py` (`_figures`, the whole-grid test's exact figures, the new test) | `::test_the_search_finds_only_vehicles_the_viewer_may_see` failed on `mutA` (the scoped clerk's search listed the hidden KDA 482M) and on `mutB` (a gap of -4800 on an empty search); `::test_a_scoped_viewer_counts_only_the_vehicles_they_may_see[companies|vehicles]` failed on `mutB`; all pass on the routines as built (92 of 92 in the scratchpad copy, and 92 of 92 on the live tree after landing, 20:46) |
| V-D11-1 | `docs/05-routines.md` (2.4, 4.7, 10.2), `docs/06-http-contract.md` (2.8, 2.9); the 08b prompt by revenue-ff | documents |
| V-D11-2 | `docs/09-testing.md` 4.1 (DN-B9-2 and DN-B10-4 cells) | documents |
| V-D11-3 | `docs/prompts/README.md` status row 07b (D4 clause): written by revenue-d5 at 20:42 under its coordinator role; the verdict clause of section 10 not yet added (30-minute rule) | documents |

## 8. Commands and outputs

Environment, measured in this session (20:43):

```
python --version                       Python 3.13.2 (.venv); psycopg 3.3.6, fastapi 0.142.4, pydantic 2.13.5
select version()  (127.0.0.1:5433)     PostgreSQL 16.15, compiled by Visual C++ build 1944, 64-bit
.github/workflows/xcode-api.yml        image: postgres:18 (file untracked, never run: N-2)
git status --short .                   ?? ./  (apps/api-python untracked as a whole)
```

Orientation (17:53): D4 landed at 17:12 and its full run (queue row 7) had frozen `src/`, `db/`
and `tests/` since 17:35, so the reading pass changed nothing in the live tree; no file in scope
changed in the 30 minutes before it. `tests/db/test_revenue_routines.py` was byte-identical to
its 17:11 copy when the test fix landed (20:39, `cmp`).

The full run (queue row 7, revenue-d5's, read from its `full.log` and `full.xml`):

```
template   xcode_template_d4full, built 17:35 from the live tree; its comment
           4b6cf4cc31b9ff4689e5f5d1521a288843614590a535988da058b8457e9dd314 equals
           template_fingerprint(db/) during the run and again at 20:41 (no file under db/ newer than 17:35)
pytest -n 2, started 17:35:41
           3 failed, 5733 passed, 4 warnings in 6920.82s (1:55:20)
failed     tests/db/test_gateway.py::test_identity_routines_map_every_outcome_with_one_statement_each
           tests/db/test_gateway.py::test_verify_device_maps_through_the_gateway
           tests/db/test_gateway.py::test_ops_routines_map_the_operator_routines
           (D1's drift: CodeCheck and DeviceVerification take `now`, ClearedPause has `was_locked`
           not `was_paused`; reported at 16:06 by verify-07b-d2, owner the next D1 session; not D4's)
modules    (junit tally, passed/failed)
           tests.db.test_revenue_routines 91/0       tests.db.test_revenue_helpers 63/0
           tests.api.test_revenue 39/0               tests.api.test_contract_released_clients 32/0
           tests.db.test_fakes_match_routines 663/0  (revenue: the protocol case and capture_a_week)
           tests.db.test_organization_routines 340/0 tests.api.test_organization_settings 20/0
           tests.db.test_constraints 59/0            tests.db.test_grants 77/0
           tests.db.test_schema_structure 39/0       tests.db.test_tenancy_isolation 97/0
           tests.db.test_migrate 18/0                tests.db.test_ops_routines 64/0
           tests.db.test_routine_headers 1342/0      tests.db.test_message_codes 6/0
           tests.unit.test_messages 428/0            tests.unit.test_routine_catalogue 2/0
           tests.api.test_openapi 5/0                tests.db.test_gateway 16/3
```

Sweeps (`db/routines`, `src`, `tests`; 20:43):

```
now()/current_date/clock_timestamp()/random()/statement_timestamp() in db/routines   none
EXECUTE / format( in db/routines             162 lines, every one a GRANT or REVOKE EXECUTE; no EXECUTE statement
SECURITY DEFINER without SET search_path     none
REVOKE ... FROM PUBLIC                       gap_band, cell, vehicle_week (multi-line), vehicle_days, percent,
                                             check_revenue_settings
skip/xfail/importorskip/sleep/bare except    none in test_revenue_routines, test_revenue_helpers, api/test_revenue,
                                             support/revenue_cases, api/test_organization_settings
TODO/FIXME/HACK/plan or finding identifiers  none (two "+254XXXXXXXXX" phone formats only)
log calls in the revenue and settings code   none
```

Routes (`xcode-api openapi` against the live tree, compared with `apps/api/Api/*.cs` and `docs/06`):

```
GET  /setup/revenue                    GetRevenueWeek       weekStart, companyId, vehicleId, page, pageSize, q
                                                            200 400 401 403 404 422
GET  /setup/revenue/dashboard          GetRevenueDashboard  period, companyId   200 400 401 403 422
PUT  /setup/revenue/{vehicleId}/{date} SaveRevenue                              200 400 401 403 404 409 422
GET  /setup/organization/settings      GetOrganizationSettings                  200 400 401 403
PUT  /setup/organization/settings/{section}                                     200 400 401 403 404 409 422
in Python, not docs/06                 none
in .NET, not Python (revenue)          GET /setup/revenue/day, PUT /setup/revenue/day/{date}, GET /setup/revenue/export:
                                       prompt 08b's, not D4's
422 listed on every route              N-1
```

Search escaping (`escape_probe.py`: the routine's own `v_pattern` expression, read from
`revenue_week_get.sql`, evaluated on PostgreSQL 16.15 with `standard_conforming_strings` on;
Python reprs, so `\\` is one backslash):

```
routine expression: '%' || replace(replace(replace(q.v, '\', '\\'), '%', '\%'), '_', '\_') || '%'
'\\'    -> '%\\\\%'    matches ['KDA 4\\82']
'A 4\\' -> '%A 4\\\\%' matches ['KDA 4\\82']
'4\\8'  -> '%4\\\\8%'  matches ['KDA 4\\82']
'_'     -> '%\\_%'     matches ['A_7%']
'%'     -> '%\\%%'     matches ['A_7%']
'a_7'   -> '%a\\_7%'   matches ['A_7%']
'kda'   -> '%kda%'     matches ['KDA 4\\82', 'KDA 482M']
```

Fail-first for V-D10-1 (scratchpad copies beside row 7, 18:44 to 19:03, `-n 0`, one private
template per tree, each started at 0.5 GB free or more; `-k "whole_grid_figures or pages_list or
truncated or scoped_viewer or company_filter or search or another_organization"`):

```
mutA  the search line moved after the visibility CASE, unparenthesised (OR binds the search to one branch)
      old tests      9 passed
      new tests      FAILED test_the_search_finds_only_vehicles_the_viewer_may_see (the scoped clerk's
                     search for "KDA" lists KDA 482M); its cross-tenant part passes (row-level security)
mutB  an `everyone` CTE without the visibility filter feeds gap, gap_band, below_threshold_days, missing_days
      old tests      9 passed
      new tests      FAILED test_a_scoped_viewer_counts_only_the_vehicles_they_may_see[companies]
                     FAILED test_a_scoped_viewer_counts_only_the_vehicles_they_may_see[vehicles]
                     FAILED test_the_search_finds_only_vehicles_the_viewer_may_see (gap -4800 on an empty search)
snap  the routines as built, strengthened module    92 passed in 9:33
```

The landed module on the live tree (20:40, `-n 0`, `xcode_template_vd4` built from the live
tree, 0.76 GB free, no other job, the cluster otherwise empty):

```
tests/db/test_revenue_routines.py   92 passed in 309.39s (0:05:09); xcode_template_vd4 dropped 20:46
```

Lint, types and the CLI database:

```
ruff check .                         All checks passed!
ruff format --check .                401 files already formatted
mypy                                 Success: no issues found in 189 source files
xcode-api db status  (before)        applied 0001-0012, pending none; routine drift
                                     ['55_pettycash/pettycash_entry_create.sql'] (verify-08's 17:15 fix)
xcode-api db routines                exit 0, applied 268 routine files; two orphan warnings, the known old
                                     overloads api.auth_sign_in (8 arguments) and api.people_list (6 arguments)
xcode-api db verify                  exit 0, 21 of 21 ok
xcode-api db status  (after)         routine drift none, migration checksum drift none
api.meta_contract_version()          5
api.revenue_* signatures             revenue_capture(uuid,uuid,text,uuid,date,numeric,text,text,bigint,timestamptz,timestamptz),
                                     revenue_dashboard_get(uuid,uuid,text,text,uuid,timestamptz),
                                     revenue_week_get(uuid,uuid,text,date,uuid,uuid,integer,integer,text,timestamptz);
                                     no older overload
```

Test references in the documents (`testrefs.py`: every `::test_` name in `docs/05`, `docs/09`,
`docs/12`, `docs/13`, `docs/15` against the `def test_` names under `tests/`, 20:47):

```
references 211; before the fix the only miss in D4's rows was DN-B9-2's
test_vehicle_days_agree_with_day_target (V-D11-2, corrected). 16 misses remain, all tests that
prompt 08b's design names and its build will write (docs/05 section 11, docs/12 the 08b rows,
docs/09 drift row 7's shared purchase); none is D4's
```

## 9. Regressions and misses against earlier audits

Read after this pass: `docs/audit/2026-10-12-build-07b-d4.md` and
`docs/audit/2026-10-12-verify-area-prompt-07.md`.
- Regressions: none. verify-07's fixes hold in the D4 tree: the vehicle read `FOR SHARE`
  (`revenue_capture.sql:91-94`), `_to_decimal` and its test, and the HTTP 409 without `current`
  (`test_a_day_another_save_holds_is_a_409_without_current`).
- Missed by the D4 build report: V-D10-1 (its V-D4-4 conceded the scoped search on a test the
  Owner alone runs), V-D11-1 (its section 5 lists 08b's export and savings rule, not the day
  capture's per-row rules), V-D11-2, V-D11-3. The D4 builder recorded V-D4-4's weaker evidence
  in its report after the full run (`docs/audit/2026-10-12-build-07b-d4.md`, below its section 4
  table, 20:39), and corrected the README status row at 20:42.

## 10. For the user

- Commit `.github/workflows/xcode-api.yml` so CI runs at all (N-2). Recommendation: commit it with
  the image pinned to the PostgreSQL the host will run; until then only the local 16.15 is
  measured.
- Give D1's three `tests/db/test_gateway.py` failures to the next D1 session (they are the only
  failures of the full run; the test was not adapted to D1's `now` argument and `was_locked`).
- `docs/prompts/README.md` status row 07b ends "verify-07b-d4 in progress". After 21:12 (the
  file changed at 20:42), replace it with: "verified 2026-10-12 in fix mode, pass with findings
  (`docs/audit/2026-10-12-verify-area-prompt-07b-d4.md`: no blocker; one major fixed with tests,
  a scoped viewer's search and whole-grid figures, which had none; one major and two minors
  corrected in the documents, among them that the 08b day capture runs the single capture's
  per-row rules)". Ask me to finish it, or let the next session that edits the row do it.
- Name the next coordinator of the board: revenue-d5 handed the role to this session at 20:45,
  the fallback revenue-17 [60bb7c] declined, and this session is at its budget.
