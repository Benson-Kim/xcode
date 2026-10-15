# Verify: prompt 03 (identity and tenancy routines), 2026-10-11

`SCOPE: area:prompt 03` · `MODE: fix` · `DEPTH: standard` · method `docs/14-verification.md`.
Run by a session that did not write the code (`verify-03` on `.coordination/board.md`), beside
three other sessions in the same tree (verify 04, verify 05, 07b D0). Edits only under
`apps/api-python/`. Times are local (EAT).

## 1. Verdict

**pass with findings.** No blocker. Two majors and three minors were found and fixed in this
run. The full suite then ran to completion: 4242 passed, 0 failed, 0 skipped (shared run 1,
22:34). It covers the tree as it stood at 21:31; a 07b D1 rewrite of three `src/` auth files
began at 22:35, after it.

- Claims (section 2): 24. holds 17, fails 5 (all fixed in this run), unproven 2, n/a 0, not
  checked 0.
- Surviving findings (section 3): blocker 0, major 2, minor 4, note 4.
- Fixed in this run, each with a test that failed first: both majors (V-D2-1 sign-in verdict
  race; V-D4-1 phone characters, raised by verify-04 as `04:V-D4-2` and taken here) and three
  minors (V-D5-1, V-D4-2, V-D10-1). One minor is a corrected document (V-D11-1). The four
  notes are residual risks recorded in `docs/12-security.md` section 7, or handed on.
- Probes (section 4): 40. holds 27, fails 6 (each fixed or recorded), unproven 2, n/a 3,
  not checked 2.

## 2. Thesis and claims

Thesis (steelmanned): prompt 03 delivers D1 to D9. The composite types, common, tenancy and
identity helpers, the eleven `api.auth_*` routines and the operator routines decide every
rule of sign-in, lockout, codes, devices, tokens and provisioning in SQL, in the check order
of `docs/07-auth.md` section 3; each routine serialises on the user row (or a `device:`
advisory lock), writes exactly one attempt row, checks token eligibility before changing
state and takes digests only; the gateway maps each routine one to one; the CLI commands
audit every action; and the behaviour equals the .NET code at `HEAD` 493bf82
(`SignInService.cs`, `AuthUnitOfWork.cs`, `UserProvisioning.cs`, `SetupContracts.cs`,
`PhoneNumber.cs`).

Grades follow `docs/14-verification.md` section 5. "A (run)" = a test against real
PostgreSQL passed in this run and its assertion was read.

