# Prompt 04: authentication service and HTTP contract

Paste everything below the line into a fresh Claude Code session running Sonnet, started in
the repository root. Requires prompts 00 to 02; the HTTP tests need prompt 03's routines
(run them once prompt 03 is complete). May run beside prompt 03 with the file split named
in that prompt.

---

You are writing the Python side of authentication in `apps/api-python`: the value objects
and pure policies, the cryptographic adapters, the auth use cases, the thirteen `/auth`
routes with the seven-property envelope, the bearer principal every other router will use,
the mail templates and delivery timing, the fakes and their parity tests, and the HTTP
contract tests including the byte-for-byte refusal rule.

## Read first, in this order

1. `CLAUDE.md`; `apps/api-python/README.md`.
2. `docs/00-principles.md`; `docs/01-architecture.md` (all); `docs/02-stack.md`;
   `docs/11-naming.md`; `docs/12-security.md` sections 2.1, 2.2, 2.4, 2.5, 2.6, 3.
3. `docs/07-auth.md` (all); `docs/06-http-contract.md` sections 1 (all), 2.1, 3
   (cross-cutting), 4; `docs/05-routines.md` sections 1.3, 1.4, 3.
4. `docs/08-operability.md` sections 2 (settings you use: signing keys, issuer, audience,
   trust lifetime, rate limit, mail, development codes, email timeout), 5, 6.
5. `docs/09-testing.md` (all).
6. `docs/inventory/inventory-auth.md` sections 1, 6, 7 (the `Seen` rule, mail text, dev
   codes) and `docs/inventory/inventory-http-contract.md` sections 1.3, 1.5, 1.8 (A), 2.2,
   3.1.
7. The code from prompts 00 to 03: `settings.py`, `container.py`, `main.py`, `http/*`,
   `infra/mail.py`, `infra/rate_limit.py`, `application/ports.py`,
   `application/repositories.py`, `domain/*`, `db/routines/identity.py`,
   `tests/support/*`.

Do not read the C# sources.

## Environment

As prompt 01. `git status` first; write only under `apps/api-python/`.

## Deliverables

### D1 Domain values and policies

- `domain/values.py`: `PhoneNumber.parse` (the exact normalisation of `docs/07-auth.md`
  section 1; returns `None` for "not a number"), `Pin` (shape check of the floor rules;
  never stores the digits in a `repr`), `DeviceId` (1..128 code points), `Email` (lower
  case, `local@domain` only, 320 max), `RefreshToken` (opaque text, 256 max),
  `VerificationCode` (32 max).
- `domain/policies.py`: `PIN_FLOOR = 4`, `UNTRUSTED_DEVICE_LIMIT = 10`,
  `pin_shape_valid`, `refusal_answer()` (the one uniform refusal), `needs_dummy_hash`,
  `envelope_for(outcome)` mapping every `AuthOutcome` of `docs/05-routines.md` section 3.1
  to the status and envelope fields of `docs/06-http-contract.md` section 1.6 (A).
- `domain/identity.py`: `AuthOutcome`, `AccountState`, `Principal` (`user_id`,
  `device_id`, `security_version`, `organization_id`, `role`, `permissions`), the outcome
  enumeration.
- Evidence: `tests/unit/test_domain_values.py` (phone table including non-ASCII digits and
  a leading `+`), `tests/unit/test_policies.py` (every outcome maps; the refusal answer is
  one object; PIN shape table: too short, non-digit, all same, ascending and descending
  runs, valid).

### D2 Cryptographic adapters (`security/`)

- `pins.py` `Pbkdf2PinHasher`: 210 000 iterations, 16-byte salt, 32-byte key, the stored
  format, constant-time verify, the dummy hash computed once per process, `hash` and
  `verify` offloaded with `asyncio.to_thread`; the iteration count is a constructor
  argument so tests use a small one except the vector test.
- `digests.py` `keyed_digest(value, key) -> str` (HMAC-SHA256, upper-case hex).
- `codes.py` (six digits from `secrets.randbelow`, zero padded), `refresh_tokens.py`
  (48 bytes, standard Base64 with padding).
