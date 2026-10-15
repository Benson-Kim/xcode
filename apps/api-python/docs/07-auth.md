# Authentication

How sign-in, device trust, verification codes, PINs, tokens and lockout work in the
Python API, with the same wire behaviour as the .NET API. Source:
`docs/inventory/inventory-auth.md` (cited as `inv-auth 2.1`), the auth rows of
`docs/06-http-contract.md` (A01 to A13, the envelope, the byte-for-byte rule) and
`docs/04-schema.md` section 3 (tables). Routine signatures are in `docs/05-routines.md`
section 3. Where this document and the .NET code disagree, the code and `AuthTests` win.
The design notes v2.33 change sign-in (number first, a lock until reset, 3 code tries,
hashed device tokens; the design register in `docs/prompts/README.md`, rows B1 to B8).
Python builds them ahead of .NET (`docs/13-open-questions.md` question 46). Section 12 is
that model, written by the design session of prompt 07b and built by its session D1 on
2026-10-12; where sections 1 to 11 and section 12 differ, section 12 is what the code does
(the timed pause of section 4, the untrusted-device cap of 10, five code tries, the
per-purpose cooldown, the organization PIN-length minimum and the mail text of section 7 are
retired). Section 12.16 lists what the build decided where section 12 was silent. Questions
47 and 54 hold the constraints.

Division of labour (`docs/01-architecture.md`): secrets and cryptography stay in the
process (`security/`); every decision that reads or changes account state is a routine
(`api.auth_*`); the use case in `application/auth/` orders the two and shapes the envelope;
`domain/policies.py` holds the pure rules (PIN shape, uniform refusal, dummy-hash rule).

## 1. Parameters