| # | Claim | Code | Verdict | Grade |
|---|---|---|---|---|
| 1 | D1: four composite types, guarded `CREATE TYPE` | `db/routines/00_types/*.sql` | holds | B (read; re-run by every template build) |
| 2 | D1: `db/types.py` adapters | `db/types.py`; `test_gateway.py` | holds | A (run) |
| 3 | D2: helpers as `docs/05` 2.1 and `OS-11` | `10_common/*.sql` | fails: an automatic reason over 500 with no typed text came back unclipped (V-D5-1); fixed | A (run) |
| 4 | D2 evidence: `fmt_money` four values, `fmt_day`, `join_words` 1 to 4, `AutomaticReasonTests` strings | `test_tenancy_helpers.py:160-230` | holds | A (run) |
| 5 | D3: resolver (inactive empty, defaults + grants, transitive dependencies, denies, pruning) in one SQL function | `30_tenancy/assigned_permissions.sql`, `effective_permissions.sql` | holds | A (run; table of cases) |
| 6 | D3: `record_change` only writer, refuses without actor, two writers get distinct versions | `record_change.sql`; `test_two_concurrent_writers_get_distinct_versions` (two connections) | holds | A (run) |
| 7 | D3: `business_date` by zone (Nairobi, New York in daylight saving), held date; `check_time_zone` exact names | `business_date.sql`, `calendar_date.sql`, `check_time_zone.sql` | holds | A (run) |
| 8 | D4: phone table of `docs/07` section 1 | `normalize_phone.sql`, `domain/values.py` | fails: non-ASCII non-digits refused where .NET strips them (V-D4-1); fixed | A (run) |
| 9 | D4: `matching_code`, `code_caps`, `policy_for` clamps and no-row cases | `20_identity/*.sql`; `test_identity_helpers.py` | holds | A (run) |
| 10 | D5: eleven routines, check orders of `docs/07` section 3 | `20_identity/auth_*.sql` | fails for A01/A02: the decision trusted a PIN verdict computed against a hash read by an earlier transaction (V-D2-1); fixed. Other routines hold | A (run) |
| 11 | D5: lock the user row or the `device:` advisory lock before the first write | `lock_user.sql`, `lock_account.sql` | holds | A (`test_concurrent_wrong_pins_on_one_account_are_both_counted`, `test_revoking_a_device_waits_for_the_accounts_other_auth_work`) |
| 12 | D5: exactly one attempt row per routine call | every `auth_*` | holds per call; the document's "one row per decision" was wrong for an unknown number (two rows), corrected (V-D11-1) | A (run) |
| 13 | D5: token eligibility before any state change | `policy_for` checks in sign-in, verify-device, complete-pin, refresh | holds | A (`..._without_a_membership_..._nothing_changed`) |
| 14 | D5: business refusals are outcomes; only `XC401 session_invalid` raises | `identity.outcome`; `auth_resolve_session.sql` | holds | A (run) |
| 15 | D6: provisioning steps 1 to 10, .NET parity | `ops_provision_user.sql` vs `UserProvisioning.cs` | fails: `--role owner` refused, .NET matches ignoring case (V-D4-2); fixed. Rest holds | A (run) |
| 16 | D6: `api.ops_*` executable by `xcode_operator` only, `api.auth_*` by `xcode_app` only | runner grants | holds | A (`test_ops_routines.py` 42501 table, `test_grants.py`) |
| 17 | D6 evidence: each `Raises:` code tested | `test_ops_routines.py` | fails: `people_names_required`, `organization_name_slug` had no test (V-D10-1); tests added | A (run) |
| 18 | D7: one routine per method, idempotent only for the two reads, `XC401` to `SessionInvalid`, one statement per call | `db/routines/identity.py`, `ops.py` | holds | A (`test_gateway.py`) |
| 19 | D8: CLI commands, exit codes, operator row, no personal data | `cli/commands/users.py` | holds; a refusal is audited by a separate row (`users.py:123-133`) | B (read; `tests/api/test_cli.py` run, assertions not re-read) |
| 20 | D9: headers parsed; `Raises:` equals `refuse(` calls | `test_routine_headers.py` (922 cases) | holds | A (run) |
| 21 | Invariant: every `api.*` is `SECURITY DEFINER`, executor-owned, `search_path` set, no `PUBLIC` | catalogue | holds: 71 of 71 `SECURITY DEFINER`; every routine file sets `search_path` (178 of 178) | A (catalogue query + `db verify`) |
| 22 | Invariant: no `now()` in a routine body | `db/routines` | holds (grep: no `now()`, `current_date`, `clock_timestamp`, `random()`) | A |
| 23 | Invariant: no PIN, code or token in clear reaches the database | routine parameters | holds: only `*_hash` and `p_pin_length` | A (grep) |
| 24 | Invariant: lint, types, all tests green, `db verify` exit 0 | whole tree | holds: full run 1 4242 passed, 0 failed, 0 skipped (22:34); `ruff check`, `ruff format --check` (334 files), `mypy` (153 files) clean at 22:35; `db routines` and `db verify` (21 ok) exit 0 at 22:37 | A (run, section 8) |

Counts: holds 17 (2, 4, 5, 6, 7, 9, 11, 12, 13, 14, 16, 18, 20, 21, 22, 23, 24); fails 5 (3,
8, 10, 15 and 17, all fixed in this run; 17 was a test gap); unproven 2 (1 and 19 hold on
reading but stay at grade B); n/a 0; not checked 0.

