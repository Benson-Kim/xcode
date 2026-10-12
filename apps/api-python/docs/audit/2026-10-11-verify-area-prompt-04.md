# Verify `area:prompt 04` (2026-10-11, `MODE: fix`, `DEPTH: standard`)

Session `revenue-e2` (board name verify-04). Method: `docs/14-verification.md`, all five
modes, fresh eyes; earlier audits read only after the own pass (section 9).

## 1. Verdict

**pass with findings**. No blocker survives. The shared full run (verify-03's run 1,
template `xcode_template_v03e` built at 21:31 from a tree holding every fix below) ended at
22:34 with 4242 passed, 0 failed, 0 skipped and exit 0 in 1:03:26 (section 8).

- Claims (section 2): 33. 27 `holds`, 5 `fails` (all now fixed or corrected: 4 in this
  run, claim 1 by verify-03), 1 `not checked`.
- Findings (section 3): 1 blocker (fixed), 2 major (both fixed, V-D4-2 by verify-03 after
  this run handed it over as question 67), 2 minor (1 fixed, 1 document corrected), 2 notes
  (1 residual risk recorded, 1 left as a hardening idea).

## 2. Thesis and claims

Steelmanned thesis: prompt 04 delivers D1 to D7. Its values, policies, PBKDF2, digests, JWT,
use cases, thirteen `/auth` routes, bearer principal, mail and contract tests hold their
invariants. Where `docs/07` and `docs/06` don't record a deviation, behaviour equals .NET at
`493bf82` plus the working tree. The auth files have not changed since the inventory except
for commit `553dd15` (mail to a loopback relay, drift row 10) and one comment in
`Security.cs` (commit `9276c51`).