| Parameter | Value | Setting |
|---|---|---|
| PIN hash | PBKDF2-HMAC-SHA256, 210 000 iterations, 16-byte random salt, 32-byte key; stored `base64(salt) + "." + base64(key)` with padding; compared in constant time; run on the hasher's own pool of 2 threads (never asyncio's default executor) with at most 16 more waiting; past that a request is refused with `TransientFailure` (503, `Retry-After: 1`) before any decision routine runs, so nothing is counted and no code is spent, and a slot is freed when its derivation ends, not when its caller leaves. A burst of sign-ins can therefore neither grow the process's threads (a shared host caps them per account) nor queue unbounded work | fixed (`security/pins.py`; `tests/unit/test_pin_hasher.py`, `tests/api/test_auth_contract.py::test_pin_hashing_at_capacity_answers_503_before_any_decision`) |
| Dummy hash | the hash of `5826` computed once per process (by the hasher the container builds) with a fresh salt; verified against when the account is unknown, removed or has no PIN, so A01/A02 always run one derivation | fixed |
| PIN shape for new PINs (`domain/policies.py`) | 4 to 8 ASCII digits, not all one digit, not a +1 or -1 run; refusal `invalid_pin` with `minimumPinLength` 4 (the floor), before any lookup | fixed |
| Policy PIN length | organization `pin_length` 4..8 (default 4); a shorter new PIN is refused `invalid_pin` with `minimumPinLength` = the policy value, disclosed only after a valid code (`inv-auth 2.5`) | per organization |
| Keyed digest | HMAC-SHA256 over the UTF-8 value, key = the signing key bytes, upper-case hex (64); used for codes and refresh tokens | `XCODE_AUTH_SIGNING_KEY` |
| Refresh token | 48 random bytes, standard Base64 (64 characters); only the digest is stored (`identity.refresh_tokens.token_hash`, unique) | fixed |
| Verification code | 6 decimal digits, zero padded, from a CSPRNG; only the digest is stored; lifetime 10 minutes inclusive (`now <= expires_at`); 5 wrong tries consume it; bound to user, purpose and device | fixed |
| Code issue limits | cooldown 60 s per user and purpose across devices (consumed codes count, withdrawn ones do not); 5 codes per rolling hour and 10 per rolling day per user across purposes and devices; a refused issue is silent: the endpoint still answers 202 and nothing is stored or mailed | fixed (`identity.code_caps`) |
| Lockout | trusted-device threshold `lockout_threshold` 3..10 (default 5); pause `lockout_minutes` 1..60 (default 15); untrusted-device cap 10 per account (constant `UNTRUSTED_DEVICE_LIMIT`) | per organization; the cap is fixed |
| Access token | JWT HS256, header `{"alg":"HS256","typ":"JWT"}`, claims `sub`, `device`, `version` (security version as a string), `org`, `role`, `first_name`, `last_name`, `permission` (string when one, array when several), `nbf` = issue time, `exp` = `nbf` + `access_token_minutes` (1..15, default 10), integer seconds, no `iat`, no `jti`; zero clock skew; issuer and audience validated | `XCODE_AUTH_ISSUER` (`xcode-api`), `XCODE_AUTH_AUDIENCE` (`xcode-clients`) |
| Refresh lifetime | `refresh_token_days` 1..90 (default 30) | per organization |
| Trusted-device lifetime | `XCODE_AUTH_TRUST_LIFETIME_DAYS` empty = never; a positive integer sets `trust_expires_at = now + days` on every trust; `<= 0` refuses startup | setting |
| Signing key | at least 32 UTF-8 bytes outside development and testing (exit 2); development and testing generate a 48-byte key per process when empty; `XCODE_AUTH_PREVIOUS_SIGNING_KEYS` are verify-only keys for access tokens during a rotation (codes and refresh digests use the current key only, as in .NET, so a rotation ends outstanding codes and refresh tokens; `docs/08-operability.md` section 10) | settings |
| Request pre-validation | `deviceId` 1..128, `phoneNumber` <= 14, `email` <= 320 and a valid address when non-empty, `pin` <= 8, `code` <= 32, `refreshToken` <= 256; `null` for any field is a refusal; lengths in code points (accepted deviation: .NET counted UTF-16 units; clients send ASCII); a field holding U+0000 or an unpaired surrogate (text PostgreSQL cannot store), a body that is not JSON, not an object or has a non-string field, and a body sent without a JSON content type are `invalid_request` too (.NET answered the last three with an empty framework 400 and stored the first) | fixed |
| Phone normalisation | strip every character that is not a decimal digit (as .NET's `\D`, so spaces, no-break spaces, direction marks and dashes go); a decimal digit outside `0-9` (Unicode `Nd`) makes the input "not a number"; `254[17]\d{8}`, `0[17]\d{8}`, `[17]\d{8}` give `+254[17]\d{8}`; else not a number (no lookup) | `identity.normalize_phone` and its Python twin, parity-tested |
| Account lookup | by normalised phone only; `email` in the request is never a lookup key | |
| Rate limit | policy `auth`: 60 s fixed window, `XCODE_RATE_LIMIT_AUTH_PER_MINUTE` permits (30; 10000 in testing), partition = client address after trusted-proxy processing; 429 empty body with `Retry-After` (`docs/06-http-contract.md` section 1.8) | setting |
| Development conveniences | `XCODE_DEVELOPMENT_CODES=true` (refused unless `XCODE_ENV=development`): A01/A02 and A04/A07 return the issued code as `developmentCode` and the resend cooldown is skipped; `XCODE_MAIL_BACKEND=log` logs the code. This replaces the .NET substring test on the connection string (`inv-auth 11.6`) | settings |

## 2. The frame every `/auth` route runs in

1. Rate limit (a dependency of every route), 429. It runs before the handler, as the
   .NET limiter middleware did, so malformed requests are throttled too: a body that does
   not parse is refused by the framework before any dependency runs, and the auth router
   then charges the limit itself before answering `invalid_request`; on the two bearer
   routes it runs before authentication too, so a missing or bad token is charged.
2. Pre-validation of the six request strings (section 1), `400 invalid_request`, no
   database access.
3. The use case calls one or two routines (section 3). Each routine locks the account row
   (`SELECT ... FOR UPDATE` on `identity.users`) as its first write-side statement, so
   concurrent attempts on one account are serialised in the database, not in the process.
   Flows that have no account yet (unknown number) or no account at all (refresh, sign-out
   with a bad token) take a transaction-level advisory lock on `hashtext('device:' ||
   device_id)` instead. Replaces the .NET in-process `AuthGate` semaphore and the
   SERIALIZABLE transaction (`inv-auth 2.11`, question `11.2`); isolation is READ COMMITTED.
   The gateway retries `40001`/`40P01` only for the two reads (`api.auth_account_lookup`,
   `api.auth_resolve_session`); a decision routine that hits one answers 503 and the client
   repeats the request, which the row lock then serialises.
4. A refusal (`authentication_failed`, `paused`) still commits what the routine changed
   (counters, consumed codes, revocations), exactly as .NET: the routine returns an outcome
   instead of raising. Only `XC4xx` errors and database failures roll back.
5. After the commit: mail (section 7), then the envelope (`docs/06-http-contract.md`
   section 1.6 A) with all seven properties in order.
6. Every decision routine writes one `identity.sign_in_attempts` row (the lookup only for an
   unknown number; code withdrawal and session resolution write none) with `operation`, `outcome`,
   `refusal`, `user_id` (null for unknown numbers), `phone_digest`, `device_id`,
   `request_id` (`docs/04-schema.md` section 3.5).

Deviation taken knowingly (`inv-auth 11.1`): .NET could commit state changes (device
trusted, code consumed, PIN set, old refresh token revoked) and still answer 401 when the
user had no active membership or role. The routines check "can receive tokens" (active
membership with a role) before changing state and answer `refused` (`refusal = inactive`)
with nothing changed. Reachable only with malformed data; the wire answer is identical.

## 3. Flows (check order per routine; outcomes use the envelope vocabulary)

### 3.1 A01 sign-in and A02 unlock (two statements)

`api.auth_account_lookup(p_request_id, p_phone, p_device_id, p_now)` returns the account
state or no row; the service then runs PBKDF2 against the stored hash or the dummy hash
and calls `api.auth_sign_in(p_request_id, p_user_id, p_device_id, p_pin_ok,
p_checked_pin_hash, p_code_hash, p_refresh_token_hash, p_skip_cooldown, p_now)`, where
`p_checked_pin_hash` is the stored hash the verdict was computed against (null for the
dummy hash). The two statements are two transactions, so a PIN set or reset can commit
between them: the routine reads `pin_hash` under the row lock and treats the verdict as a
wrong PIN when it differs from `p_checked_pin_hash` (.NET verified inside its gate and
SERIALIZABLE transaction, so an old PIN never passed after a reset). The decision inside
`api.auth_sign_in`, in order:

1. No account, status `removed`, or no PIN: `refused` (`unknown_number` is recorded by the
   lookup for an unknown or non-normalising number, and again by this routine with the
   digest of the empty string, so an unknown number leaves two attempt rows; `inactive`/
   `no_pin` here). The service still ran one derivation.
2. `paused_until` set and `now >= paused_until`: clear the pause (`failed_attempts = 0`,
   `paused_until = null`) and continue.
3. Still paused: trusted device -> `paused` with `retry_after_seconds =
   ceil(paused_until - now)`; untrusted device -> `refused` (`paused_untrusted`). No counter
   moves, whatever the PIN.
4. `trusted` = a device row for (user, device) not revoked and not expired.
5. Untrusted and `untrusted_failed_attempts >= 10`: `refused` (`untrusted_cap`), whatever
   the PIN; no counter moves (a lapsed pause is still cleared, as on every path past step 3).
6. PIN wrong, trusted: `failed_attempts + 1`; below `lockout_threshold` -> `refused`
   (`wrong_pin`); at or above -> `paused_until = now + lockout_minutes`, `paused` with
   `retry_after_seconds = lockout_minutes * 60` (the Nth wrong PIN shows the timer;
   `failed_attempts` stays at the threshold). Without an active membership the built-in
   defaults (5 and 15) apply, so wrong PINs count even on an account that can receive no
   token.
7. PIN wrong, untrusted: `untrusted_failed_attempts + 1` -> `refused` (`wrong_pin`).
8. PIN right, untrusted: no membership or role -> `refused` (`inactive`); else issue a
   `new_device` code when the cooldown and caps allow (`identity.code_caps`,
   `identity.supersede_codes`, insert the row with `p_code_hash`) -> `verification_required`
   with `masked_email` and `code_issued` true or false. Lockout counters untouched.
9. PIN right, trusted: no membership or role -> `refused` (`inactive`); else clear the
   pause and `failed_attempts` (`untrusted_failed_attempts` untouched), insert the refresh
   token, `identity.touch_version` -> `authenticated` with the claim material.

The service generates the code before the call (so it can mail it) and the refresh token
before the call (so it can return it); both are discarded when the routine does not use
them. `masked_email` = first character of the stored email, `***`, then everything from the
first `@`; `***` alone when there is no `@` or it comes first.

### 3.2 A03 verify-device (one statement)

`api.auth_verify_device(p_request_id, p_phone, p_device_id, p_code_hash,
p_refresh_token_hash, p_trust_days, p_now)`: unknown, removed, PIN-less or paused (a lapsed pause counts
as not paused and is not cleared) -> `refused`; newest unconsumed `new_device` code for
(user, device): none, expired or at 5 failures -> `refused`; digest mismatch ->
`failed_attempts + 1` on that code (the fifth consumes it) -> `refused`; no membership or
role -> `refused`; else consume the code, clear the pause and `failed_attempts`, set
`untrusted_failed_attempts = 0`, upsert the trusted device (`revoked = false`,
`trust_expires_at` per setting), insert the refresh token, `touch_version` ->
`authenticated`. No PBKDF2 runs in this flow.

### 3.3 A04 setup-pin/request and A07 pin-reset/request (one statement)

`api.auth_request_code(p_request_id, p_phone, p_device_id, p_purpose, p_code_hash,
p_skip_cooldown, p_now)`:
the account is "ready" when active and (for `first_setup`) has no PIN or (for `pin_reset`)
has one; not ready, cooldown or a cap -> `silent`; else supersede (consume, keeping their
expiry so they still count toward the caps) older codes of the same
user and purpose on every device, insert the row -> `check_email` with the recipient
address. The endpoint answers `202 check_email` in both cases; `developmentCode` only when
issued and development codes are on. No pause or device-trust check: a paused account may
reset its PIN, and completing the reset lifts the pause.

### 3.4 A05 setup-pin/verify and A08 pin-reset/verify (one statement)

`api.auth_verify_code(p_request_id, p_phone, p_device_id, p_purpose, p_code_hash, p_now)`:
not ready -> `refused`; newest unconsumed code for (user, device, purpose): none, expired
or at 5 failures -> `refused`; mismatch -> `failed_attempts + 1` (fifth consumes) ->
`refused`; match -> `code_verified`, the code is kept for the completion.

### 3.5 A06 setup-pin/complete and A09 pin-reset/complete (one statement)

The service checks the PIN shape first (`invalid_pin`, `minimumPinLength` 4, no database
access; a PIN over 8 characters never gets here), hashes the PIN, then calls
`api.auth_complete_pin(p_request_id, p_phone, p_device_id, p_purpose, p_code_hash,
p_pin_length, p_pin_hash, p_refresh_token_hash, p_trust_days, p_now)`: not ready -> `refused`; the
code as in 3.4 (a wrong code counts a failed try) -> `refused`; `p_pin_length <
policy.pin_length` -> `invalid_pin` with `minimum_pin_length` = the policy value (the
built-in 4 without an active membership, so this check precedes the next), code not
consumed, nothing else changed; no membership or role -> `refused`; else, in this order:
consume the code; set `pin_hash`; `untrusted_failed_attempts = 0`; `security_version + 1`
(every outstanding access token dies); clear the pause and `failed_attempts`; revoke every
live refresh token of the user on every device; consume every unconsumed code of the user
(all purposes and devices); trust this device; insert the new refresh token;
`touch_version` -> `authenticated`. Both purposes behave the same once the code matches.

### 3.6 A10 refresh (one statement)

`api.auth_refresh(p_request_id, p_token_hash, p_device_id, p_new_token_hash, p_now)`, lock
on the token's user row (advisory `device:` lock when the token is unknown): token unknown
or its `device_id` differs -> `refused`, nothing written; user not active -> revoke every
live token of the user -> `refused`; token already revoked (replay) -> revoke every live
token of the user on that device -> `refused` (`token_replayed`; the device stays trusted);
expired, user paused, or device not trusted -> `refused`, nothing written; no membership
or role -> `refused`, nothing written; else revoke the presented token (`version + 1`),
insert the new one, `touch_version` -> `authenticated` with freshly read role, names,
permissions and security version (this is how clients pick up admin changes).

### 3.7 A11 sign-out (one statement)

`api.auth_sign_out(p_request_id, p_token_hash, p_device_id, p_now)`: when a token row
matches both the digest and the device, revoke every live token of that user on that
device; always `signed_out`. Device trust and outstanding access tokens are untouched (they
live until `exp`).

### 3.8 A12 devices/{id}/revoke (bearer; two statements)

Session resolution (3.10) then, after the service has checked that `{id}` equals the
token's `device` claim (403 empty body; this precedes the length pre-validation, so the 400
of `inv 2.2` is unreachable, `inv-auth 11.15`), `api.auth_revoke_device(p_request_id,
p_user_id, p_device_id, p_now)`: lock the user row; mark the device revoked if it exists;
revoke the user's live tokens on that device; consume the user's unconsumed codes for that
device; always `device_revoked`. The caller's own access token stops at once.