## 3. Findings

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| V-D2-1 | red team (dismissed employee with the old phone) | `docs/07` 3.1, prompt D5: the sign-in decision is made under the user row lock | A01 runs two transactions: `api.auth_account_lookup` reads `pin_hash`, Python derives the verdict (about 0.3 to 1.2 s, longer when the PIN pool queues), then `api.auth_sign_in` locks the row and trusted `p_pin_ok`. A PIN reset (A07 to A09) that commits in between leaves the old PIN's verdict standing: someone holding the old PIN and a trusted phone gets 200 with a fresh 30-day refresh token after the reset meant to evict them (a reset trusts the completing device but does not revoke the others). Expected 401, as .NET verifies inside its per-account gate and SERIALIZABLE transaction (`AuthUnitOfWork.cs:15-27`, `SignInService.cs:13-15`) | `auth_sign_in.sql` (old lines 137, 159); `tests/api/test_auth_races.py::test_a_pin_reset_during_a_sign_in_voids_the_old_pins_verdict` answered 200 `authenticated` before the fix | looked for a version or hash check in `auth_sign_in`: none; checked the other flows: every other decision is one statement | survives, **major** (needs the old PIN, a trusted device and timing; the PIN pool queue widens the window) | **fixed**: `api.auth_sign_in` takes `p_checked_pin_hash` and treats the verdict as a wrong PIN unless it equals the locked row's `pin_hash` (`coalesce(p_pin_ok AND pin_hash = p_checked_pin_hash, false)`); a reset to the same PIN inside that window also counts as one wrong PIN (a new salt gives a new hash), which fails closed and costs the person one attempt; `PinVerdict.checked_pin_hash`, gateway, use case, fake and shared cases follow; `docs/05` 3.2 and `docs/07` 3.1 |
| V-D4-1 | falsification (raised by verify-04 as `04:V-D4-2`) | `docs/07` section 1 phone row; D4 phone table | .NET `PhoneNumber.Normalize` strips every non-digit (`Regex.Replace(value, @"\D", "")`, `apps/api/Domain/PhoneNumber.cs:29`); both twins refused any non-ASCII character, so `0712<U+00A0>345678` or a number wrapped in U+202A/U+202C (as Android apps copy it) was an unknown number on the web, which sends the field as typed | `normalize_phone.sql`; `PhoneNumber.parse`; `phone_vectors.py` pinned the refusal; both twins failed 7 corrected vectors before the fix (section 8) | the design said "non-ASCII digits are not a number" (`docs/07` section 10 row 5), which needs only the digits refused | survives, **major** (a released client path) | **fixed**: both twins strip every non-digit and still refuse a decimal digit outside 0-9 (an explicit Unicode 15.1 `Nd` list in SQL, `str.isdecimal` in Python); vectors corrected; a test over all 670 non-ASCII decimal digits; `docs/07` section 1 and section 10 row 5; question 67 resolved |
| V-D5-1 | falsification | `docs/05` 2.1 `compose_reason`, `OS-11` | .NET `Automatic(reason)` clips an automatic reason to 497 + `...` when no typed reason is given (`SetupContracts.cs:150,155`); `compose_reason` returned it whole, and `ck_change_log_reason` (500) would turn it into a 5xx | `compose_reason.sql`; new test failed with a 520-character result | every current caller's automatic text stays under 500 (names are capped at 100 to 200), so it is latent | survives, **minor** | **fixed** + `docs/05` row; `test_compose_reason_clips_a_long_automatic_reason_without_a_typed_one` |
| V-D4-2 | dialectic | `docs/07` section 9: provisioning "parity with `--provision-user`" | `--role owner` refused `people_role_unknown`; .NET looks roles up with `StringComparer.OrdinalIgnoreCase` (`AccessContracts.cs:104`) and stores the catalogue spelling. A test row pinned the refusal | `ops_provision_user.sql`; `test_ops_routines.py` row `("owner", "people_role_unknown")` | `docs/05` said "case-sensitive catalog names" without saying it departs from .NET | survives, **minor** (operator tool) | **fixed**: names matched ignoring case and stored as the catalogue spells them; the wrong row replaced by `test_provision_matches_the_role_name_ignoring_case` (proof: `AccessContracts.cs:104`); `docs/05` row |
| V-D10-1 | falsification | D6 evidence; `docs/14` D10 "every `Raises:` code has a test" | `people_names_required` and `organization_name_slug` of `api.ops_provision_user` had no test | grep over the scope's tests | none found | survives, **minor** | **fixed**: `test_provision_refuses_names_past_their_lengths` |
| V-D11-1 | Socratic | `docs/07` section 2 item 6, `docs/04` 3.5 "one row per authentication decision" | an unknown number leaves two rows: the lookup's (digest of the number) and `api.auth_sign_in`'s with no account (digest of the empty string) | `auth_account_lookup.sql:31`, `auth_sign_in.sql` step 1; `test_step_1_no_account_is_refused` | the prompt's invariant is per call, and the code meets it | survives, **minor** (document) | **document corrected** (`docs/07` 3.1 step 1) |
| V-D2-2 | red team (outsider with numbers) | `docs/07` section 1 code limits | the 5-an-hour, 10-a-day caps are per account across purposes; A07 needs only a number, so anyone can spend a person's daily budget and their next new-device sign-in gets no code for up to a day | `code_caps.sql` | parity: .NET counts the same way | survives, **note** | residual risk in `docs/12` section 7, owner product |
| V-D2-3 | pre-mortem (trail leaked) | `docs/04` 3.5 `phone_digest` | unkeyed SHA-256 over about 2 x 10^8 Kenyan numbers is reversed in minutes | `phone_digest.sql` | the documents never claim confidentiality | survives, **note** | residual risk in `docs/12` section 7, owner security |
| V-D8-1 | red team (operator) | `docs/12` section 2 "operators are identified" | `operator` is whatever `XCODE_OPERATOR` says; all operators share one role | `record_operator_action.sql`; `docs/08` | none | survives, **note** | residual risk in `docs/12` section 7, owner operations |
| V-D10-2 | pre-mortem | D10 "tests as evidence" | mypy checks `src` only (`pyproject.toml` `files = ["src"]`), so a dataclass change broke `tests/support/auth_cases.py` only at run time (99 failures in this run's first targeted pass, then fixed) | `pyproject.toml` | none | survives, **note** | for prompt 09 or the owners: add `tests` to mypy |

## 4. Per domain

Probes from `docs/14-verification.md` section 4, as far as prompt 03 reaches.

D1 Tenancy and authorization
- Tenant routines enter their organization: holds for the scope (the auth routines take no
  organization; `policy_for` and `auth_resolve_session` set it from `active_organization`);
  the `db verify` check rejects an `api.*` routine that takes `p_organization_id` without a
  `tenancy.enter_organization(` call (`db/verify.py:750-767`). Bites: unproven here (prompt 01's
  check tests).
- Functions owned by `xcode_owner` that read past RLS: `identity.active_organization(uuid)`
  and `tenancy.organization_ids()` (catalogue query). Neither takes caller input that can
  steer to another organization: the user id comes from a locked row or a verified token.
  holds.
- Anti-escalation and the catalogue: n/a (prompt 05).

D2 Identity and sessions
- Refusals identical at the routine level: holds (`refused` for unknown, paused untrusted,
  capped; the envelope is prompt 04).
- Lockout model and resets: holds (`test_state_machine_transition`, `test_counter_resets`).
- Security version, deactivation, device revocation stop the next request; refresh rotation
  and replay: holds (`test_resolve_session_refuses_each_failure_cause`,
  `test_rotation_then_replay_revokes_the_devices_live_tokens`).
- Codes: caps, expiry at equality, withdrawal: holds (`test_identity_helpers.py`).
- The decision uses current state: **fails** (V-D2-1), fixed.
Hardest attacks that failed: (1) two concurrent wrong PINs to lose a count: the row lock
serialises them (two-connection test); (2) a code from another device: bound to the device
(`test_verify_device_cannot_trust_another_device_with_a_code`); (3) a dismissed employee's
refresh: `policy_for` is null without an active membership, refused with nothing written.

D3 Data integrity and concurrency
- `identity.users.version` bumped by `touch_version` in every routine that changes the row:
  holds (read). Lock order: user row, then code or token rows, in every auth and operator
  routine; no routine here locks an organization row: holds.
- Append-only by grant: holds (`sign_in_attempts`, `change_log`, `audit_events`,
  `operator_actions`: INSERT only for the executor, nothing for `xcode_app`/`xcode_operator`).
- Money and replays: n/a for the scope.

D4 Contract parity
- Routes: n/a for prompt 03 (no HTTP); the 13 auth routes equal the .NET 13
  (`AuthEndpoints.cs`, `http/routers/auth.py`). The other routes belong to later prompts
  (the .NET table has 97 `Map*` calls, the Python routers 70; prompts 06 to 08b).
- Behaviour against .NET: phone normalisation **fails** (V-D4-1), role names **fail**
  (V-D4-2), both fixed; reason clipping **fails** (V-D5-1), fixed; provisioning otherwise
  equal to `UserProvisioning.cs` (names do not bump the security version in either).
- Drift: `git status --short apps/api tests/api` shows uncommitted .NET edits from other work
  (petty cash, reports, recurring pauses); none touches auth, provisioning or the helpers
  this scope ports.

D5 Domain rules and time: business date and zones hold (claim 7); `fmt_day` uses `Mon`,
which is not localised without `TM`: holds; reason text: V-D5-1.

D6 Database craft
- `SECURITY DEFINER` with fixed `search_path`; no `PUBLIC` execute on `api.*`: holds.
- No dynamic SQL: holds (no `EXECUTE`/`format(` in routine bodies).
- Old overloads: the runner strips caller grants from a function no file re-creates
  (`db/migrate.py` docstring); the changed `api.auth_sign_in` signature leaves its old
  overload grant-less in long-lived databases: holds. Measured at 21:25 on the CLI database
  `xcode` after `db routines`: the 8-argument `api.auth_sign_in` is executor-owned with ACL
  `{xcode_api_executor=X/xcode_api_executor}` (`has_function_privilege` false for `xcode_app`
  and `xcode_operator`), and the 9-argument one carries `xcode_app=X`; the runner lists the
  old one as an orphan. Dropping it is a deploy step for whoever applies this change to a
  long-lived database (A).
- Versions: local cluster PostgreSQL 16.15; CI pins `postgres:18` but the workflow file is
  untracked and has never run; nothing in the scope needs more than 13.
- Template: every run used a private template built from the files tested (`xcode_template_v03`
  baseline, `v03b`, `v03c`, `v03d`, and `v03e` for the full run; all dropped afterwards); another session's `db/` edit at 20:46 made the harness
  refuse a rebuild of `v03c` while my run held it, as designed.
- Note: `btree_gist` support functions live in schema `ops`, owned by `postgres`, with the
  default `PUBLIC` execute; harmless C functions, prompt 01/02 scope.

D7 Performance: one statement per gateway call (`test_gateway.py`); `meta_unassigned_user_count`
calls `active_organization` per user (a `SECURITY DEFINER` function is not inlined), once at
startup: note. EXPLAIN at 10x: not checked (no heavy read in the scope).

D8 Operability: no log call in the scope carries personal data (`db/session.py` logs the
routine name and duration; the CLI prints ids, counts and refusal codes); every `XCODE_*`
name appears in `settings.py`, `.env.example`, `docs/08` (grouped rows such as
`XCODE_EMAIL_HOST/PORT/FROM/...`) and `test_settings.py`: holds.

D9 Hosting and supply chain: not checked (outside the scope; verify-04 holds it).

D10 Tests as evidence
- No skip, xfail, sleep or broad except in the scope's tests: holds (the hits of the sweep
  are in prompt 01 and 04 files, section 8).