| # | Claim (where stated) | Code | Verdict | Grade |
|---|---|---|---|---|
| 1 | Phone normalisation is the `docs/07` s1 rule and equals .NET | `domain/values.py` `PhoneNumber.parse`; `identity.normalize_phone` | **fails** against .NET (V-D4-2) | A (vectors run on both twins; one vector pins the wrong answer) |
| 2 | Bounds of `Pin`, `DeviceId`, `Email`, `RefreshToken`, `VerificationCode`; no digits in `repr` (D1) | `domain/values.py` | holds (code points: an accepted deviation, `docs/07` s10 row 4) | A |
| 3 | PIN floor rules equal .NET `PinRules` (D1) | `policies.pin_shape_valid` vs `AuthContracts.cs:39-50` | holds | A |
| 4 | One refusal object; `envelope_for` maps every outcome (D1) | `domain/policies.py` | holds | A |
| 5 | `Principal` carries the six fields; every router uses `current_principal` (D1, D5) | `http/dependencies.py` | holds | B |
| 6 | PBKDF2 210 000 / 16 / 32, stored format, constant-time compare (D2) | `security/pins.py` | holds | A |
| 7 | Derivations run off the event loop on a bounded pool; past capacity 503 before any decision (D2) | `pins.Pbkdf2PinHasher._run` | holds | A |
| 8 | Digest = HMAC-SHA256 with the signing key, upper hex, as .NET `Security.cs:76` (D2) | `security/digests.py` | holds | A |
| 9 | Codes are 6 digits from `secrets`; refresh tokens are 48 bytes, Base64 (D2) | `security/codes.py`, `refresh_tokens.py` | not checked (context budget; files are 11 and 12 lines) | - |
| 10 | JWT claims and header exactly; integer seconds; no `iat`/`jti` (D2) | `security/tokens.py` vs `Security.cs:80-90` | holds | A |
| 11 | Verify: previous keys, zero leeway, `iss`/`aud` required, HS256 pinned (D2) | `tokens._decode` | holds | A |
| 12 | Use cases take only ports; `domain`/`application` import only the stdlib | `application/auth/*`; `tests/unit/test_layers.py` | holds | A |
| 13 | Sign-in mails a new-device code before replying, bounded by the timeout; on failure it withdraws the code and answers 503 (D3) | `sign_in.SignIn._mail_code`, `infra/mail.VerificationMailer.send_now` | holds | B |
| 14 | Setup and reset mail is queued after the routine; A04/A07 answer the same either way (D3, D7) | `request_code.py`; `test_code_requests_answer_the_same_whether_or_not_mail_was_sent` | holds | A |
| 15 | The fake equals the routines on a shared case table (D4) | `tests/support/auth_cases.py`, `tests/db/test_fakes_match_routines.py` | holds | A |
| 16 | Request models and pre-validation equal .NET `Run` (`AuthEndpoints.cs:76-80`) apart from the recorded deviations (D5) | `http/schemas/auth.py` | holds | A |
| 17 | The thirteen routes, paths and statuses (D5) | `http/routers/auth.py` vs `AuthEndpoints.cs:26-64` | holds | A |
| 18 | The rate limit is charged on every `/auth` request, before validation (D5, `docs/12` row) | `routers/auth.py` | **fails**, now fixed (V-D4-1) | A |
| 19 | Bearer failure is 401 with an empty body and `WWW-Authenticate: Bearer`; another device's id is 403 (D5) | `dependencies.current_session`, `revoke_device` | holds | A |
| 20 | OpenAPI: sign-in documents 202 and 423 with no `security`; the Bearer scheme (D7) | `tests/api/test_openapi.py` | holds | A |
| 21 | Development codes appear only in development (D5) | `settings.py` (`_check`, `development_codes`); contract tests | holds | A |
| 22 | Mail subject and body equal .NET `Security.cs:121` (D6) | `infra/mail.verification_message` | holds | A |
| 23 | `XCODE_EMAIL_TIMEOUT_SECONDS` is in settings, `.env.example`, `docs/08` and the tests (D6) | `settings.py`, `test_settings.py` | holds | A |
| 24 | `LogMailer` writes the body only in development and testing (D6) | `container._default_mailer`; `settings._check_mail` | holds | A |
| 25 | SMTP works on the real host, whose relay listens on loopback without TLS (D6, drift row 10) | `infra/mail.SmtpMailer` | **fails**, now fixed (V-D9-1) | A |
| 26 | Sign-in refusals are byte-for-byte identical (D7) | `test_the_sign_in_refusals_are_byte_for_byte_identical` | holds | A |
| 27 | Lockout, pause, cap, rotation, replay, sign-out, revoke, session kill (D7) | `test_auth_contract.py` | holds | A |
| 28 | Statement budget per route (D7) | `test_each_route_stays_within_its_statement_budget` | holds | A |
| 29 | No PIN, code, token, phone or email in logs (invariant) | `test_no_pin_code_token_phone_or_email_reaches_the_log` | holds (see note V-D8-2) | A |
| 30 | Lint, types and all tests green (invariant) | whole tree | holds: full suite 4242 passed; `ruff check`, `ruff format --check` (334 files) and `mypy` clean after the run | A |
| 31 | Exactly one PBKDF2 derivation per sign-in attempt, known or unknown number (invariant) | `PinHasherSpy` over the real hasher, `test_auth_contract.py:700-713` | holds | A |
| 32 | `docs/06` s1.5: the limiter runs after authentication "as in .NET" | `docs/06` | **fails**; corrected (V-D4-1) | A (`Program.cs:169-171`) |
| 33 | `docs/06` s1.4: `WWW-Authenticate` "on every 401", given as the .NET contract | `docs/06` | **fails** as a parity claim; corrected (V-D4-3) | A |