### 3.9 A13 session (bearer; one statement)

Session resolution only; the body is built from the token claims.

### 3.10 Session resolution for every bearer route

`api.auth_resolve_session(p_user_id, p_device_id, p_security_version, p_now)` after
signature, lifetime, issuer and audience validation: the user exists and is active, the
security version equals the `version` claim, and the device row is not revoked and not
expired; otherwise `XC401` -> 401 empty body with `WWW-Authenticate: Bearer`. No cache.
A pause is not checked here: tokens issued before a pause keep working; the pause blocks
sign-in, unlock and refresh only (parity).

## 4. Pause and lockout state machine

Per account, two independent counters on `identity.users`: `failed_attempts` with
`paused_until` (trusted devices) and `untrusted_failed_attempts` (untrusted devices).

| State | Definition |
|---|---|
| Open | no pause (or a lapsed one) and `untrusted_failed_attempts < 10` |
| Counting | open with `1 <= failed_attempts < lockout_threshold` |
| Paused | `now < paused_until` |
| Lapsed | `paused_until` in the past; treated as open; cleaned by the next A01/A02 |
| Capped | `untrusted_failed_attempts >= 10`; untrusted devices get the unknown-number answer; trusted devices are unaffected |

| Counter | Reset by | Never reset by |
|---|---|---|
| `failed_attempts`, `paused_until` | a lapsed pause (next A01/A02); a right PIN on a trusted device (A01/A02); A03 success; A06/A09 success; `api.ops_clear_pause` | token issue itself; refresh; sign-out; device revoke |
| `untrusted_failed_attempts` | A06/A09 success (a PIN set or reset); A03 success (a verified new device) | a right PIN on a trusted device; a lapsed pause; `api.ops_clear_pause` |
| a code's `failed_attempts` | nothing; the fifth failure consumes the code | |

Ways out of a pause or cap without an operator: wait, or complete a PIN reset by email
(A07 to A09), which clears both. With an operator: `xcode-api clear-pause` (section 9),
which clears the pause only.

## 5. Device trust and verification codes

| Purpose | Issued by | Account state | Checked by | Consumed by | Mail timing |
|---|---|---|---|---|---|
| `new_device` | A01/A02 (right PIN, untrusted device) | active with a PIN | A03 | A03 | before the reply; failure = code withdrawn, `503 service_unavailable` |
| `first_setup` | A04 | active, no PIN | A05 (kept) | A06 | after the reply |
| `pin_reset` | A07 | active, has a PIN | A08 (kept) | A09 | after the reply |

A code is found by (user, device, purpose), newest unconsumed only. A code ends early on
success, on the fifth wrong try, when a newer code of the same user and purpose is issued
(any device), on PIN set or reset (all codes of the user), on device revoke (the device's
codes) and on withdrawal after a failed send. A device becomes trusted only through A03 or
A06/A09; provisioning trusts nothing. `device_id` is a client-chosen opaque string of 1 to
128 characters.

## 6. Tokens and revocation

Issue (`api.auth_sign_in`, `api.auth_verify_device`, `api.auth_complete_pin`,
`api.auth_refresh`): the routine returns the claim material (organization, role, names,
effective permissions from `tenancy.effective_permissions`, security version, policy
lifetimes) and stores the refresh digest; the service signs the access token and returns
the raw refresh token once. Refresh rotation and replay detection are in 3.6.

| Event | Access tokens (checked per request) | Refresh tokens | Device trust |
|---|---|---|---|
| Sign-out (A11) | live until `exp` | that device's revoked | unchanged |
| Device revoke (A12) | that device's stop at once | that device's revoked | revoked |
| Security version bump (admin edit of name, role or single permissions; `api.people_update`) | all stop at once; refresh renews them | untouched | unchanged |
| Admin change of email or phone (`api.people_update`) | all stop | all revoked | all revoked (PIN kept; next sign-in needs a code) |
| Deactivate (`api.people_set_active` false) | all stop (status, version, devices) | all revoked | all revoked |
| Reactivate | nothing restored | nothing restored | nothing restored; devices re-trust by code |
| Admin sign out of every device (`api.people_sign_out`) | all stop (devices revoked) | all revoked | all revoked; security version unchanged |
| Operator remove (`api.ops_remove_user`) | all stop (status, version) | all revoked | unchanged rows (parity) |
| PIN set or reset (A06/A09) | all stop (version); the new pair belongs to the completing device | all revoked, then one new | completing device trusted |
| Operator revoke sessions (`api.ops_revoke_sessions`) | all stop (version) | all revoked | all revoked |
| Trust expiry | that device's stop at expiry | refresh refused | expired; A03 renews |
| Pause | unaffected | refresh refused while paused | unchanged |
| Signing-key rotation | old-key tokens verify until `exp` while the key is in the previous-keys list | all refused (digest key changed) | unchanged |