- Wrong implementations the tests catch: skipping the row lock (two-connection test fails);
  skipping token eligibility (`..._without_a_membership_...`); trusting a stale verdict (now
  `test_steps_6_and_7_a_verdict_on_a_hash_replaced_since_the_lookup_is_a_wrong_pin`, the
  shared fake/routine case and the API race test); stripping instead of refusing a non-ASCII
  digit (`test_every_non_ascii_decimal_digit_makes_the_input_not_a_number`); a routine that
  skipped the device check in refresh (`test_refresh_refuses_an_untrusted_device`).
- Every `Raises:` code tested: **fails** (V-D10-1), fixed.
- Full suite once: section 8.

D11 Documents and prompts: `docs/05`, `docs/07`, `docs/12`, `docs/13` corrected in this run;
prompt 03's verify block uses `docker compose`, which this machine lacks (the local cluster
on 5433 replaces it); the prompt asks for PostgreSQL 18, the machine has 16.

## 5. Per mode

Assumptions (Socratic)

| Assumption | Where stated | Enforced by |
|---|---|---|
| The account cannot change between lookup and decision | implied by `docs/07` 3.1 ("two statements") | nothing before this run; now the `p_checked_pin_hash` comparison under the row lock |
| Only ASCII text is a phone number | `docs/07` section 1 | the twins; contradicted by .NET (V-D4-1) |
| An automatic reason is short | `compose_reason` header | caller name limits only; now the clip |
| Each routine writes one attempt row | prompt invariant | `test_each_decision_routine_writes_exactly_one_attempt_row` |
| Operators are who they say | `docs/12` section 2 | nothing (V-D8-1) |