- `tokens.py` `JwtTokenIssuer`: issue with exactly the claims and header of
  `docs/07-auth.md` section 1 (`permission` a string for one key and an array for several;
  no `iat`, no `jti`; integer seconds); verify with the current key, then each previous key,
  zero leeway, issuer and audience required, `alg` pinned to HS256 (`none` and any other
  algorithm refused).
- Evidence: `tests/unit/test_pin_hasher.py` (format, verify, wrong PIN, malformed stored
  value raises `IntegrityBug`, the dummy hash differs per process, the full count runs
  once), `tests/unit/test_tokens.py` (claims byte for byte against a token you construct
  by hand with `PyJWT` in the test; previous-key verification; every tampering refused),
  `tests/unit/test_digests.py` (a fixed HMAC vector).

### D3 Use cases (`application/auth/`)

- `sign_in.py` (A01 and A02 share it), `verify_device.py`, `request_code.py`,
  `verify_code.py`, `complete_pin.py`, `refresh.py`, `sign_out.py`, `revoke_device.py`,
  `resolve_session.py`, `get_session.py`; each a `<Verb><Noun>Command` and a class with
  `execute`, taking only ports (`IdentityRepository`, `Clock`, `PinHasher`, `CodeHasher`
  or the digest function, `TokenIssuer`, `Mailer`/`MailQueue`).
- `SignIn`: lookup, always one PBKDF2 verification (dummy when needed), decision routine,
  then the token pair or the mail; `new_device` mail awaited with the timeout and
  withdrawn plus `service_unavailable` on failure; `first_setup`/`pin_reset` mail enqueued
  after the routine returned.
- Evidence: `tests/unit/test_use_case_sign_in.py` and one per use case: the order of port
  calls with `FakeIdentityRepository` and `MailSpy` (the mail is enqueued only after the
  repository call returned; the PBKDF2 verify runs exactly once for unknown and known
  accounts; the withdraw call happens on a mail failure).

### D4 Fakes and parity

- `tests/support/fakes.py` `FakeIdentityRepository`: an in-memory implementation of every
  method with the same outcomes as the routines (lockout counters, pause, cap, codes with
  caps, devices, tokens, rotation and replay) built from the same case list.
- `tests/db/test_fakes_match_routines.py`: a shared table of scenarios (in
  `tests/support/auth_cases.py`) run against the fake and against `IdentityRoutines` on
  PostgreSQL, asserting identical outcomes. Add every branch of `docs/07-auth.md`
  section 3 to the table.

### D5 HTTP (`http/`)

- `http/schemas/auth.py`: one request model per route (same wire fields, `extra="ignore"`,
  defaults `""`), `AuthResponse` with the seven properties in order and nulls written,
  `AuthSessionResponse`.
- `http/routers/auth.py`: the thirteen routes of `docs/06-http-contract.md` section 2.1
  with the exact paths, the pre-validation of section 2.1 answering `400 invalid_request`
  before any lookup, the `auth_rate_limit` dependency on every route, bearer on A12 and A13
  (`current_principal`), the 403 empty body when the path id differs from the `device`
  claim, status codes per envelope status (200, 202, 400, 401, 423, 503), no tags, no
  `security` on anonymous routes and `Bearer` on A12/A13 in OpenAPI.
- `http/dependencies.py` `current_principal`: `Authorization: Bearer` only; any failure is
  401 with an empty body and `WWW-Authenticate: Bearer`; verifies the token through
  `TokenIssuer`, runs `ResolveSession`, binds `actor_id` and `organization_id` into the log
  context. Every later router uses it unchanged.
- Development codes: `developmentCode` only when `settings.development_codes` is true and
  a code was issued; the settings refuse the flag outside development (prompt 00 did this;
  verify).
- Evidence: `tests/api/test_auth_contract.py` (D7).

### D6 Mail