## 3. Findings

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| 04:V-D9-1 | pre-mortem (deploy day) | claim 25; drift row 10 | Staging's relay is the host's mail server on 127.0.0.1, without TLS (.NET `Email:EnableSsl=false`, commit 553dd15). Python forced STARTTLS on 587 and refused every other port outside development, so no code mail would leave and new devices could not sign in. | `infra/mail.py:96-104` (before); `Security.cs:108-113`; the new test `test_a_starttls_mailer_refuses_a_relay_without_tls` shows STARTTLS failing against such a relay | Is there another way to configure it? No: `allow_plaintext` was hard-wired to `is_development` (`container.py`). | survives, **blocker** (a deploy that cannot work on the real host) | **fixed**: `XCODE_EMAIL_TLS` (default true). `false` sends without TLS and is refused outside development unless the host is `localhost` or a loopback literal (`settings.is_local_host`, both in settings and in `SmtpMailer`). Tests: `test_a_relay_on_this_machine_takes_mail_without_tls` (a real SMTP exchange on 127.0.0.1), `test_mail_without_tls_is_refused_to_a_relay_on_another_machine`, `test_email_without_tls_is_refused_for_a_relay_on_another_machine`, `test_email_without_tls_is_allowed_for_a_relay_on_this_machine`. Drift row 10 closed. |
| 04:V-D4-1 | falsification | claims 18, 32; `docs/12` "charged for every `/auth` request" | `GET /auth/session` or the revoke route with no token, or a bad one, after the window's permits are used: .NET answers 429, because `UseRateLimiter` runs before `UseAuthentication`/`UseAuthorization` (`Program.cs:169-171`). Python answered 401 and never charged it, because `auth_rate_limit` was a parameter dependency after `current_principal`. | `routers/auth.py` (before: `_: Annotated[None, Depends(auth_rate_limit)]` after the principal); the test `test_the_rate_limit_counts_bearer_routes_after_authentication` pinned the deviation; `docs/06` s1.5 justified it as ".NET parity" | Is there a .NET test of the opposite order? None (`ForwardedClientTests.cs` covers sign-in only). Was it a deliberate security choice? The only reason the documents gave was parity, and that is false. Charging first is also stricter. | survives, **major** (a rule wrong on a reachable path; a document that would make the next session build the wrong thing) | **fixed**: the decorator `dependencies=_LIMITED` (FastAPI resolves it before parameter dependencies, `fastapi/routing.py:893-898`). The test was rewritten to the .NET order, parametrised over both routes: `test_the_rate_limit_counts_bearer_routes_before_authentication` (401, then 429 with an empty body and `Retry-After`, no `WWW-Authenticate`, no statement). The assertion in `test_the_rate_limit_answers_429_per_forwarded_client_address` became 429, proved against `Program.cs:169-171`. `docs/06` s1.5 and s2.1 and `docs/07` s2 step 1 corrected. |
| 04:V-D4-2 | red team (a released web client) | claim 1 | A person types or pastes `0712<U+00A0>345678`, or a number carrying direction marks (U+202A to U+202C, U+200E), into the web sign-in. The web sends the field as typed (`apps/web/components/AuthPanel.tsx:210`). .NET `PhoneNumber.Normalize` strips every non-digit (`\D`, `PhoneNumber.cs`) and signs the person in. `PhoneNumber.parse` and `identity.normalize_phone` refuse any non-ASCII character, so the answer is 401 as for an unknown number. | `domain/values.py:157-165`; `db/routines/20_identity/normalize_phone.sql:16`; `tests/support/phone_vectors.py:29` expects `None`; `docs/07` s10 row 5 decided only that non-ASCII *digits* are not a number | Does the mobile app hit it? No: it strips with `normalisePhone` (`packages/shared/src/format.ts:114`). Did a document accept the deviation? `docs/07` s1 states the Python rule, but the recorded decision covers digits only. | survives, **major** (a rule wrong on a reachable path of a released client; an uncommon input) | handed over as **open question 67** (owner of `identity.normalize_phone`, prompt 03); **fixed by verify-03** at 20:37-20:39: both twins strip every non-digit and refuse a decimal digit outside 0-9 (`domain/values.py` `PhoneNumber.parse`, `db/routines/20_identity/normalize_phone.sql`), the vectors in `tests/support/phone_vectors.py` now expect the .NET answers (no-break space, narrow no-break space, direction marks, en dash), q67 marked resolved. Read-checked by this session; its tests are verify-03's and run in the shared full run. |
| 04:V-D8-1 | falsification | `docs/08` s2 "checked at startup, not first send" | `XCODE_EMAIL_PORT=25` outside development passed `settings-check`; `serve` then died building the mailer with a `MailDeliveryError` traceback | `settings._check_mail` (before) had no port rule | already reported as prompt-00 V-D8-6 and left to drift row 10's owner | survives, minor | **fixed**: the port rule is now in `_check_mail` (465 or 587 outside development unless TLS is off to a loopback relay). Tests: `test_an_smtp_port_without_tls_is_refused_at_startup_outside_development`, `test_any_smtp_port_is_allowed_for_a_relay_on_this_machine_without_tls`. `docs/08` row updated. |
| 04:V-D4-3 | Socratic | claim 33 | The envelope 401s of the anonymous routes carry `WWW-Authenticate: Bearer`, which .NET's `Results.Json(..., 401)` never did; `docs/06` gave the header as the contract for every 401 | `routers/auth.envelope_response`; `AuthEndpoints.cs:82` | No client reads the header on those answers: the web proxy forwards status and body, and the mobile app reads the status | survives, minor | **document corrected** (`docs/06` s1.4: an accepted addition). This was found earlier as docs V-D4-6 but never applied. |
| 04:V-D7-1 | red team (outsider with many addresses) | `docs/07` s1 PIN pool row | Every sign-in, unlock and PIN completion costs one derivation before any decision, and the pool admits 18. One derivation measured 1.2 s on this loaded machine, so a few dozen addresses, each within 30 requests a minute, can hold the pool full. Every other sign-in then gets 503. | `security/pins.py:65-75`; the measurement in section 8 | Nothing is counted or spent, and .NET degraded the same way (slower, not 503). A per-account limit before the derivation would leak which numbers exist. | survives, note | **residual risk** recorded in `docs/12` s7 (owner: operations, prompt 09 sizes the pool) |
| 04:V-D8-2 | red team (log reader) | claim 29 | `recipient_hash` is an unkeyed SHA-256 of the address, cut to 12 hex digits. Anyone who reads the logs and holds the staff email list can tell who received codes. | `infra/mail.py:55-57` | It is not the address itself, and the prompt asked for no address, which holds | survives, note | hardening idea, no change: key it, for example HMAC with a log key. Not fixed because notes are out of fix scope. |