Falsification: the claims table (section 2) is the falsification table; each failing claim
names the observation that disproved it.

Pre-mortem (three months after cutover)
1. A phone is stolen; its owner resets the PIN by email; the thief's script, which had kept
   signing in with the old PIN, holds a fresh token issued after the reset, and keeps
   reading figures for 30 days. Noticed when the owner sees edits they did not make. (Was
   possible: V-D2-1; fixed.)
2. Web users who paste their number from WhatsApp cannot sign in; support sees "wrong
   number" complaints after the switch from .NET. (V-D4-1; fixed.)
3. A prankster requests PIN resets for a list of numbers each morning; staff on new phones
   get no code all day. (V-D2-2; residual risk.)
Inversion: what guarantees failure is any decision taken on state read by an earlier
transaction. Only A01/A02 split their decision; A12 (resolve then revoke) only revokes, which
is idempotent.

Red team (personas 2, 3, 5, 7 apply): stale-verdict sign-in (gap, fixed); code-budget denial
(parity, recorded); enumeration by timing of the lookup's write (dwarfed by the PBKDF2 run
every A01/A02 does; parity); operator naming (recorded); calendar: pause and code expiry at
the exact instant (tested).

Dialectic
| Decision | Strongest counter | Verdict | Confidence |
|---|---|---|---|
| Two statements for A01/A02, PBKDF2 in the process | verify inside one transaction holding the row lock, as .NET did | keep two statements (a connection held through a 1 s derivation would exhaust the pool) and bind the verdict to the hash | high |
| Row lock + `device:` advisory lock at READ COMMITTED | SERIALIZABLE as .NET | keep: the lock serialises per account; the race found was across transactions, which SERIALIZABLE would not have fixed either | high |
| Refusals as outcomes that commit counters | raise and roll back | keep (parity, `docs/07` section 2 item 4) | high |
| Unkeyed phone digest | HMAC with a key outside the database | keep for now, recorded (V-D2-3) | medium |
| Refuse every non-ASCII character in a phone | follow .NET | changed to follow .NET for non-digits (V-D4-1) | high |