## 7. Enumeration resistance, timing and mail

Byte-for-byte rule (`docs/06-http-contract.md` section 2.1): unknown number, non-normalising
number, removed account, paused account on an untrusted device, capped account on an
untrusted device and a wrong PIN on an untrusted device all produce the same
`401 authentication_failed` body and headers; A04/A07 always answer `202 check_email`;
A06/A09 reveal the policy minimum only to a request with a valid code. A01/A02 always run
one PBKDF2 derivation; nothing else is time-equalised (parity, `inv-auth 6.2`), and no
artificial delay is added (`inv-auth 11.16`: not adopted).

Mail (`infra/mail.py`, `docs/prompts/00-bootstrap-app.md` D7): subject
`Your verification code`; body `Your {Purpose} code is {code}. It expires in 10 minutes.`
with `{Purpose}` one of `FirstSetup`, `NewDevice`, `PinReset` (the label map of the
purpose enum, kept because clients and people know the text); recipient = the stored
address, never the request's `email`. `new_device` mail is awaited before the reply with
`XCODE_EMAIL_TIMEOUT_SECONDS` (default 10; .NET had the 100 s framework default,
`inv-auth 11.7`); on failure the service calls `api.auth_withdraw_code(p_request_id,
p_code_id)` (a withdrawn code neither starts the cooldown nor counts toward the caps) and
answers `503 service_unavailable`. `first_setup` and `pin_reset` mail goes through the
in-process `MailQueue` after the reply; a failed send withdraws the code and logs
`mail.failed` with the purpose, the code id and the request id (the code id leads to the
user in the database; the outcome of a code issue carries no user id), never the code or
address; a failed withdrawal is logged as `mail.withdraw_failed` and swallowed. The log
mailer is allowed only in development and testing, where it also logs the body
(`mail.body`) so a developer can read the code.

## 8. Organization security policy

`tenancy.organization_security_policies` (`docs/04-schema.md` section 4.6) with the bounds
as `CHECK` constraints; `identity.policy_for` clamps on read as well, so a row written
before the constraints existed still yields in-range values. Fields auth reads:
`pin_length`, `lockout_threshold`, `lockout_minutes`, `access_token_minutes`,
`refresh_token_days`. The policy of a user is that of their single active membership;
built-in defaults when there is none; a saved policy applies from the next sign-in or
refresh and revokes nothing. `password_*`, `idle_unlock_seconds` and `allow_pin_sign_in`
are stored and served but never read by a flow.

## 9. Operator commands (`xcode-api`, role `xcode_operator`)

| Command | Routine | Behaviour |
|---|---|---|
| `provision-user --email --phone [--role] [--first-name] [--last-name] [--organization-name]` | `api.ops_provision_user` | parity with `--provision-user` (`inv-auth 9.1`): one organization per database (created with defaults and seeded roles when none; more than one is an error); the user is created active or re-activated with the new phone; names from the options or derived from the email local part; role from the option, the existing link, or `Owner`; a changed phone, status, membership or role bumps the security version and revokes every device and token; `Owner` and `Office admin` get an all-companies scope; the new person sets a PIN through A04 to A06 |
| `remove-user --email` | `api.ops_remove_user` | status `removed`, security version bump, every refresh token revoked; devices and membership untouched (parity) |
| `clear-pause --email` | `api.ops_clear_pause` | clears `paused_until` and `failed_attempts`; never the untrusted cap (new; .NET had no such command) |
| `revoke-sessions --email` | `api.ops_revoke_sessions` | security version bump; every device and token revoked (new) |
| `account-state --email` | `api.ops_account_state` | status, pause, counters, device and token counts for a support call; never a hash (new) |
| startup summary | `api.meta_unassigned_user_count` (as `xcode_app`) | the warning `{n} active users have no organization membership and cannot sign in` |

Every command records `ops.operator_actions` with `XCODE_OPERATOR` and prints ids and
counts only.

## 10. Decisions on the inventory's open questions

| `inv-auth 11` | Decision |
|---|---|
| 1 commit after failure | roll back by checking token eligibility first (section 2); wire-identical |
| 2 serialisation | row lock on the user plus an advisory `device:` lock; READ COMMITTED; gateway retry on `40001` |
| 3 email | addresses are validated as `local@domain` only (display-name forms refused, an accepted deviation recorded in `docs/13-open-questions.md`); stored lower-cased; unique on the lower-cased value |
| 4 lengths | code points; accepted deviation |
| 5 phone | non-ASCII digits are "not a number"; every other non-digit is stripped as in .NET (question 67); test vectors in the parity test, plus every non-ASCII `Nd` character |
| 6 development conveniences | `XCODE_DEVELOPMENT_CODES` and `XCODE_MAIL_BACKEND=log`, both refused outside development (log also in testing) |
| 7 mail robustness | 10 s SMTP timeout; after-reply mail through the bounded `MailQueue`; a crash loses queued mail and the code is still live (parity); an outbox table is a later extension |
| 8 cooldown counts consumed codes | copied |
| 9 pause not checked per request | copied |
| 10 JWT details | pinned by `tests/unit/test_tokens.py` byte for byte against a token built with PyJWT from the claim list of section 1; no captured .NET token is available yet (one joins the suite at cutover, `docs/10-data-migration.md` section 2) |
| 11 PIN rehash | not built; recorded in `docs/13-open-questions.md` question 6 |
| 12 refresh replay race | clients single-flight; the routine's behaviour is the .NET one |
| 13 several active memberships | the partial unique index of `docs/04-schema.md` section 4.2 makes it impossible |
| 14, 15 | corrected in the inventories by the drift pass |
| 16 timing | no dummy work added |
| 17 settings | all from the environment (`docs/08-operability.md`) |

## 11. Tests that pin this document

`tests/db/test_auth_routines.py` (every branch of section 3 with the attempt row, the
state machine of section 4, the revocation matrix), `tests/unit/test_policies.py` (PIN
shape, uniform refusal, dummy-hash rule, masking), `tests/unit/test_tokens.py` (claims,
header, lifetimes, previous keys), `tests/unit/test_pin_hasher.py` (format, a published
PBKDF2 vector and the full iteration count), `tests/api/test_auth_contract.py` (the thirteen routes, the envelope, the
byte-for-byte pairs with the `Seen` exclusions `Date`, `Content-Length`, `X-Request-ID`,
rate limiting, mail timing and the 503 path, development codes).

## 12. The sign-in model of the design notes v2.33 (built by prompt 07b D1)