## 4. Per domain

- **D1 tenancy (bearer principal only)**: `current_session` binds the actor and organization from the routine, not from the token's `org` (holds). Hardest attacks: a token whose `org` names another tenant (refuted: the organization comes from `api.auth_resolve_session`, and the signature is required); a bearer route reached with another device's id (403, tested); 401 versus 404 probing on `/auth` (not applicable: there are no id lookups apart from revoke, which compares with the claim).
- **D2 identity and sessions**: byte-for-byte holds (claim 26); lockout model, rotation and kill after a version bump or removal hold (claim 27); tokens hold (10, 11); codes hold (14); the rate limit failed and is fixed (V-D4-1). Timing: one derivation for known and unknown numbers (31). PIN completion now derives before the code check, unlike .NET (`PinSetupService.cs:27-41`). The cost is uniform and it is covered by V-D7-1. The sign-in TOCTOU between lookup and decision belongs to verify-03 (`03:V-D2-1` on the board), which holds `sign_in.py`.
- **D3 integrity and concurrency**: n/a to prompt 04's Python beyond ordering. Mail goes out only after the routine committed (14). The routines' locks are prompt 03's.
- **D4 contract parity**: routes, statuses and pre-validation hold (16, 17). The limiter order failed and is fixed (V-D4-1); phone input fails, open (V-D4-2); the header document is corrected (V-D4-3). Drift since the inventory: only commit 553dd15 (row 10, now closed) and one comment in `Security.cs` (`9276c51`).
- **D5 domain and time**: phone parity fails (V-D4-2). Token lifetime edges equal .NET: valid while `nbf <= now <= exp`, zero skew (`tokens.verify`). PIN rules are equal (3).
- **D6 database craft**: n/a (prompt 04 has no `db/` files). `db verify` was re-run: 21 checks ok.
- **D7 performance**: statement budgets hold (28). The PIN pool bounds the threads (7); saturation is V-D7-1.
- **D8 operability**: mail timeouts hold (`send_now` `wait_for`). No secrets in logs (29; note V-D8-2). The `XCODE_*` sweep found `XCODE_EMAIL_TLS` added and present in `settings.py`, `.env.example`, `docs/08` and `test_settings.py`. The port check was moved to startup (V-D8-1).
- **D9 hosting**: loopback mail relay fixed (V-D9-1). Measured: local PostgreSQL 16.15; CI declares `postgres:18` (`.github/workflows/xcode-api.yml:63`) but the workflow is untracked and has never run.
- **D10 tests as evidence**: a test pinned a wrong behaviour twice (the limiter order; the NBSP phone vector). `test_smtp_mailer.py` asserted private attributes only (grade C) and now has a real SMTP exchange. Sweep: no `skip`, `xfail` or bare `except` in the scope's tests. `sleep` appears in `test_pin_hasher.py` (pool scheduling, 5 ms), `test_auth_contract.py:357,651` and `support/client.py` (mail delivery polling); each waits for an observable state, not for time. No TODO or plan ids (the `XXX` hit at `values.py:148` is a format pattern).
- **D11 documents**: `docs/06` s1.4, s1.5 and s2.1, `docs/07` s2, `docs/08` s2 (two rows), `docs/12` s7, `docs/13` q67 and drift row 10 in `docs/prompts/README.md` were corrected in this run.

## 5. Per mode