## 6. Conceded

- A refused operator command leaves no trace: the CLI records the refusal in its own
  transaction (`cli/commands/users.py:123-133`).
- Provisioning a new name does not bump the security version: neither does .NET
  (`UserProvisioning.cs`, the bump condition lists phone, status, membership and role).
- A capped account could still verify a device: no new-device code is issued past the cap,
  because A01 refuses before step 8.
- Two refreshes racing with one token revoke the device's tokens: the documented .NET
  behaviour (`docs/07` section 10 row 12).
- A lapsed pause is not cleared on the `inactive` path of step 8: it is treated as open on
  every read, so nothing observable changes.
- `check_time_zone` could accept an abbreviation: `EAT`, `UTC+3` and lower-case names are
  refused (`test_check_time_zone_refuses_anything_else`).

## 7. Fixes

Originals kept in the session scratchpad; `apps/api-python` is untracked, so `git diff` shows
nothing for it.

| Finding | Files | Test that failed before and passes now |
|---|---|---|
| V-D2-1 | `db/routines/20_identity/auth_sign_in.sql`, `domain/identity.py` (`PinVerdict.checked_pin_hash`), `db/routines/identity.py`, `application/auth/sign_in.py`, `tests/support/{fakes,scenario,auth_cases,pins}.py`, `tests/db/test_gateway.py`, `tests/db/test_ops_routines.py` (grant tuple), `docs/05`, `docs/07` | `tests/api/test_auth_races.py::test_a_pin_reset_during_a_sign_in_voids_the_old_pins_verdict` (200 before); `tests/db/test_auth_routines.py::test_steps_6_and_7_a_verdict_on_a_hash_replaced_since_the_lookup_is_a_wrong_pin`; shared case `step_6_a_verdict_on_a_hash_replaced_since_the_lookup_is_a_wrong_pin` (fake and routines) |
| V-D4-1 | `db/routines/20_identity/normalize_phone.sql`, `domain/values.py`, `tests/support/phone_vectors.py`, `tests/db/test_phone_parity.py`, `docs/07`, `docs/13` (question 67) | the 7 corrected vectors (both twins wrong before); `test_every_non_ascii_decimal_digit_makes_the_input_not_a_number` guards the refusal |
| V-D5-1 | `db/routines/10_common/compose_reason.sql`, `docs/05` | `test_compose_reason_clips_a_long_automatic_reason_without_a_typed_one` (failed with 520 characters) |
| V-D4-2 | `db/routines/20_identity/ops_provision_user.sql`, `docs/05` | `test_provision_matches_the_role_name_ignoring_case` (the replaced row asserted the refusal and passed in the baseline) |
| V-D10-1 | `tests/db/test_ops_routines.py` | `test_provision_refuses_names_past_their_lengths` (new coverage) |
| V-D11-1, V-D2-2, V-D2-3, V-D8-1 | `docs/07` 3.1, `docs/12` section 7 | documents |