The rules of `docs/design/XCODE_Build_Notes_v2.3.md` v2.33 sections 1 and 2 (rule ids
`DN-B1-*` to `DN-B8-*` and the decisions `DEC-1` to `DEC-8` of `docs/15-design-v2-3.md`),
specified for the build session D1 of `docs/prompts/07b-design-v2-3.md`. Sections 1 to 11
describe the model the code has today; once D1 lands, it folds this section into them and
deletes what it replaces. Where this section and sections 1 to 11 differ, this section is
the target. Routes are N01 to N09 (`docs/06-http-contract.md` section 2.12), tables
`docs/04-schema.md` section 13.1, routines `docs/05-routines.md` section 10.1.

### 12.1 Parameters that change

| Parameter | Value | Replaces |
|---|---|---|
| New PIN | exactly four ASCII digits; refused (in this order): not four digits (`length`); one digit four times, four consecutive digits of `0123456789` or of `9876543210`, or the last four digits of the person's own number (`weak`); the PIN being replaced (`unchanged`). `domain/policies.py` `new_pin_problem(pin, phone, replaced=None)` returns the first problem or `None` | `pin_shape_valid` (4 to 8 digits, all-equal and +1/-1 runs only) and `PIN_CEILING` for new PINs |
| PIN to verify | 1 to 8 characters (pre-validation unchanged); a PIN set before this model, of 5 to 8 digits, keeps verifying until its holder changes it | |
| Organization `pin_length` | stored, validated 4..8 and served as today (released web screens); read by no flow; `p_pin_length` leaves `api.auth_complete_pin`, and `invalid_pin` always carries `minimumPinLength` 4 | the policy minimum (`PinSetupService.cs:32-36`) |
| Wrong-PIN limit | `PIN_TRIES = 5` in a row per scope (section 12.5), one constant in `domain/policies.py` with its SQL twin `identity.pin_tries()` and a parity test | `lockout_threshold` and `lockout_minutes` for the decision; `UNTRUSTED_DEVICE_LIMIT` 10 |
| Code tries | 3; the third wrong try voids the code and a replacement is issued (section 12.6) | 5 |
| Code issue limits | at most one a minute per person (every purpose and device; consumed and superseded codes count, withdrawn ones do not), five per rolling hour, ten per rolling day; silent | one a minute per person and purpose |
| Device token | 32 bytes from `secrets`, Base64url without padding (43 characters), returned once as `deviceToken`; stored as `token_hash` = SHA-256 of its ASCII text, upper-case hex (`security/device_tokens.py`) | none (trust by `deviceId`) |
| Trusted-device lifetime | 90 days after `last_used_at` (`TRUSTED_DEVICE_IDLE_DAYS`, `identity.device_idle_days()`); `XCODE_AUTH_TRUST_LIFETIME_DAYS` stays an optional cap counted from the trust date | the fixed lifetime from the trust date |
| Device name | `deviceName` in the new routes' bodies: trimmed, 1 to 60 characters of `[A-Za-z0-9 .()+-]` starting with a letter or digit, else `invalid_request`; absent or empty = unknown (`NULL`); stored on the device row, shown in the profile and the people pane, used in the code email. The narrow alphabet is deliberate: a stranger can ask for a reset code for any number (N05) and so chooses the device line of a mail the real person receives; without `:`, `/`, `@` or quotes it cannot carry a link or an address (`docs/12-security.md` section 7) | none |
| Idle unlock | `idle_unlock_seconds` default 900 for new organizations (existing rows keep their value), served as `idleUnlockSeconds` in `GET /setup/appearance`; the clients ask for the PIN again after it (A02, or N02 with the device token) | default 300, not served |
| PIN throttle | rate-limit policy `auth_pin` on the routes that check a PIN (A01, A02, N02, N07): 20 per 10 minutes per client address and 10 per 10 minutes per `deviceId`, charged after the `auth` policy and before pre-validation; 429 empty body with `Retry-After`; settings `XCODE_RATE_LIMIT_PIN_PER_ADDRESS` (20), `XCODE_RATE_LIMIT_PIN_PER_DEVICE` (10), 10000 each in testing | the `auth` policy alone (30 a minute per address) |

### 12.2 The number step (N01 `POST /auth/start`, one statement)

Body `{phoneNumber, deviceId, deviceToken, deviceName}` (`deviceToken` and `deviceName`
optional). `api.auth_start` locks the account row (or takes the `device:` advisory lock when
there is no account) and answers, first match wins:

1. The number does not normalise or has no account: the **simulated account** of section
   12.14 a: `pin_locked` when the sign-in history holds five or more wrong-PIN tries for the
   number's digest, else `pin_required`. Nothing else is written but the attempt row.
2. Blocked (user `removed`, or no active membership with a role): `blocked` (403).
3. No PIN: issue a `first_setup` code for this device when the caps allow (silently
   otherwise) and answer `verification_required` with `purpose` `first_setup` and
   `maskedEmail`.
4. A forced reset is pending (`pin_reset_required`): the same with `purpose` `pin_reset`.
5. The PIN is locked for this device (section 12.5; a valid `deviceToken` makes the device
   trusted): `pin_locked` (423).
6. Otherwise `pin_required` (200).

No answer carries a name, a role or the PIN's length. Codes are mailed after the reply
(the `MailQueue`, as A04 and A07). Statement budget 1; `auth` rate limit only (no PIN is
checked).

### 12.3 The PIN step (N02 `POST /auth/pin`, two statements)

Body `{phoneNumber, deviceId, deviceToken, deviceName, pin}`. Statement one is
`api.auth_account_lookup` (it now returns the account state for a token-trusted device,
`docs/05-routines.md` 10.1); the service runs one derivation, against the stored hash or the
dummy hash (`needs_dummy_hash` also covers blocked, PIN-less and reset-due accounts), then
calls `api.auth_pin` with the verdict and the hash it checked. Under the row lock, first
match wins:

1. No account: the simulated account: past five recorded wrong tries `pin_locked`; else a
   wrong try is recorded and the answer is `authentication_failed` with `triesLeft`, or
   `pin_locked` when this try is the fifth.
2. Blocked: `blocked`, nothing counted.
3. No PIN, or a forced reset pending: issue the `first_setup` or `pin_reset` code and answer
   `verification_required` with that `purpose` (the PIN is not looked at).
4. The verdict is for a hash that is no longer stored (a PIN set or reset committed during
   the derivation): treated as a wrong PIN, as `api.auth_sign_in` does with
   `p_checked_pin_hash`.
5. Locked for this device: `pin_locked`, nothing counted.
6. Wrong PIN: the scope's counter + 1 (trusted: `failed_attempts`; untrusted:
   `untrusted_failed_attempts`); below five `authentication_failed` with `triesLeft` = 5 minus
   the count; at five the lock starts, the change log records it (section 12.11) and the
   answer is `pin_locked`.
7. Right PIN on an untrusted device: issue a `new_device` code (caps silent) and answer
   `verification_required` with `purpose` `new_device` and `maskedEmail`; the code is mailed
   before the reply, and a failed send withdraws it and answers `service_unavailable`
   (section 7). No counter moves.
8. Right PIN on a trusted device: `failed_attempts = 0`, `last_used_at` and
   `last_signed_in_at` = now, refresh token, `touch_version`: `authenticated`.