**Assumptions** (where stated → what enforces it): "the limiter sat on the group, so it runs after authentication" (`docs/06` s1.5) → nothing; false (V-D4-1). "Only non-ASCII digits differ from .NET" (`docs/07` s10 row 5) → the vectors pin a broader refusal (V-D4-2). "Mail is encrypted outside development" (`mail.py`) → the port rule, which left no loopback path (V-D9-1). "One derivation per attempt" → `PinHasherSpy` (holds). "The signing key digests codes and tokens, and a rotation ends refresh tokens" (`docs/07:266`) → `KeyedDigester(settings.auth_signing_key)` (holds, documented).

**Falsification**: claims table above. Five falsified, each by a concrete input or the .NET source.

**Pre-mortem** (likelihood × impact): (1) cutover day on the cPanel host: no code mail, new phones locked out → high × high, V-D9-1, fixed. (2) a promotional week brings many sign-ins plus a scripted burst: the pool fills and everyone gets 503 → medium × medium, V-D7-1, recorded. (3) office staff paste numbers from a spreadsheet with no-break spaces and are told their number or PIN is wrong → low × medium, V-D4-2, q67. Inversion: what would guarantee failure is a host with a plaintext loopback relay plus TLS forced by port. That condition existed until this run.

**Red team**: outsider (unthrottled 401 surface on A12/A13 → fixed; pool saturation → residual; enumeration through byte-for-byte answers → defended, claim 26); dismissed employee (old access token after removal → 401 from the session check, tested; refresh replay → family revoked, tested); compromised neighbour (holding `xcode_app` it can pass `p_skip_cooldown` and its own code hashes; conceded, because that credential already mints codes); log reader (recipient hash, V-D8-2).

**Dialectic**: (a) charge bearer routes after authentication, so attackers without tokens cost nothing and are not counted? Counter: .NET counted them, `docs/12` promises it, and counting is stricter. Changed, high confidence. (b) Refuse every non-ASCII character to keep the SQL twin simple? Counter: a released web client sends raw input that .NET accepted. Kept open as q67, default follow .NET, medium confidence. (c) TLS by port (Python) or a flag (.NET)? Kept port-derived TLS and added a flag that can only turn it off for loopback, high confidence. (d) Derive before the code check in PIN completion (one round trip, uniform cost) or after (as .NET)? Kept: it does not add a new attack class (V-D7-1 covers it), medium confidence.

## 6. Conceded

- Envelope 503 versus problem-details 503 at pool capacity: both clients treat any status of 500 or more as unavailable (`apps/web/app/api/auth/[...path]/route.ts:201`, `apps/mobile/src/lib/api.ts:219`).
- Lengths in code points rather than UTF-16 units: a recorded deviation (`docs/07` s10 row 4).
- Refresh tokens die on a key rotation: documented (`docs/07:266`), and .NET has no rotation at all.
- `version` claim with leading zeros refused: only tokens this service signs carry it.
- Revoke with `%2F` in the id: .NET and Python both answer 403.
- `LogMailer` in production: refused by `_check_mail`.
- `skip_cooldown` passed by the caller: see red team.
- `Email.parse` narrower than `MailAddress.TryCreate`: recorded (`docs/07` s10 row 3).

## 7. Fixes

| finding | files | test failing before, passing after |
|---|---|---|
| V-D9-1 | `infra/mail.py`, `settings.py`, `container.py`, `.env.example`, `docs/08`, `docs/prompts/README.md` | `tests/unit/test_smtp_mailer.py::test_a_relay_on_this_machine_takes_mail_without_tls[*]`, `::test_mail_without_tls_is_refused_to_a_relay_on_another_machine[*]`; `tests/unit/test_settings.py::test_email_tls_is_on_by_default`, `::test_email_without_tls_is_refused_for_a_relay_on_another_machine[*]`, `::test_email_without_tls_is_allowed_for_a_relay_on_this_machine[*]`, `::test_email_without_tls_is_allowed_for_any_relay_in_development` (14 failed before) |
| V-D4-1 | `http/routers/auth.py`, `docs/06`, `docs/07` | `tests/api/test_auth_contract.py::test_the_rate_limit_counts_bearer_routes_before_authentication[*]` and `::test_the_rate_limit_answers_429_per_forwarded_client_address` (both `assert 401 == 429` before) |
| V-D8-1 | `settings.py`, `docs/08` | `tests/unit/test_settings.py::test_an_smtp_port_without_tls_is_refused_at_startup_outside_development[*]` (2 failed before) |
| V-D4-3 | `docs/06` | document only |
| V-D7-1 | `docs/12` s7 | residual risk |
| V-D4-2 | `docs/13` q67; fix by verify-03 (`domain/values.py`, `normalize_phone.sql`, `tests/support/phone_vectors.py`) | verify-03's report holds the failing-first evidence |

