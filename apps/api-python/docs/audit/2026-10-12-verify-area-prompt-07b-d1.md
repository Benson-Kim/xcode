# Verify `area:prompt 07b-design-v2-3.md, part D1` (fix mode, standard depth)

Session verify-07b-d1, 2026-10-12 07:22 to 08:00. Method: `docs/14-verification.md`.
Stopped early by the context budget of `docs/prompts/verify.md` ("about 100k tokens"):
what is not done is marked `not checked`, and section 11 says where to resume.

## 1. Verdict

**fail**: the full suite did not run (D1's own run was also stopped, at 1%, on 2026-10-12
00:25), and one major survives unfixed.

- Findings: 2 majors (1 fixed, 1 open as question 69), 0 blockers, 0 minors, 2 notes.
- Claims (section 2): 16 in total: 1 `fails` (fixed), 1 `fails` (open), 0 `holds`,
  9 `unproven` (read and consistent, not rerun after the fix and not on a full run),
  5 `not checked`.
- Under the board rule of 2026-10-12, no D1 clause is `holds` before a full run is green.

## 2. Thesis and claims

Thesis (steelmanned): "Migration `0008_sign_in`, the `api.auth_*` routines, the device
token, the use cases and N01 to N09 deliver B1, B2's number-first entry, B4 to B8 and the
forced-reset part of B3 as `docs/07-auth.md` section 12 states them; v2.11 phones still sign
in; and no answer tells an unknown number from a known one beyond what D0 decided and
recorded (`docs/07` 12.14 a, `docs/12` section 7)."

| # | Claim (prompt 07b D1 / docs) | Code | Verdict | Grade |
|---|---|---|---|---|
| 1 | Migration for the identity changes; existing pauses become locks, lapsed ones clear (`docs/04` 13.1) | `db/migrations/0008_sign_in.sql` (DO checks count locks before and after) | unproven (read only) | D |
| 2 | N01 order: unknown simulated, blocked, no PIN / forced reset code, locked, pin_required (`docs/07` 12.2) | `db/routines/20_identity/auth_start.sql` | unproven (read: order matches) | B (tests exist, not rerun) |
| 3 | N02 order and both lock scopes (`docs/07` 12.3, 12.5) | `auth_pin.sql`, `locked_for.sql`, `count_wrong_pin.sql` | unproven (read: matches) | B |
| 4 | Two wrong PINs at once both count (row lock) | `identity.lock_user` via `lock_account.sql` | unproven | B (`test_two_wrong_pins_at_once_both_count_toward_the_lock`, not rerun) |
| 5 | Code rules: 3 tries, replacement, caps 1/min, 5/h, 10/day (`docs/07` 12.6) | `matching_code.sql`, `code_caps.sql`, `issue_code.sql`, `auth_check_code.sql` | unproven (read: matches) | B |
| 6 | Code email holds code, purpose and device name only | `infra/mail.py` templates | not checked | |
| 7 | Device token: 32 random bytes, SHA-256 at rest, 90 days idle (`docs/07` 12.8) | `security/device_tokens.py`, `device_trusted.sql`, `device_live.sql` | unproven (SQL read: token must match the same `deviceId`; a new route never reaches the legacy branch) | B |
| 8 | Removal of every device after a reset or a block (`docs/07` 12.9) | `remove_devices.sql`, completion routines | not checked | |
| 9 | Sign-in history and change-log phrases verbatim (`docs/07` 12.10, 12.11) | `log_sign_in.sql`, `count_wrong_pin.sql` | unproven (one phrase read) | D |
| 10 | Forced reset part of B3 (`docs/07` 12.7) | `auth_start.sql`, `auth_pin.sql`, `auth_sign_in.sql` (`reset_required`) | unproven (read) | B |
| 11 | Refusals the design keeps uniform stay byte for byte, the new step included | `tests/api/test_auth_contract.py`, `test_auth_steps.py` | unproven (not rerun) | B |
| 12 | v2.11 request (number and PIN together, trust by `deviceId`) still signs in | `tests/api/test_contract_released_clients.py` | unproven (not rerun) | B |
| 13 | Concurrency: a code voided while a new one is issued | `tests/api/test_auth_races.py` | not checked | |
| 14 | **The simulated reset code of an unknown number answers like a real one** (`docs/07` 12.14 a) | `unknown_code_tries.sql` | **fails**: 07b-d1:V-D2-1, fixed | A after the fix |
| 15 | **No answer tells an unknown number from a known one beyond what was decided and recorded** (prompt 07b invariants) | the simulated account (`auth_pin.sql`, `auth_check_code.sql`, `unknown_*_tries.sql`) | **fails**: 07b-d1:V-D2-2 (part recorded by D1 in `docs/12` s7, part not), open | A for the leak (hand-traced against the routines; no test, see V-D2-2) |
| 16 | Lint, types, all tests green; `db verify` exit 0 | | not checked (no full run; `ruff check` and `ruff format` clean on the files I changed) | |