Secure-coding checks (the `testing-api-authentication-weaknesses` and
`exploiting-race-condition-vulnerabilities` checklists, read after the fixes were written and
applied to them as a review; no traffic beyond the local test cluster):
- Time of check against time of use: the hash comparison runs after `identity.lock_user`
  (`auth_sign_in.sql:39`, then line 61), so a reset either commits before the lock (the
  verdict is void) or waits for the sign-in to commit.
- Two endpoints racing (reset during sign-in): `test_auth_races.py` drives exactly that
  and asserts 401, no live token for the device and one counted failure.
- Fails closed: a NULL verdict or a NULL checked hash is a wrong PIN (the `checked_hash=None`
  case of the routine test).
- Same answer as a wrong PIN, so the race opens no enumeration signal; lockout counters
  move as for a wrong PIN.
- No secret in clear: the new parameter is a stored digest, and `PinVerdict.checked_pin_hash`
  is `repr=False`.
- Not applicable to these changes: JWT signing and claims, refresh rotation (unchanged).

## 8. Commands and outputs

Environment: Windows 10, 4 cores shared with three sessions; local PostgreSQL 16.15 on
5433 (`XCODE_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5433/postgres`); Python
3.13.2 (`.venv`). Every run used `.venv/Scripts/python -m pytest -q -p no:cacheprovider`
with a private `XCODE_TEST_TEMPLATE`; logs in the session scratchpad.