Statement budget 2 (3 when a new-device mail fails and the code is withdrawn). Throttled by
`auth` and `auth_pin`.

### 12.4 PIN rules

- Checked in the service before any hashing, with the number the request carries (the
  account is found by that number, so it is the person's own) or, for N07, the number the
  lookup returns. Every new PIN on every route: N06, N07, A06, A09.
- "The PIN being replaced": on N07 the current PIN is in the request, so the service
  compares the two strings. On a reset (A09, N06 with `pin_reset`) the old PIN is only a
  hash: the service verifies the new PIN against the stored hash (one more derivation on the
  PIN pool) and passes the verdict with the hash it checked; the routine refuses with
  `invalid_pin` (`pinProblem` `unchanged`) when the verdict holds for the stored hash. A
  first PIN has nothing to replace.
- The new routes answer `invalid_pin` with `pinProblem` (`length`, `weak`, `unchanged`) and
  `minimumPinLength` 4; the old routes answer `invalid_pin` with `minimumPinLength` 4 for
  every problem (the v2.11 envelope has no `pinProblem`). As today, a problem found by the
  routine (`unchanged`) is disclosed only to a request that carries a valid code, and the
  code is not consumed.
- PINs longer than four digits: a hash does not reveal its length, so such PINs cannot be
  found and forced to reset. They keep verifying on every route; their holders replace them
  when they reset or change the PIN. The new clients submit the PIN on its fourth digit, so
  on them a holder of a longer PIN uses "Forgot PIN" (decision `DEC-7`; client fact in
  `docs/06-http-contract.md` section 4).

### 12.5 The lock (replaces section 4)

Two counters on `identity.users`, both "in a row": `failed_attempts` counts wrong PINs on
trusted devices (scope **every device**), `untrusted_failed_attempts` wrong PINs on
untrusted devices (scope **new devices**). The fifth wrong PIN of a scope starts its lock;
the lock is the counter at five, so there is no lock column and nothing lapses.
`paused_until` is retired (`docs/04-schema.md` 13.1).

| State | Definition | Trusted device | Untrusted device | People status |
|---|---|---|---|---|
| Open | both counters below 5 | PIN checked | PIN checked | Active |
| Locked on every device | `failed_attempts >= 5` | refused, nothing counted; refresh refused | refused, nothing counted | Locked |
| Locked for new devices | `untrusted_failed_attempts >= 5`, the other below 5 | PIN checked | refused, nothing counted | Locked (the pane says "new devices") |

| Counter | Back to 0 on | Never on |
|---|---|---|
| `failed_attempts` | a right PIN on a trusted device (A01, A02, N02; the current PIN on N07); a verified new device (A03, N03 `new_device`); a PIN set, reset or change; `xcode-api clear-pause` | refresh, sign-out, a right PIN on an untrusted device not followed by its code |
| `untrusted_failed_attempts` | a verified new device; a PIN set, reset or change; `xcode-api clear-pause` | a right PIN on a trusted device |

The only ways out of a lock are a PIN reset with a code (A07 to A09, N05, N03, N06), which
clears both, and the operator's `clear-pause`, which clears both scopes (a person whose
email is not on the phone has no other way back, question 53; it is also the only lever for
a new-devices lock on a person with no live trusted device, whom a stranger can otherwise
brick with five wrong PINs; the action is audited in `ops.operator_actions`). A forced reset does not clear a lock; its completion does. The
answers to a locked account: N01/N02 `pin_locked`; A01/A02 on a trusted device `423 paused`
with `retryAfterSeconds` = the policy's `lockout_minutes` x 60 (the phone shows its paused
screen with "Reset PIN"; a retry after the countdown is paused again); A01/A02 on an
untrusted device the uniform 401.

Concurrency: `identity.lock_user` serialises every attempt on the account, so two wrong
PINs at once both count, and the fifth is decided once.

### 12.6 Codes