## 8. Commands and outputs

- Environment: `SELECT version()` gave PostgreSQL 16.15 (Visual C++ build 1944); `python --version` gave 3.13.2. The CI image is `postgres:18`; the workflow is untracked, so it has never run. One derivation of `pbkdf2_hmac` with 210 000 iterations took 1.207 s (machine at 100 % CPU, 0.5 to 0.9 GB free).
- Template: the stale `xcode_template` fingerprint `17b91e68…` did not match the files (`7a8b76ad…`), so this run used a private `XCODE_TEST_TEMPLATE=xcode_template_v04`, built by the harness and dropped at the end.
- Baseline before any change (`pytest -n 3`, 25 modules: the unit modules of the scope, `test_layers`, `test_settings`, `test_smtp_mailer`, `test_mail_queue`, `tests/db/test_fakes_match_routines.py`, `test_auth_routines.py`, `tests/api/test_auth_contract.py`, `test_openapi.py`, `test_contract_released_clients.py`): **854 passed in 1340 s**.
- After the fixes: `tests/api/test_auth_contract.py tests/api/test_openapi.py`: 47 passed in 475 s. `tests/unit` plus `tests/api/test_contract_released_clients.py`: 838 passed, **3 failed**. The failures are `test_sign_in_and_unlock_on_a_trusted_phone`, `test_a_paused_account_shows_the_timer_on_its_trusted_phone` and `test_a_new_phone_verifies_with_an_email_code`, all 500 on sign-in. They are attributed to verify-03's in-flight change to `auth_sign_in.sql` (20:29) and `application/auth/sign_in.py` (20:24), claimed on the board. The same tests passed in the baseline, and this run did not touch sign-in. `tests/unit/test_settings.py test_smtp_mailer.py test_cli.py` after the last fix: 142 passed.
- `ruff check .`: all checks passed. `ruff format --check`: one file would be reformatted, `tests/db/test_access_routines.py`, which is not this session's (verify-05's scope). `mypy`: no issues in 153 files.
- `xcode-api db verify` (development, CLI database `xcode`): 21 checks ok, exit 0.
- Full suite: shared run 1 (verify-03, `pytest -n 3 -q -p no:cacheprovider`, template `xcode_template_v03e` built at 21:31; this run's last code change was `settings.py` at 20:33). Log: `C:/Users/user/AppData/Local/Temp/claude/c--Users-user-Documents-Coding-PrioriTech-xcode-wt-revenue/a8d2101e-c659-4330-a63a-c957132463b2/scratchpad/full.log`. Read by this session: **4242 passed, 6 warnings in 3806.80 s (1:03:26)**, `exit=0 secs=3817 end=22:34`, no `FAILED` or `ERROR` line. The 6 warnings are PyJWT `InsecureKeyLengthWarning` from `tests/unit/test_tokens.py` forging HS384/HS512 tokens with the 36-byte test key (test-only; HS256 needs 32 bytes and production keys are checked at startup). The three released-client 500s of 21:05 pass here, which confirms the attribution to verify-03's in-flight change.
- After the run: `ruff format --check .` 334 files formatted (the earlier flag on `tests/db/test_access_routines.py` is gone); `ruff check .` all checks passed.

## 9. Regressions and misses against earlier audits

- prompt-00 V-D8-6 (port rule at startup) was handed to drift row 10's owner and still open: fixed here (V-D8-1).
- docs V-D4-6 (`WWW-Authenticate` addition) had the synthesis "record as an accepted addition in `docs/06`", which was never applied: applied here (V-D4-3).
- prompt-00 claim C28 ("auth rate limit holds") and the 04/05 validation of 2026-10-10 missed V-D4-1. The validation wrote the false ".NET parity" sentence and the test that pinned it.
- Missed by every earlier pass: V-D4-2 (the vector table pins it), V-D9-1 as a fixable defect (it was registered as drift but nobody owned it), V-D7-1 as an availability risk.

## 10. For the user

Nothing irreversible or purely business. Question 67 (phone characters) was technical and
is resolved by verify-03 with the .NET behaviour.