## 3. Findings

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| 07b-d1:V-D2-1 | red team (outsider with a list of numbers) | `docs/07` 12.14 a: the code step of an unknown number "counts down three wrong tries ... as for a real account" | N05 "forgot PIN" with device A, then N03 `pin_reset` with a wrong code and device B. Real account: codes are per device (`matching_code.sql`: `c.device_id = p_device_id`), so "no code", `triesLeft` null. Unknown number: `unknown_code_tries` read the history by digest only, so `refused` with `triesLeft` 2. Three requests tell "account with a PIN" from "unknown" | `tests/db/test_auth_routines.py::test_the_simulated_reset_code_belongs_to_the_device_that_asked_for_it` failed before the fix (`'wrong_code' != 'code_expired'` for the unknown number; the real account passed the same assertions) | looked for a device filter in the simulation, the fake and the docs: none; the N03 use case passes the request's device to the routine unchanged | survives, **major** (an enumeration-resistance claim, reachable with three anonymous requests) | **fixed**: `identity.unknown_code_tries(p_phone_digest, p_device_id, p_now)` filters the issuing row and the wrong tries by device; `auth_check_code.sql` passes it; the fake mirrors it (`FakeAttempt.device_id`); helper test extended with another device |
| 07b-d1:V-D2-2 | red team + pre-mortem | same claim, and the prompt invariant "no refusal tells an unknown number from a known one beyond what D0 decided and recorded" | (a) Forgot PIN, two wrong codes, forgot PIN again within the minute, one wrong code: the real person's second request is silently capped (`code_caps.sql`: a code younger than a minute), the old code takes its third try and answers `code_resent`; the unknown number restarts from the newest `forgot_pin` row and answers `refused`, `triesLeft` 2. Five requests in a minute. (b) An N04 resend after the minute issues a fresh real code (`auth_resend_code.sql`) that the simulation does not model (only `forgot_pin` and `code_resent` rows restart it). (c) Hourly and daily caps. (d) Two concurrent N02 tries: the lookup records an unknown number's try in statement one (`auth_account_lookup.sql`), so both decisions can count both rows (`triesLeft` 3 and 3) where a real account's row lock gives 4 then 3 | hand-traced against `code_caps.sql`, `issue_code.sql`, `matching_code.sql`, `auth_check_code.sql`, `unknown_code_tries.sql`, `auth_resend_code.sql`, `auth_pin.sql` | read `docs/12` section 7: D1 recorded (c) ("a dozen requests") and (d) as residual risks, so those two are conceded as recorded; (a) is far cheaper than the recorded estimate and (b) is not recorded | survives for (a) and (b), **major**; (c), (d) conceded as recorded | **open question 69** (`docs/13`): replace the history replay by a shadow state per number that runs through the same cap, cooldown and lock code; residual risk bullet added after D1's two in `docs/12` section 7. Not fixed here: a partial patch of the replay leaves the next divergence, and the shadow state is a schema decision for 07b's design owner |
| 07b-d1:V-D10-1 | falsification | "D1 is done" (`docs/audit/2026-10-12-build-07b-d1.md`) | D1's full run stopped at 1% (00:25); my baseline of the D1 modules stopped at 90% (30-minute job limit) with 17 failures whose details were not printed; from 64% the tree was changing under it (D2 wrote `db/routines/30_tenancy/*` and `domain/tenancy.py` from 07:41) | `baseline.log` (scratchpad); afterwards `tests/unit`: 912 passed, 2 failed, both D2's (`test_permission_keys` against `domain/tenancy.py` 07:56; `test_routine_catalogue`: new `tenancy.person_sign_in` not yet in `docs/05`) | attributed by file times; the D1 parity cases pass after my fix (318 passed) | note | the shared full run (board queue row 1) decides; attribute every failure by file time before fixing |
| 07b-d1:V-D11-1 | Socratic | `docs/12` s7 residual risk "telling the two apart takes a dozen requests per number" | the one-minute cooldown does it in five (V-D2-2 a) | as above | none | note (doc understated the cost) | doc corrected: one bullet after D1's |