| Rule | Behaviour |
|---|---|
| Lookup | the newest unconsumed code for (user, device, purpose), as today |
| Wrong code | `failed_attempts + 1`; the third consumes it (void), and in the same transaction a replacement for the same user, purpose and device is issued when the hourly and daily caps allow (the one-a-minute rule does not apply to it, `DEC-8`); N03 answers `code_resent` (202); the old routes answer the uniform 401. The replacement is mailed after the reply |
| Expired, consumed, or none | `authentication_failed` (N03 with `triesLeft` null), the uniform 401 on the old routes; nothing issued |
| Resend (N04) | `purpose` in the body. `new_device`: only when a `new_device` code for this user and device was issued in the last 10 minutes (the PIN was right on this device); `first_setup`: only while the person has no PIN; `pin_reset`: only while a reset is pending or a `pin_reset` code for this device was issued in the last 10 minutes. The older code of the purpose is superseded. Always `verification_required`, issued or not |
| Caps | `identity.code_caps`: false when any non-withdrawn code of the person (any purpose, any device) is younger than 60 s (not for a replacement, nor with development codes), or five in the last hour, or ten in the last day. Superseded and voided codes count; withdrawn ones do not |
| Email | subject `Your verification code`; three lines and nothing else: `Code: {code}`, `For: {purpose words}` (`Confirm this device`, `First sign in`, `Reset PIN`, the prototype's step titles), `Device: {device name}` (`Unknown device` when the request named none: the old routes and the automatic replacement after an old-route try). Wording is question 62 |

### 12.7 Forced reset

`identity.users.pin_reset_required`, set by "Make [name] reset the PIN" (S45,
`people.sign_in`, `docs/05-routines.md` 10.3). At once and in one transaction: the flag is
set, every trusted device row of the person is revoked (remembered or not), every refresh
token revoked, every unconsumed code consumed, `security_version + 1` (every access token
stops at the next request), and the change log records "PIN reset required, {First Last}".
While it is set: N01 and N02 send a `pin_reset` code instead of asking for the PIN; A01 and
A02 answer the uniform 401 (refusal `reset_required`, nothing counted); a reset completion
(A09, or N06 with `pin_reset`) clears it, and the PIN being replaced is refused there. A
person without a PIN cannot be forced (`unchanged`): their first sign-in already needs a code.

### 12.8 Trusted devices and the device token

Row: `identity.trusted_devices` gains `token_hash`, `name`, `trusted_at`, `last_used_at`,
`remembered` (`docs/04-schema.md` 13.1). A device is **live** when it is not revoked,
`last_used_at` is within 90 days and `trust_expires_at` is null or later. It is **trusted
for a PIN-only sign-in**:
- on the new routes when it is live, remembered, and `token_hash` equals the digest of the
  `deviceToken` sent with the same `deviceId`;
- on the old routes when it is live, remembered and has no `token_hash` (trusted by
  `deviceId` alone, as every v2.11 phone is). A row that has a token is never trusted by its
  `deviceId` alone (`DEC-5`). The new routes pass a non-null token hash (empty when no
  `deviceToken` was sent, `identity.device_trusted` in `docs/05-routines.md` 10.1), so a
  request on a new route never reaches this legacy branch: a leaked `deviceId` cannot buy a
  PIN-only sign-in on a new route against a legacy row.

Session resolution (section 3.10) needs a live row for the token's `device` claim,
remembered or not. `last_used_at` moves to now whenever a session is issued or refreshed for
the device (sign-in, unlock, verification, completion, refresh), so a phone in use never
expires.

Trusting (N03 with `new_device`, N06, and the old A03, A06, A09): upsert on (user,
`deviceId`) with `revoked = false`, `trusted_at = last_used_at = now`, `name` from the
request, `trust_expires_at` from the setting. On the new routes `trustDevice` (default
true) decides: true gives `remembered = true` and a new token, returned once as
`deviceToken` (a later trust of the same row replaces the token); false gives
`remembered = false`, no token, a session for this sign-in only, and a code again at the
next sign-in (`DEC-6`). The old routes always trust, without a token. Signing out (A11) of a
device that is not remembered also revokes its row. The token is never logged: the
redaction processor drops `deviceToken` and `device_token` like `refreshToken`.

### 12.9 What removes devices

| Event | Trusted devices | Refresh tokens | Access tokens | Change log |
|---|---|---|---|---|
| First PIN (A06, N06 `first_setup`) | the completing device trusted (when asked, on N06) | one new | `security_version + 1` | "PIN set at first sign in" (and "Device trusted") |
| PIN reset (A09, N06 `pin_reset`, from a forgotten or forced reset) | every one revoked, then the completing device trusted again (always on A09, when asked on N06) | all revoked, one new | `security_version + 1` | "PIN reset with a code" (and "Device trusted") |
| PIN change (N07) | kept | kept | unchanged | "PIN changed" |
| Forced reset (S45) | every one revoked | all revoked | `security_version + 1` | "PIN reset required, {name}" |
| Block (S10, built) | every one revoked | all revoked | `security_version + 1` | "Removed access for {name}" (built) |
| Remove all (S11) | every one revoked | all revoked | unchanged (no session survives without its device) | "Trusted device removed, {name}" |
| Remove one (N09 own, S46 someone's, A12 own current) | that one | that device's | that device's stop (no live row) | "Trusted device removed" (", {name}" when someone else removes it) |

### 12.10 Sign-in history

`identity.sign_in_attempts` is the sign-in history: one row per decision, as today, with the
new operations (`start`, `pin`, `code`, `resend_code`, `forgot_pin`, `new_pin`,
`change_pin`, `remove_device`) and outcomes (`pin_required`, `pin_locked`, `blocked`,
`code_resent`, `pin_changed`), never served whole over HTTP. `identity.users.last_signed_in_at`
is set when a sign-in issues a session (not on refresh) and is the "last sign-in" of the
people list and pane. Ordinary sign-ins never reach `tenancy.change_log` (DN-B8-2).

### 12.11 Change-log entries (DN-B8-1)

Section `signIn` (`docs/04-schema.md` 13.3), entity = the person's user id, actor = whoever
acted (the person for their own sign-in events; the administrator for S11, S45, S46). The
reason is the notes' phrase, verbatim; when the actor is not the person, `, {First Last}`
follows (the prototype's form). When one call does two of them (a completion that trusts
the device), the phrases are joined with `; ` in event order, so each routine still calls
`tenancy.record_change` once. Snapshots: `before` and `after` are
`tenancy.sign_in_snapshot(user)` taken before and after the change:
`{"Status": <people status word>, "Devices": [<names of live remembered devices, null for unnamed>]}`.

| Phrase | Written by |
|---|---|
| `PIN set at first sign in` | A06, N06 (`first_setup`) |
| `PIN reset with a code` | A09, N06 (`pin_reset`) |
| `PIN changed` | N07 |
| `PIN locked after 5 wrong tries` | the wrong PIN that brings a scope's counter to five (A01, A02, N02, N07); the snapshot's `Status` becomes `Locked` |
| `Device trusted` | A03, N03 (`new_device`), and joined to the PIN phrase on A06, A09 and N06 when the device is remembered |
| `Trusted device removed` | A12, N09, S46, S11 |
| `PIN reset required` | S45 |

Unknown numbers and people without an active membership write no change-log row (there is
no organization to write it in).

### 12.12 The profile routes

- **N07 change PIN** (bearer; body `{currentPin, newPin}`; the repeat is checked by the
  client): `new_pin_problem` on the new PIN with the lookup's number and the current PIN;
  `api.auth_account_lookup` by user; one derivation verifies the current PIN, one hashes the
  new one; `api.auth_change_pin` under the row lock: verdict on a changed hash = wrong;
  locked on every device -> `pin_locked`; wrong current PIN counts as a trusted-device wrong
  PIN (`authentication_failed` with `triesLeft`, the fifth locks and logs); right -> new hash,
  both counters 0, "PIN changed", answer `pin_changed` (200, no tokens; sessions and devices
  stay). Budget 3; throttled by `auth_pin`.
- **N08 own trusted devices** (bearer): the caller's live remembered rows, newest use first:
  `{id, name, trustedAt, lastUsedAt, thisDevice}`. Budget 2.
- **N09 remove own device** (bearer; `{id}` = the row's id): revoke it, its refresh tokens
  and codes; log; an id that is not the caller's live row is 404 empty. Removing "this
  device" ends the caller's session at once. Budget 2.

### 12.13 The thirteen released routes under this model

| Route | Change (notes require it) |
|---|---|
| A01, A02 | counters and lock of section 12.5; refusal `reset_required` for a pending forced reset; trusted only by a legacy row (no token); `last_used_at`, `last_signed_in_at`; `auth_pin` throttle; the 423 `paused` answer now means "locked until reset" |
| A03 | three tries with the automatic replacement; success resets both counters, trusts by `deviceId` (legacy row), logs "Device trusted" |
| A04, A07 | the caps of section 12.6 |
| A05, A08 | three tries with the automatic replacement |
| A06, A09 | the PIN rules of 12.4 (`invalid_pin` with `minimumPinLength` 4); A09 removes every device first; logs; clears a forced reset |
| A10 | refused while locked on every device or when the device is not live; moves `last_used_at` |
| A11 | also revokes a not-remembered row |
| A12 | logs "Trusted device removed" |
| A13 | none |

The envelope (seven properties) and the byte-for-byte refusals of section 7 are unchanged:
on these routes, an unknown number, a blocked account, a wrong PIN or a lock seen from an
untrusted device, and a pending forced reset all answer the same 401.

### 12.14 Threats decided here

**a. The number step tells who has an account (DN-B1-5, `DEC-2`).**

- For answering truthfully (the notes): the screen flow needs it. A person without a PIN
  must go to a code, a person with a forced reset too, and a blocked person must be told to
  speak to the office; anything else adds a dead end. The notes accept the leak "where
  possible", and the number alone is not a credential: every next step needs a PIN or the
  person's email.
- Against: an outsider with a list of numbers learns at once which numbers are customers'
  staff, which of them have never signed in (new, so likely to click a phishing mail about
  their "first sign in"), which are blocked (former staff), and makes the server mail codes to
  them.
- Decided: the answers that leak are only the three the flow needs. An unknown number gets
  `pin_required`, the same bytes as a real account with a PIN, and the PIN step simulates an
  account for it: `triesLeft` counts down from the wrong tries recorded for that number's
  digest in the sign-in history, the fifth answers `pin_locked`, and every later visit to
  the number step answers `pin_locked`, exactly as for a real account locked for new
  devices. "Forgot PIN" for it answers `verification_required` (no mail), and its code step
  counts down three wrong tries and answers `code_resent` (the history again), as for a real
  account. N04 and N05 carry no `maskedEmail` for anyone, since an unknown number has no
  address to mask; the code step reached from them shows no address. Timing: the number step runs no derivation for anyone; the PIN step runs one for
  everyone (the dummy hash for unknown, blocked, PIN-less and reset-due accounts). The code
  mail is sent after the reply, so issuing one costs the same as not.
- Residual risk (`docs/12-security.md` section 7): the number step tells an outsider that a
  number belongs to a person without a PIN, with a pending forced reset, or blocked; each
  such probe of a PIN-less or reset-due number mails a code, at most one a minute and five an
  hour per person. Mitigated by the `auth` limit per address, the code caps, and the sign-in
  history (`phone_digest` per attempt) for detection. Not mitigated: an outsider rotating
  addresses can sort a list of numbers into these three groups. A fourth, slower
  distinguisher remains: the simulated lock of an unknown number is counted from immutable
  history rows and never clears, while a real account's `untrusted_failed_attempts` resets
  on a verified new device or a PIN change (section 12.5); an outsider who locks a set of
  numbers and re-probes over days learns which ones re-open to `pin_required` — those are
  real, active accounts. It reveals only existence, not the PIN, and depends on owner
  activity (`docs/12-security.md` section 7).

**b. A stranger locks a person out (DN-B4-1, `DEC-1`).**

- For the notes' literal rule (one counter across devices, the fifth wrong PIN locks every
  device): device ids are chosen by the client, so any limit per device is void and only a
  per-person count stops guessing; a stolen trusted phone gets five tries and is then
  useless; recovery is self-service by email in a minute.
- Against: anyone who knows a number (a dismissed conductor, a rival fleet) locks that
  person out of every device with five taps, before the morning's revenue capture, and the
  person needs their email to get back in, which many crews do not have on their phone
  (question 53); the reset then removes all their trusted devices too. The per-device and
  per-address limits the notes name cannot stop it: five tries are under any sane per-address
  limit, and device ids rotate for free. And the literal rule is weaker against guessing than
  it looks: "reset to zero on a correct PIN" lets a stranger make four wrong tries, wait for
  the owner's next sign-in, and make four more, every day, without ever locking the account
  or being noticed.
- Decided: the count is per person across devices, in two scopes (section 12.5). Wrong PINs
  from trusted devices lock every device (the stolen phone case: five tries, then nothing
  works until a reset). Wrong PINs from untrusted devices lock every untrusted device, and
  only a code clears that count: the owner's trusted phone keeps working, and a stranger gets
  at most five guesses per code event of the owner, never four per day. A thief who holds a
  trusted device and also tries from untrusted ones gets at most ten guesses before both
  scopes lock (one in a thousand against four digits), against the notes' five: accepted.
- Mitigations kept: the `auth_pin` throttle per address and per device slows a sweep over
  many numbers; the lock is in the change log ("PIN locked after 5 wrong tries") so the
  office sees it; the people status shows Locked.
- Residual risk: a stranger can still lock a person out of new devices (five taps), so that
  person needs a code to sign in on a new phone; a person whose trusted phone is the one
  stolen is locked everywhere after five tries by the thief. Owner may overrule the split
  (question 47).

**c. Mail flood through the code routes.** Every issue path counts toward the per-person
caps (one a minute, five an hour, ten a day), including the automatic replacement; the
resend route issues a `new_device` code only after a right PIN on that device within ten
minutes, so it cannot be used to mail someone without their PIN. Across people, the `auth`
limit per address bounds the rate; rotating addresses is the residual risk.

**d. A stolen device token.** The token alone gives nothing: a trusted device still needs
the PIN, and five wrong PINs from it lock every device. Stored only as a SHA-256 digest, so
the database does not yield usable tokens. The person removes it from their devices list,
an administrator with `people.sign_in` does, a reset or a block removes all, and it expires
after 90 days unused.

**e. A v2.11 device id copied from another phone.** Rows trusted the old way are trusted by
`deviceId` alone, as today: someone who learns a phone's id (it travels in the access
token's `device` claim) can present it on A01 and get a PIN-only sign-in on that person's
legacy row. Unchanged from today's risk; it ends as phones move to the token (`DEC-5`).

### 12.15 Tests

`docs/09-testing.md` section 4.1 lists the test for each rule above.

### 12.16 Decisions of the build (D1, 2026-10-12)

- `api.auth_account_lookup` takes `p_pin_try`: A01, A02 and N02 record an unknown number as
  one PIN try (the row `identity.unknown_pin_tries` counts); a reset completion (A09, N06)
  looks the account up without recording one, so a stranger's resets do not move an unknown
  number's simulated lock.
- The simulated code of an unknown number exists only for `pin_reset` (a real account with a
  PIN can only hold the reset code a stranger asked for): a `forgot_pin` history row (A07, N05
  record that operation; A04 records `request_code`) or a `code_resent` row less than ten
  minutes old starts it, and wrong `code` rows after it count. Another purpose answers as
  "no code" (`triesLeft` null), as a real account does.
- `identity.unknown_pin_tries` reads at most six rows: the PIN step's own try is already
  recorded by its lookup, so "locked before this try" is six.
- The simulated reset code belongs to the device that asked for it, as a real code does
  (`identity.unknown_code_tries` takes the device id): a code step from another device
  answers "no code" for both.
- `identity.code_check` carries `tries_left`; `identity.unknown_code_tries`,
  `identity.remove_devices` and `tenancy.sign_in_snapshot` take `p_now` (liveness and expiry
  need it); `identity.count_wrong_pin` has no device-name parameter, and `api.auth_pin` none
  (neither used it).
- A reset completion whose checked hash no longer matches refuses with `verdict_void` and
  changes nothing (the "PIN being replaced" verdict cannot be trusted); the client retries
  with the same code.
- A wrong code on a completion (A06, A09, N06) counts and voids on the third try without a
  replacement; A05, A08 and N03 replace.
- A03 refuses a pending forced reset (`reset_required`) and checks no lock: a verified new
  device clears both scopes (12.5).
- `needs_dummy_hash` covers an unknown or removed account, no PIN and a pending forced reset;
  an account without membership verifies its stored hash (A01 keeps counting its wrong PINs;
  N02 answers `blocked` before the verdict). A reset completion compares the new PIN with
  the stored hash even while a forced reset is pending.
- On the released routes an outcome of the number-first routes (never produced there) maps to
  the uniform refusal.
- Device removals (A12, N09) do not bump the user row's `version` (the row is unchanged).
- N09 removes any live row of the caller (remembered or not), else 404.
- The PIN throttle charges the address before the device and stops at the first refusal; on
  N07 the address half is a dependency before authentication and the device half uses the
  token's `device` claim.
- Lock order (`docs/05-routines.md` 10.1): the people routines lock the membership
  `FOR NO KEY UPDATE` before the user row; the sign-in change-log rows take `KEY SHARE` on the
  actor's membership while holding the user row
  (`tests/db/test_auth_routines.py::test_a_person_write_and_a_sign_in_event_do_not_deadlock`
  fails with `DeadlockDetected` under `FOR UPDATE`).