| Run | Template | Modules | Result |
|---|---|---|---|
| Baseline (before any edit), `-n 3` | `xcode_template_v03` | `tests/db/test_tenancy_helpers.py`, `test_identity_helpers.py`, `test_auth_routines.py`, `test_ops_routines.py`, `test_gateway.py`, `test_routine_headers.py`, `test_grants.py`, `test_phone_parity.py`, `tests/unit/test_cli.py`, `tests/api/test_cli.py` | 1357 passed in 26:44, exit 0 |
| Pre-fix proofs | before each fix | the new or corrected tests against the unfixed code | failed as listed in section 7: the race test got 200 `authenticated`; compose_reason returned 520 characters; `--role owner` was refused (the baseline row asserted that); 7 phone vectors were wrong in both twins |
| Fix 1, `-n 2` | `xcode_template_v03b` | `tests/api/test_auth_races.py`, `tests/db/test_auth_routines.py`, `test_gateway.py`, `test_ops_routines.py`, `test_fakes_match_routines.py`, `test_grants.py`, `tests/unit/test_use_case_sign_in.py`, `test_use_case_resolve_session.py`, `tests/api/test_auth_contract.py`, `tests/api/test_cli.py` | 100 failed, 519 passed in 37:12: 99 `TypeError` (`PinVerdict` caller `tests/support/auth_cases.py` missed; mypy covers `src` only, V-D10-2) and `test_a_provisioned_person_sets_a_pin_and_signs_in` (checked hash of the person's own PIN); both fixed |
| Fix 2, `-n 2` | `xcode_template_v03c` | `tests/db/test_phone_parity.py`, `test_identity_helpers.py`, `test_tenancy_helpers.py`, `tests/unit/test_domain_values.py` | 1 failed, 298 passed in 28:16: the `test_normalize_phone` row for U+00A0 still asserted the refusal; corrected to `+254712345678` |
| Fix 3, `-n 2` | `xcode_template_v03d` | `tests/db/test_ops_routines.py`, `test_fakes_match_routines.py`, `test_identity_helpers.py::test_normalize_phone`, `test_phone_parity.py`, the two changed `test_auth_routines.py` tests, the compose_reason test, `test_routine_headers.py`, `tests/api/test_auth_races.py`, `test_contract_released_clients.py`, `tests/unit/test_domain_values.py` | 1487 passed in 18:17, exit 0 (ended 21:30) |
| Full run 1 (shared with verify-04 and verify-05), `-n 3` | `xcode_template_v03e` | whole suite (`pytest -n 3 -q -p no:cacheprovider`), started 21:31; nobody edited `src/`, `db/` or `tests/` while it ran (board freeze) | 4242 passed, 6 warnings in 1:03:26, exit 0 (ended 22:34). The warnings are PyJWT `InsecureKeyLengthWarning` from tests that sign HS384/HS512 tokens with the 36-byte test key (prompt 04's algorithm checks), not a defect |

Other commands:

| Command | When | Output |
|---|---|---|
| `ruff check .` | 22:35 | `All checks passed!`, exit 0 |
| `ruff format --check .` | 22:35 | `334 files already formatted`, exit 0 |
| `mypy` | 22:35 | `Success: no issues found in 153 source files`, exit 0 (covers `src` only: V-D10-2) |
| `xcode-api db routines` (CLI database `xcode`, claimed on the board) | 21:22 and 22:35 | `applied 184 routine files`, exit 0; orphan warnings: the old 8-argument `api.auth_sign_in` (this run's change) and the old 6-argument `api.people_list` (verify-05's change) |
| `xcode-api db verify` | 21:25 and 22:35 | 21 checks `ok`, exit 0 |
| catalogue query on `xcode` (`pg_proc`, `has_function_privilege`) | 21:25 | old overloads not executable by `xcode_app` or `xcode_operator` (section 4, D6) |
| sweeps: `grep` over `db/routines` for `now()`, `current_date`, `clock_timestamp`, `random()`, `EXECUTE`, `format(`, `search_path` | during the challenge | as reported in section 4 (D6) and claims 21 to 23 |

## 9. Regressions and misses against earlier audits

Read only after this run's own pass. There is no earlier verify report for prompt 03 in
`docs/audit/`; the only earlier claim is the status line "implemented; validated
2026-10-09" in `docs/prompts/README.md`, with no report behind it. Nothing it recorded as
fixed was found broken again (it recorded nothing checkable). What that validation missed:
V-D2-1 (the stale verdict), V-D4-1 and V-D4-2 (both pinned the wrong answer in tests: the
no-break-space vector in `phone_vectors.py` and `test_identity_helpers.py`, and the
`("owner", "people_role_unknown")` row), V-D5-1 and V-D10-1. The prompt 01 verify report
listed `meta_unassigned_user_count.sql` as out of its scope (its N5); this run covered it
(D7 note). The prompt 04 verify report raised the phone finding (`04:V-D4-2`), taken here
as V-D4-1.

## 10. For the user

1. **Code budget shared across purposes (V-D2-2).** Anyone with a phone number can use up
   that person's codes for the day with PIN-reset requests, so the person cannot add a new
   phone until the next day. Recommendation: keep .NET's counting until cutover, then give
   new-device codes a budget of their own (the same 5 an hour and 10 a day). The denial
   costs an outsider nothing; the extra mail per account is bounded by the same caps.
2. **Operator identity (V-D8-1).** Today the audit row names whoever `XCODE_OPERATOR` says.
   Recommendation: one database login per operator once more than one person runs the CLI,
   and record `session_user` beside the claimed name. It costs a role per person and a line
   in the runbook.

3. **Deploy step.** Any long-lived database that receives this change keeps the old
   8-argument `api.auth_sign_in` as a grant-less orphan. Drop it when the change is deployed.

The green full run covers the tree as of 21:31. The 07b D1 session began rewriting
`domain/identity.py`, `db/routines/identity.py` and `application/auth/sign_in.py` at 22:35,
after the run, so its own runs must cover that rewrite.
`tests/api/test_auth_races.py` guards this report's main fix.

Nothing else here needs a business decision: the two majors were parity defects and are
fixed, and the phone-digest note (V-D2-3) is a security choice recorded for the 07b redesign.

Process note: my first times on `.coordination/board.md` ran about an hour ahead of the
clock (estimates written before I measured it); the row added at 21:02 says so. A scripted
correction of the older rows was refused by the permission system, so they stand as
written.