## 4. Per domain

D2 identity and sessions (the scope's core):

| Probe | Verdict |
|---|---|
| Unknown number, paused/locked and capped answer the same bytes on the released routes | unproven (tests exist: `test_auth_contract.py`; not rerun) |
| New steps: unknown number answers like an account with a PIN | **fails** (V-D2-1 fixed; V-D2-2 open) |
| Lockout model: two scopes, resets only on a code, a PIN change or `clear-pause` | unproven (SQL read: `locked_for`, `count_wrong_pin`, `auth_check_code` clears both on a verified new device; `auth_pin` clears only `failed_attempts` on a trusted right PIN) |
| `security_version` bump, deactivation and revocation stop the next request | not checked |
| Tokens (algorithm, claims, leeway) | not checked (unchanged by D1) |
| Codes: caps include superseded and voided, exclude withdrawn | unproven (SQL read: `code_caps.sql` excludes `consumed AND expires_at <= created_at`) |
| Rate limit before body validation, `auth_pin` charged once | not checked |
| Device token: digest only at rest, never logged | unproven (no log call in `application/auth`, `auth_steps.py`, `device_tokens.py`; mail logs carry a recipient hash only) |

D1, D3 to D9: not checked beyond the sweeps below. D10: section 3 V-D10-1; two
`asyncio.sleep` polls in `tests/api/test_auth_contract.py:364,661` wait for queued mail
(bounded loops, not a fake of the capability): conceded. D11: V-D11-1; `docs/05` 10.1 and
`docs/07` 12.16 updated with the fix.

Mechanical sweeps (all hits listed):
- `now()`, `current_date`, `clock_timestamp()`, `random()` in `db/routines`: none.
  (`0008_sign_in.sql` uses `now()` in its one-off data DO blocks, as a migration may.)
- `EXECUTE` / `format(` in `db/routines`: none outside grants.
- `SECURITY DEFINER` without `SET search_path`: none.
- `skip`, `xfail`, `importorskip`, bare `except` in the D1 test modules: none; `sleep(`:
  the two above.
- `TODO`, `FIXME`, `HACK`, plan ids in `src`, `db`, `tests`: none (`XXX` hits are the
  phone format `+254XXXXXXXXX` in `domain/values.py:148`, `normalize_phone.sql:2`).
- Log calls with a body, phone, email, PIN, code or token in the D1 code: none found.
- Routes versus `docs/06` versus OpenAPI; `XCODE_*` settings across four files: not checked.

## 5. Per mode

- **Assumptions**: "the simulated account answers as a real one" rests on the history
  replay modelling every state a real account has (codes per device, cooldown, caps,
  resend, serialisation); enforced by nothing but the cases someone thought of (V-D2-1,
  V-D2-2).
- **Falsification**: claims table, section 2.
- **Pre-mortem**: three months after cutover a rival fleet's script feeds a list of
  numbers through N05/N03 at five requests a number, sorts out every staff number with a
  PIN, and each real person receives one unexplained "Reset PIN" mail; nobody notices
  because each mail looks like a mistyped number. Inversion: the condition (a replay that
  ignores the cooldown) exists now. Early sign: `forgot_pin` history rows from one address
  across many digests.
- **Red team**: outsider persona, V-D2-1 (fixed) and V-D2-2 (open); stolen device token
  (token alone gives nothing: `device_trusted.sql` requires the same `deviceId`, and N02
  still needs the PIN): conceded.
- **Dialectic**: "simulate an unknown number" versus "answer every number the same way
  until a PIN is entered" (the pre-v2.3 model). The design chose truthful answers for
  PIN-less, reset and blocked numbers; keeping that, the replay is the weak part, so
  question 69 proposes a shadow state rather than reversing DEC-2. Confidence medium.

## 6. Conceded

- V-D2-2 (c) hourly/daily caps and (d) concurrent N02 tries: already recorded by D1 in
  `docs/12` section 7 (they still count against the prompt invariant if the owner rejects
  question 69's direction).
- A new route reaching the legacy `deviceId` trust: `auth_start.sql` and `auth_pin.sql`
  pass `coalesce(p_device_token_hash, '')`, which matches no row (`device_trusted.sql`).
- A device token presented with another `deviceId`: the match is on (user, `device_id`,
  `token_hash`) together.
- The two test sleeps: bounded polls for queued mail, not a fake.

## 7. Fixes

| Finding | Files | Test that failed before and passes now |
|---|---|---|
| 07b-d1:V-D2-1 | `db/routines/20_identity/unknown_code_tries.sql` (new `p_device_id`), `db/routines/20_identity/auth_check_code.sql` (passes it), `tests/support/fakes.py` (`FakeAttempt.device_id`, `_remember`, `_unknown_code_tries`), `tests/db/test_identity_helpers.py` (new signature, another-device assertion) | `tests/db/test_auth_routines.py::test_the_simulated_reset_code_belongs_to_the_device_that_asked_for_it` |

Documents: `docs/05-routines.md` 10.1 `identity.unknown_code_tries` row; `docs/07-auth.md`
12.16 one bullet; `docs/12-security.md` section 7 one bullet; `docs/13-open-questions.md`
question 69.

Deploy note: the old `identity.unknown_code_tries(text, timestamptz)` stays in a database
that already ran the routine files (the dev `xcode` database); it is an `identity` helper
with no caller grant, but drop it in the next migration (with the old 8-argument
`api.auth_sign_in` the board already lists).

## 8. Commands and outputs

- `git status --short` at 07:22: `apps/api-python/` untracked as a whole; no D1 file
  changed after 00:18; other sessions edited docs from 07:09 and, from 07:41, D2 files.
- `SELECT version()`: PostgreSQL 16.15 (local cluster, port 5433). `python --version`:
  3.13.2. CI (`.github/workflows/xcode-api.yml`, untracked, never run): `postgres:18`.
- .NET drift for auth since 2026-10-07: no change to `apps/api` auth files
  (`git log`/`git status`); D1 is ahead of .NET by decision (question 46).
- Baseline (`-n 2`, template `xcode_template_vd1`, started 07:27): stopped at 90% by the
  30-minute job limit; 17 failures, no details printed (see V-D10-1).
- Failing-first: the new test failed (`'wrong_code' != 'code_expired'`), then
  `-k "simulated or unknown_code or reset_code"` on `test_auth_routines.py` and
  `test_identity_helpers.py`: 4 passed; `tests/db/test_fakes_match_routines.py -k "code or
  unknown"`: 318 passed in 16:49 (template `xcode_template_vd1b`).
- `tests/unit` (no database): 912 passed, 2 failed (D2's in-flight work, V-D10-1).
- `ruff check` and `ruff format --check` on the changed Python files: clean.
- Full run: not run; requested as row 1 of the board's shared full-suite queue (07:41).
- `mypy`, `db routines`, `db verify`: not run (the CLI database is claimed through the
  board, and D2 changes routines there today).
- Cleanup: `xcode_template_vd1`, `xcode_template_vd1b` and my `test_gw0_*` dropped.

## 9. Regressions and misses against earlier reports

Read after my pass: `docs/12` section 7 (D1's residual risks). D1 recorded the hourly/daily
cap divergence and the concurrent-try divergence; it missed the device scope (V-D2-1,
fixed), the one-minute cooldown and the resend (V-D2-2 a, b). `docs/audit/2026-10-12-build-07b-d1.md`
and the 07b D0 verify were not read (budget).

## 10. For the user

- Question 69 (`docs/13`): keep simulating unknown numbers from the history, or give each
  probed number a shadow state that runs through the same code as a real account.
  Recommendation: the shadow state. The replay has now diverged four ways, each found by
  reading one more rule; a shadow row reuses the real cap, cooldown, per-device and lock
  logic, so a new rule cannot diverge silently.

## 11. Where to resume

1. The shared full run (board queue row 1): read the D1 modules from its log; until it is
   green, every D1 claim stays `unproven`.
2. Not checked here: claims 6, 8, 13, 16; D2 probes on `security_version`, tokens and the
   rate limits; D1 (people actions across tenants), D3 (lock order of the auth routines),
   D4 (released-client rows, routes versus `docs/06` versus OpenAPI), D5, D6 (`db verify`,
   stale overloads), D8 (`XCODE_*` across four files).
3. V-D2-2: after the owner answers question 69, build the shadow state with a test per
   divergence (a) to (d).

## 12. Shared full run (added by the coordinator, revenue-d5 [b49167], 2026-10-12 15:30)

The shared full run: `pytest -n 2 -q -p no:cacheprovider -rfE --junitxml` on a fresh
`xcode_template_full` built at 13:01 from the frozen live tree, 13:00 to 15:23 (2:22:27):
5617 passed, 42 failed, 0 errors, 0 skipped. Log and JUnit XML in revenue-17 [60bb7c]'s
scratchpad (`full.log`, `full.xml`); every failure has an owner (coordination board
section 5, 15:26).

Section 11 item 1, the D1 modules: `test_auth_steps.py` 22, `test_auth_contract.py` 42,
`test_auth_races.py` 1, `test_contract_released_clients.py` 28, `test_ops_routines.py` 64,
`test_fakes_match_routines.py` 663, `test_enum_parity.py` 27, `tests/unit` 943, all passed;
`test_auth_routines.py` 140 of 141 and `test_identity_helpers.py` 55 of 56. The two failures
(`test_step_9_the_right_pin_on_a_trusted_device_clears_its_scope_and_issues_tokens`,
`test_policy_for_returns_the_defaults_names_role_and_permissions`) count 77 permission keys
where they expect 39: 07b D2's `0009` catalogue (59 rights and the legacy keys), not a D1
defect; D2's verifier (revenue-a8) records them.

Outside the list, `tests/db/test_gateway.py` 16 of 19: one more of the same count, and two
stale since D1's own `src/xcode_api/domain/identity.py` (2026-10-11 22:36, after the test file's
20:23): `test_verify_device_maps_through_the_gateway` (`DeviceVerification` now takes `now`)
and `test_ops_routines_map_the_operator_routines` (`ClearedPause` has no `was_paused`). No D1
session is live; this is for the next D1 session.

The verdict stays **fail** (question 69). The D1 claims that were `unproven` only for want of a
full run stay `unproven` for steps 9 and `policy_for` until their tests are corrected; the
others' modules passed.