- `infra/mail.py`: the two templates (`Your verification code`; `Your {Purpose} code is
  {code}. It expires in 10 minutes.` with the label map `FirstSetup`, `NewDevice`,
  `PinReset`), `SmtpMailer` timeout from `XCODE_EMAIL_TIMEOUT_SECONDS` (default 10; add
  the setting to `settings.py`, `.env.example`, `docs/08-operability.md` section 2 and
  the settings matrix), `LogMailer` logging the code only in development and testing,
  `MailQueue` unchanged.
- Evidence: `tests/unit/test_mail_templates.py` (exact subject and bodies for the three
  purposes); `tests/api/test_auth_contract.py` covers timing and the 503 path with a
  `MailSpy` that can fail on demand.

### D7 HTTP contract tests (`tests/api/test_auth_contract.py`)

- Every route: happy path, each refusal, each pre-validation case (one per field), the
  envelope's seven properties in order with nulls written, content type
  `application/json; charset=utf-8`, `X-Request-ID` on every answer including 401 and 429.
- The byte-for-byte rule: for each pair of `docs/07-auth.md` section 7 (unknown number,
  non-normalising number, removed account, paused on an untrusted device, capped, wrong
  PIN untrusted) compare status, body bytes and headers minus `Date`, `Content-Length`,
  `X-Request-ID`; A04 and A07 answer identically whether or not mail was sent.
- Lockout and pause with `ManualClock` (threshold reached, timer value, lapse, cap at ten,
  reset by A03 and A06/A09); refresh rotation and replay; sign-out; device revoke; the
  session check kills tokens immediately after a security-version bump, a device revoke
  and a removal; development codes present in development and absent in testing; rate
  limit 429 with an empty body and `Retry-After` after the configured permits, partitioned
  by client address through a trusted proxy; the statement budget of
  `docs/06-http-contract.md` section 2.1 per route.
- OpenAPI: `POST /auth/sign-in` documents 202 and 423 with `AuthResponse` and no
  `security`; `components.securitySchemes.Bearer` is `http`/`bearer`/`JWT` (the full
  assertion set of `docs/06-http-contract.md` section 1.11 is completed in prompt 09; write
  the auth half now in `tests/api/test_openapi.py`).

## Invariants at the end

- `domain/` and `application/` import only the standard library (`test_layers.py`);
  `http/` imports no adapter.
- A PIN, code or refresh token never appears in a log line, an exception message, a
  `repr` or a settings summary (grep the test logs with a known value).
- Exactly one PBKDF2 derivation per sign-in attempt, known or unknown account.
- The seven envelope properties are always present and ordered; every `/auth` 4xx and 5xx
  below 500 is JSON with a string `status` (the web proxy depends on it).
- Lint, types, all tests green (database tests once prompt 03 is in); no TODO/FIXME; no
  plan or prompt identifiers.

## Verify (paste the outputs into the report)

```
cd apps/api-python
ruff check . && ruff format --check . && mypy
pytest tests/unit -q
pytest tests/db tests/api -n auto -q                   # with PostgreSQL and prompt 03 applied
xcode-api serve & sleep 3
curl -s -i -X POST localhost:5000/auth/sign-in -H 'content-type: application/json' -d '{"phoneNumber":"0712345678","pin":"1234","deviceId":"d1"}'
kill %1
```

## Report format

1. Checklist: one row per deliverable D1 to D7 and per bullet: done or not, `file:symbol`,
   test name.
2. Verify outputs, trimmed, including the curl answer with its headers.
3. Deviations from `docs/07-auth.md` and `docs/06-http-contract.md` with reasons; document
   lines changed.
4. Items left for later prompts.

## House rules

- Shared tree: `git status` first; edit only under `apps/api-python/`; never revert or
  reformat others' changes; never kill processes you did not start; never bare `git stash`.
- No commits unless the user asks. No AI attribution anywhere.
- No comments unless needed; no plan or prompt identifiers anywhere; names per
  `docs/11-naming.md` (`xcode`, never `Auth`).
- Never weaken a test to make it pass. If a document is wrong, fix the document and report
  it.
