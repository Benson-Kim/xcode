# Auth inventory: the .NET API's authentication, as input for `docs/07-auth.md`

Source of truth: the C# under `apps/api/` (namespace `Auth` appears only in citations). Wire shapes, statuses and the `AuthResponse`
envelope are NOT repeated here: they live in `inventory-http-contract.md` sections 1.5, 1.8, 2.2 (endpoints `A01`-`A13`) and 3.1;
this file cites them by id. Paths are relative to `apps/api/` unless they start with `tests/`.

**(uncommitted)** marks facts that exist only in files that git shows as modified or untracked at the time of writing
(`git status --short apps/api tests/api`). The auth rewrite out of `AuthService.cs` is entirely uncommitted:
`Application/Authentication/*`, `Infrastructure/AuthUnitOfWork.cs`, `Infrastructure/AuthGate.cs` are untracked; `Application/AuthContracts.cs`
(the `Mail` member), `Api/AuthEndpoints.cs`, `Program.cs` (the `AddAuthServices` line, response compression) and `Application/AccessUseCases.cs`
are modified; `Application/AuthService.cs` is deleted in the working tree. Committed and unchanged: `Domain/Entities.cs`, `Domain/PhoneNumber.cs`,
`Infrastructure/Security.cs`, `Infrastructure/UserProvisioning.cs`, `appsettings.json`. `inventory-http-contract.md` still cites the deleted
`AuthService.cs` lines; behaviour was re-checked against the new files and agrees except where section 11 says otherwise.

Class map (all **(uncommitted)** unless noted): `SignInService` (A01, A02, A03), `PinSetupService` (A04-A09), `SessionService` (A10, A11, A12),
`AuthAccounts` / `AuthDevices` / `AuthPolicy` (three small services in one file, `Application/Authentication/AuthAccounts.cs:7,26,55`),
`AuthCodes` (issue and check codes), `SessionTokens` (issue and revoke refresh tokens), `AuthUnitOfWork` (lock + transaction + mail after commit),
`AuthGate` (lock map), `TokenIssuer` / `PinHasher` / `VerificationMailer` / email senders (`Infrastructure/Security.cs`, committed).

## 1. Parameters

### 1.1 Credentials and hashing

| Parameter | Value | Source |
|---|---|---|
| PIN hash algorithm | PBKDF2-HMAC-SHA256 (`Rfc2898DeriveBytes.Pbkdf2`), password = the PIN string encoded as UTF-8 | `Infrastructure/Security.cs:57,63,69` |
| PIN iterations | 210 000 | `Security.cs:57` |
| PIN salt | 16 random bytes (`RandomNumberGenerator`), new per hash | `Security.cs:62` |
| PIN derived key | 32 bytes | `Security.cs:63` |
| PIN stored format | `base64(salt)` + `"."` + `base64(hash)`, standard Base64 with padding, in `users.PinHash` (max length 256, nullable; null = no PIN) | `Security.cs:64`, `Infrastructure/AuthDb.cs:47` |
| PIN compare | constant time (`FixedTimeEquals`) on the 32-byte values; a stored hash that does not split into two valid Base64 parts throws (500) | `Security.cs:66-71` |
| Dummy hash | `Hash("5826")` computed once at startup (so a different salt each boot), verified against for an unknown or unusable user so PBKDF2 always runs once on sign-in | `Security.cs:59`, `SignInService.cs:15` |
| PIN length cap before hashing | 8 characters: `AuthRequest.Pin` longer than `PinRules.MaximumLength` (8) is `400 invalid_request` in `Run` before any lookup. Sign-in does NOT apply `PinRules.IsValid`: any string of 0-8 characters is hashed (an empty PIN is hashed too and simply never matches) | `Api/AuthEndpoints.cs:78-79`, `Application/AuthContracts.cs:41-42`, `SignInService.cs:15` |
| PIN content rules (new PINs only) | `PinRules.IsValid`: length 4-8, ASCII `0`-`9` only, not all one digit, not a full +1 or full -1 step sequence. Refusal = `400 invalid_pin`, `minimumPinLength` 4 (constant `PinRules.MinimumLength`, not the policy value) | `AuthContracts.cs:39-51`, `PinSetupService.cs:27` |
| Policy PIN length for new PINs | the organization's clamped `PinLength` (4-8, default 4); see section 8 and flow A06 step 3 | `PinSetupService.cs:32-36` |
| Keyed hash for codes and refresh tokens | HMAC-SHA256 over the UTF-8 value, key = UTF-8 bytes of `Auth:SigningKey`, output upper-case hex (64 characters). Same function (`TokenIssuer.Hash`) for both | `Security.cs:76` |
| Refresh token | 48 random bytes, standard Base64 (64 characters, can contain `+`, `/`, `=`), stored only as the keyed hash; column `TokenHash` max 64, unique index | `SessionTokens.cs:40,46`, `AuthDb.cs:58-59` |
| Verification code | `RandomNumberGenerator.GetInt32(0, 1_000_000)` formatted `D6` (zero padded, 6 digits); stored as the keyed hash (`CodeHash` max 64) | `AuthCodes.cs:28,35`, `AuthDb.cs:54` |
| Code compare | `FixedTimeEquals` on the two hex hashes decoded to bytes | `AuthCodes.cs:49` |
| Changing the signing key | invalidates every outstanding code, refresh token and access token at once (all three are keyed by it); there is no key id, no second key, no rotation window | `Security.cs:76,88`, `Program.cs:110` |

### 1.2 Verification-code policy

| Parameter | Value | Source |
|---|---|---|
| Digits | 6 | `AuthCodes.cs:28` |
| Lifetime | 10 minutes from `CreatedAt`; usable while `now <= ExpiresAt` (inclusive), `FailedAttempts < 5`, not consumed | `AuthCodes.cs:37`, `Domain/Entities.cs:64` |
| Wrong tries per code | 5; the 5th wrong try sets `Consumed` (a later correct code is refused) | `Entities.cs:66-70` |
| Resend cooldown | 1 minute: refused when ANY non-withdrawn code of the same user AND same purpose (any device) was created less than 1 minute ago (`CreatedAt + 1 min > now`). Skipped in DevelopmentMode | `AuthCodes.cs:19-20` |
| Hourly cap | `AuthCodes.HourlyCodeLimit` = 5: non-withdrawn codes of the user (all purposes, all devices, consumed ones included) with `CreatedAt > now - 1 h` | `AuthCodes.cs:13,22-24` |
| Daily cap | `AuthCodes.DailyCodeLimit` = 10, same counting, window 24 h | `AuthCodes.cs:14,25` |
| Caps in DevelopmentMode | still enforced (only the cooldown is skipped) | `AuthCodes.cs:20-25` |
| Supersession | issuing a code consumes every code of the same user and same purpose, for all devices, usable or not | `AuthCodes.cs:27` |
| Refused issue | returns null: the endpoint still answers its normal success (202); nothing is stored or sent | `AuthCodes.cs:20,24,25`, `SignInService.cs:47-52` |
| Withdrawn | a code that could not be mailed: `Consumed = true` and `ExpiresAt = CreatedAt`; `IsWithdrawn = Consumed && ExpiresAt <= CreatedAt`. Withdrawn codes do not start the cooldown and do not count toward the caps | `Entities.cs:74-80` |

### 1.3 Lockout

| Parameter | Value | Source |
|---|---|---|
| Trusted-device threshold | organization `LockoutThreshold`, clamped 3-10, default 5 | `Security.cs:28`, `Domain/Organization.cs:287` |
| Pause length | organization `LockoutMinutes`, clamped 1-60, default 15 (900 s) | `Security.cs:29`, `Organization.cs:288` |
| Untrusted-device cap | `SignInService.UntrustedAttemptLimit` = 10, a per-account constant (not policy-driven) | `SignInService.cs:9` |
| Counters | `users.FailedAttempts` (trusted devices), `users.UntrustedFailedAttempts` (untrusted devices), `users.PausedUntil` | `Entities.cs:13-16` |
| Retry-after | `ceil(seconds from now to PausedUntil)` as int | `AuthAccounts.cs:36` |

### 1.4 Tokens, sessions and request limits

| Parameter | Value | Source |
|---|---|---|
| JWT algorithm | HS256 (`SecurityAlgorithms.HmacSha256`), key = UTF-8 bytes of `Auth:SigningKey` | `Security.cs:88`, `Program.cs:110` |
| Issuer / audience | `Auth:Issuer` default `xcode-api`; `Auth:Audience` default `xcode-clients` (both validated) | `AuthContracts.cs:14-15`, `Program.cs:108-109` |
| Claims | `sub`, `device`, `version` (SecurityVersion), `org`, `role`, `first_name`, `last_name`, one `permission` per effective key; `nbf` = issue time, `exp`; no `iat`, no `jti`. Full detail: HTTP inventory 1.5 | `Security.cs:79-88` |
| Access lifetime | organization `AccessTokenMinutes`, clamped 1-15, default 10 | `Security.cs:30`, `SessionTokens.cs:60` |
| Refresh lifetime | organization `RefreshTokenDays`, clamped 1-90, default 30; `ExpiresAt = now + days` | `Security.cs:31`, `SessionTokens.cs:47` |
| Clock skew | zero (`ClockSkew = TimeSpan.Zero`); lifetime, issuer, audience and signing key all validated; `MapInboundClaims = false` | `Program.cs:104-112` |
| Trusted-device lifetime | `Auth:TrustLifetimeDays` (int?, null = never expires); `<= 0` aborts startup; applied on every `Trust` (a re-verify replaces the expiry) | `AuthContracts.cs:16`, `Program.cs:26`, `AuthAccounts.cs:51` |
| Signing key config | `Auth:SigningKey` (env `Auth__SigningKey`), at least 32 UTF-8 bytes else startup throws. Empty is allowed ONLY in Development or Testing, where a random 48-byte Base64 key is generated per process start (every restart then invalidates everything) | `Program.cs:22-25` |
| Key rotation | none | `Program.cs:110` |
| Per-request session check | after JWT validation: user exists and `Active`, `SecurityVersion.ToString() == version claim`, `TrustedDevice` (sub, device) exists with `Revoked = false` and `TrustExpiresAt` null or in the future; any failure = 401, empty body. Two reads per request, no cache | `Program.cs:115-127` |
| Pause is not checked per request | a paused account's already-issued access tokens keep working; pause only blocks sign-in, unlock and refresh | `Program.cs:124-125`, `SessionService.cs:32` |
| Request pre-validation limits | deviceId 1-128, phone <= 14, email <= 320 (+ valid address if non-empty), pin <= 8, code <= 32, refreshToken <= 256. Lengths are .NET UTF-16 code units, not code points | `AuthEndpoints.cs:78-79` |
| Rate limit | policy `auth`: fixed window 1 minute, `RateLimiting:AuthPermitLimit` (default 30; 10000 in Testing; `<= 0` aborts startup), partition = remote IP after forwarded-headers (only `ForwardedHeaders:KnownProxies`, default loopback, may set `X-Forwarded-For`), queue 0, rejection 429 empty body | `Program.cs:81-98` |
| Phone normalization | strip non-digits (`\D`, Unicode-aware: non-ASCII decimal digits are kept and then fail the ASCII-only checks); accept 12 digits `254` + `[17]\d{8}` -> `+254...`; 10 digits `0` + `[17]\d{8}` -> `+254` + rest; 9 digits `[17]\d{8}` -> `+254` + digits; else empty string (= not a number). Blank/whitespace input = empty. Stored `users.PhoneNumber` max 13 | `Domain/PhoneNumber.cs:25-49`, `AuthDb.cs:43` |
| Account lookup | by normalized phone only (`email` is never a lookup key); an empty normalization finds nobody without touching the database | `AuthAccounts.cs:9-11` |

## 2. Flows A01 to A13

Statuses and envelope codes below use the HTTP inventory vocabulary (1.8 (A), 3.1). Request fields per endpoint: HTTP inventory 3.1.

### 2.0 Frame shared by A01-A12 (`Api/AuthEndpoints.cs:76-83`, `Infrastructure/AuthUnitOfWork.cs:11-33`) (uncommitted)

1. Pre-validation (`AuthEndpoints.Run`): any violation = `400 invalid_request`, before the lock, before any lookup, no database access. Limits in 1.4.
2. Lock key (`AuthEndpoints.LockKey`, `AuthEndpoints.cs:73-74`): the normalized phone (`+254...`) when the request's phone normalizes, else the text `device:<deviceId>`. Refresh and sign-out send a blank phone, so their key is always `device:<deviceId>`. A12 uses the account's own phone (see A12). The lock is an in-process semaphore per key (`AuthGate`, 10 000 keys max, see 2.11); it is acquired with the request's cancellation token.
3. Inside the lock: execution strategy (SQL Server `EnableRetryOnFailure(3, 5 s)`, `Program.cs:75`) -> SERIALIZABLE transaction -> the flow's action -> `SaveChangesAsync` -> commit. On a retry the change tracker is cleared first and the action runs again from scratch.
4. `SaveChangesAsync` runs `ValidateWrites` then `BumpVersions` (`Infrastructure/OrganizationModel.cs:87-127`): every `User` or `RefreshToken` row in state Modified gets `Version = original + 1`. `User` and `RefreshToken` carry `IsConcurrencyToken` on `Version` (`AuthDb.cs:48,60`); `TrustedDevice` and `VerificationCode` have no version.
5. A flow that RETURNS a failure (401, 423, ...) still commits whatever it changed (failed-attempt counters, revocations, consumed codes). Only an exception rolls back. There is no catch around it: an exception (concurrency conflict, database error) is a 500 (HTTP inventory 1.8 (C)).
6. The lock is released after commit, then mail is delivered (`Deliver`, 2.11 and section 7). Only the last (committed) attempt's `AuthResult.Mail` is used.
7. The answer is serialized as the seven-property `AuthResponse` (`Results.Json`).

Rows touched by `SessionTokens.Issue` (every flow that ends in tokens: A01/A02 trusted, A03, A06, A09, A10): reads the user's single ACTIVE membership (ignoring tenant filters; more than one active membership throws -> 500), the organization's clamped security policy, the user's `PersonRole` and `Role`, the `PermissionOverrides`; resolves effective permissions (`PermissionCatalog.DefaultsFor(role.Name)` + overrides + membership active); inserts one `RefreshToken`. No membership or no role = `401 authentication_failed` and NO token row (`SessionTokens.cs:13-31`). Callers have usually already changed state by then and that state is committed (see the flags per flow).

### 2.1 A01 `POST /auth/sign-in` and A02 `POST /auth/unlock` (identical handler `SignInService.SignIn`, `SignInService.cs:11-56`)

Lock key: normalized phone, else `device:<deviceId>`. Checks in order:

1. Find user by normalized phone (none -> user is null).
2. PBKDF2 verify the PIN against the user's hash, or against the dummy hash when the user is null or has no PIN (`user?.PinHash ?? DummyHash`). Always exactly one derivation. Result kept as `correct`.
3. User null, `Status` Removed, or no PIN -> `401 authentication_failed`. Writes: none.
4. If `PausedUntil` is set and `now >= PausedUntil`: `ClearLockout` (FailedAttempts = 0, PausedUntil = null).
5. If still paused (`now < PausedUntil`): device trusted -> `423 paused` (+`retryAfterSeconds`); not trusted -> `401 authentication_failed`. The PIN is irrelevant here and NO counter changes (a paused account cannot be pushed further).
6. `isTrusted` = a `TrustedDevice` row for (user, deviceId) that is not revoked and not expired.
7. Not trusted and `UntrustedFailedAttempts >= 10` -> `401 authentication_failed` without regard to the PIN; no counter changes.
8. PIN wrong and device trusted: read the policy (user's active membership's organization, clamped; defaults when none); `FailedAttempts++`; if `FailedAttempts < LockoutThreshold` -> `401`; else `PausedUntil = now + LockoutMinutes` and `423 paused` with `retryAfterSeconds = ceil(LockoutMinutes * 60)` (the fifth wrong PIN already shows the timer; `FailedAttempts` stays at the threshold, it is not reset until the pause lapses or a clear).
9. PIN wrong and device not trusted: `UntrustedFailedAttempts++` -> `401`.
10. PIN right and device not trusted: issue a `NewDevice` code (cooldown, caps, 1.2) -> `202 verification_required`, `maskedEmail` = `MaskEmail(user.Email)`, `developmentCode` only when a code was issued AND DevelopmentMode. When issuance is refused: still 202, `developmentCode` null, no mail. The code's mail is sent BEFORE the answer; mail failure -> `503 service_unavailable` (the code is withdrawn). No lockout counter changes in this branch (neither is cleared).
11. PIN right and device trusted: `ClearLockout` (FailedAttempts = 0, PausedUntil = null; `UntrustedFailedAttempts` untouched) -> `SessionTokens.Issue` -> `200 authenticated`, or `401` when there is no membership or role (the ClearLockout is still committed).

Reads: `users`, `trusted_devices`, `memberships`+`security_policies` (step 8 only), `verification_codes` (step 10), plus the Issue reads. Writes: `users` counters (Version +1 when anything changed), `verification_codes` (insert + consume previous of same user and purpose), `refresh_tokens` insert. Version bumps: `User.Version` only; `SecurityVersion` never changes in this flow. Mail: `NewDevice` code, before the reply.

### 2.2 A03 `POST /auth/verify-device` (`SignInService.VerifyDevice`, `SignInService.cs:58-72`)

Lock key: normalized phone, else `device:<deviceId>`.

1. Find user. Null, Removed, no PIN, or paused (`IsPaused(now)`, a lapsed pause counts as not paused) -> `401`. No PIN is verified in this flow and no PBKDF2 runs.
2. `Consume(NewDevice)`: pick the user's newest (by `CreatedAt`) UNCONSUMED code with this `deviceId` and purpose `NewDevice`. None, expired, or already 5 failures -> `401` (nothing recorded). Hash of the supplied code != stored hash -> that code's `FailedAttempts++` (5th consumes it) -> `401` (the increment is committed). Match -> code consumed.
3. `ClearLockout`; `UntrustedFailedAttempts = 0` (the only place besides `SetPin` that resets the cap).
4. `Trust(deviceId)`: insert a `TrustedDevice` row or update the existing one (`Revoked = false`, `TrustExpiresAt = now + TrustLifetimeDays` or null).
5. `Issue` -> `200 authenticated`; or `401` if no membership or role (the code consumption, lockout clear and device trust are still committed: flagged in section 11).

Writes: `verification_codes`, `users`, `trusted_devices`, `refresh_tokens`. Version bumps: `User.Version`. Mail: none.

### 2.3 A04 `POST /auth/setup-pin/request` and A07 `POST /auth/pin-reset/request` (`PinSetupService.Request`, `PinSetupService.cs:10-15`)

Purpose: A04 = `FirstSetup`, A07 = `PinReset`. Lock key: normalized phone, else `device:<deviceId>`.

1. Find user; `ReadyFor(user, purpose)`: active AND (FirstSetup: has no PIN; PinReset: has a PIN). Not ready -> nothing is issued.
2. Ready: `AuthCodes.Issue` (cooldown per user+purpose, hourly and daily caps; may return null).
3. Always `202 check_email`; `developmentCode` = the issued code only in DevelopmentMode, else null.
4. No pause check and no device-trust check: a paused account can request a reset (the reset's completion clears the pause).

Writes: `verification_codes` (insert + consume previous of the same user and purpose, all devices) only when issued. Version bumps: none. Mail: purpose code, queued in `AuthResult.Mail`, sent AFTER the reply (`SendLater`); send failure does not change the 202.

### 2.4 A05 `POST /auth/setup-pin/verify` and A08 `POST /auth/pin-reset/verify` (`PinSetupService.VerifyCode`, `PinSetupService.cs:17-23`)

Lock key: normalized phone, else `device:<deviceId>`.

1. Find user; not `ReadyFor(purpose)` -> `401 authentication_failed`.
2. `Matching`: newest unconsumed code for (user, deviceId, purpose). None / expired / already 5 failures -> `401`. Hash mismatch -> that code's `FailedAttempts++` (5th consumes) -> `401` (committed).
3. Match -> `200 code_verified`. The code is NOT consumed.

Writes: `verification_codes.FailedAttempts` / `Consumed` on a wrong code only. No version bumps. Mail: none.

### 2.5 A06 `POST /auth/setup-pin/complete` and A09 `POST /auth/pin-reset/complete` (`PinSetupService.CompletePin`, `PinSetupService.cs:25-48`)

Lock key: normalized phone, else `device:<deviceId>`. Checks in order:

1. `PinRules.IsValid(pin)` false -> `400 invalid_pin`, `minimumPinLength` 4. Runs before any account lookup. (A pin over 8 characters never gets here: pre-validation already answered `400 invalid_request`.)
2. Find user; not `ReadyFor(purpose)` -> `401 authentication_failed`.
3. Policy PIN length (user's active membership's organization, clamped; 4 when none): `pin.Length < PinLength` -> if `Matching` finds no usable matching code (wrong code counts a failed try) `401`; if the code matches `400 invalid_pin` with `minimumPinLength` = the policy length (disclosed only with a valid code). The code is not consumed.
4. `Consume` the code (same selection as A05) -> otherwise `401` (wrong code counts a failed try, committed).
5. Effects, in this order: `User.SetPin(hash)` (new PBKDF2 hash, `UntrustedFailedAttempts = 0`, `SecurityVersion++`); `ClearLockout` (`FailedAttempts = 0`, `PausedUntil = null`); revoke ALL the user's not-yet-revoked refresh tokens (every device); consume ALL the user's unconsumed codes (every purpose and device); `Trust(deviceId)`; `Issue`.
6. `200 authenticated`; or `401` when there is no membership or role, in which case the PIN change, token revocation and device trust above are still committed.

Reads and writes: `users`, `verification_codes`, `refresh_tokens` (revoke + insert), `trusted_devices`. Version bumps: `User.Version`, `User.SecurityVersion` (+1, kills every outstanding access token), each revoked `RefreshToken.Version`. Mail: none. Only this step hashes a PIN (one PBKDF2 derivation); the earlier refusals are cheaper, so these paths are not time-equalised (section 6).

### 2.6 A10 `POST /auth/refresh` (`SessionService.Refresh`, `SessionService.cs:10-37`)

Lock key: `device:<deviceId>` (the clients send a blank phone; a valid phone in the body would switch the key to the phone). Not serialised against the same user's phone-keyed flows. Checks in order:

1. Keyed hash of `refreshToken`; find the token row by hash (revoked rows included). None, or `DeviceId` differs from the request's -> `401`. Nothing written.
2. Load the user. Not active -> revoke ALL the user's non-revoked refresh tokens (committed), `401`.
3. Token already revoked (replay) -> revoke all the user's non-revoked tokens on THAT device (committed), `401`. The trusted device row is untouched.
4. `now >= token.ExpiresAt`, or user paused, or device not trusted (row missing, revoked or expired) -> `401`. Nothing written; the token is not revoked.
5. `token.Revoke()`, then `Issue` -> `200 authenticated` with a new access token and a new refresh token. If `Issue` fails (no membership or role) the answer is `401` but the old token's revocation is committed.

Role, names, permissions and `SecurityVersion` are re-read, so this is how a client picks up changes. Writes: `refresh_tokens` (revoke old, insert new). Version bumps: the revoked `RefreshToken.Version`. Two concurrent refreshes with the same token are serialised by the key; the second sees the revoked token and triggers step 3 (it also revokes the first request's new token). Clients single-flight their refresh for this reason. Mail: none.

### 2.7 A11 `POST /auth/sign-out` (`SessionService.SignOut`, `SessionService.cs:39-47`)

Lock key: `device:<deviceId>`. Find the token by hash AND `DeviceId` (revoked rows included); if found, revoke all of that user's not-yet-revoked tokens on that device. Always `200 signed_out`. Trusted device untouched; outstanding access tokens untouched (they live until `exp`). Writes: `refresh_tokens` revoke. Version bumps: each revoked `RefreshToken.Version`. Mail: none.

### 2.8 A12 `POST /auth/devices/{id}/revoke` (`AuthEndpoints.cs:50-56`, `SessionService.RevokeDevice`, `SessionService.cs:49-59`)

1. Framework JWT check (including the per-request session check): failure = 401 empty body.
2. `id` not equal (ordinal) to the `device` claim -> `403` empty body. This runs BEFORE pre-validation, so the `400 invalid_request` for a path id over 128 characters is unreachable (a valid token's device claim is at most 128).
3. Lock key = `SessionService.AccountKey(userId)`: the user's normalized phone, read from the database OUTSIDE the lock; the user row missing or a phone that does not normalize falls back to `device:<id>`. This makes a revoke wait for the account's other sign-in work (`tests/api/AuthTests.cs:577`).
4. Action: mark the `TrustedDevice` (user, id) revoked if it exists; revoke all the user's not-yet-revoked refresh tokens on that device; consume every unconsumed code of the user for that device. Always `200 device_revoked`.

Writes: `trusted_devices`, `refresh_tokens`, `verification_codes`. Version bumps: revoked `RefreshToken.Version`; `User.Version` and `SecurityVersion` unchanged. Mail: none. The caller's own access token stops at once (per-request device check).

### 2.9 A13 `GET /auth/session` (`AuthEndpoints.cs:57-64`)

JWT required (and the per-request session check). No database access, no lock. Answers from the token claims; no `AuthResponse`. Shape: HTTP inventory A13.

### 2.10 Lock key summary

| Flow | Lock key |
|---|---|
| A01-A09 | normalized phone, else `device:<deviceId>` |
| A10, A11 | `device:<deviceId>` (their phone is blank) |
| A12 | account's normalized phone (looked up outside the lock), else `device:<id>` |
| A13 | none |

### 2.11 Lock map, transaction and delivery (`Infrastructure/AuthGate.cs`, `Infrastructure/AuthUnitOfWork.cs`) (uncommitted)

| Item | Behaviour |
|---|---|
| Lock | one `SemaphoreSlim(1,1)` per key in a process-wide concurrent map (`AuthGate.For`); waiting honours the request's cancellation token; released in `finally` after the transaction (before mail delivery) |
| Map cap | `MaxEntries` 10 000; when the count exceeds it, idle entries (semaphore free) are removed oldest-first by last-use (monotonic milliseconds) until at most 8 000 remain; entries in use are never evicted |
| Scope | in-process only. Several API instances are protected only by the SERIALIZABLE transaction and the `Version` concurrency tokens on `users` and `refresh_tokens` |
| Isolation | SERIALIZABLE for every flow, including the failing and read-only ones (A05/A08/A11/A12 included) |
| Retry | SQL Server retrying execution strategy: 3 retries, 5 s maximum delay, transient errors only (deadlock, timeouts, serialization). Not retried: concurrency-token conflicts, constraint violations, application exceptions (all surface as 500) |
| Per retry | change tracker cleared, new transaction, the whole flow action re-run; the code, hash and mail of a rolled-back attempt are discarded |
| After commit | `Deliver(result)`: no `Mail` -> the result as is. Mail with purpose other than `NewDevice` -> `SendLater` (fire-and-forget, result unchanged). `NewDevice` -> awaited `Send`; failure -> `503 service_unavailable` replaces the result |
| Test pinning | `tests/api/AuthTests.cs:434` (`ConcurrentFailuresCannotLoseAttempts`), `:577` (revoke waits for the account's lock), `:595` (`ASlowEmailDoesNotHoldUpOtherSignIns`: the lock is released before mail is sent) |

## 3. Pause and lockout state machine

Per account (`users` row). State = (`FailedAttempts`, `PausedUntil`, `UntrustedFailedAttempts`). Two independent counters.

### 3.1 States

| State | Definition |
|---|---|
| Open | `PausedUntil` null (or already in the past) and `UntrustedFailedAttempts < 10` |
| Counting | Open with `FailedAttempts` between 1 and threshold-1 |
| Paused | `now < PausedUntil` (the row also holds `FailedAttempts >= threshold`) |
| Pause lapsed | `PausedUntil` set but `now >= PausedUntil`: treated as Open; the row is cleaned lazily (see 3.3) |
| Capped | `UntrustedFailedAttempts >= 10`; independent of Paused. Matters only for devices that are not trusted |

### 3.2 Transitions

| Event | Device | Effect |
|---|---|---|
| Wrong PIN, not paused | trusted | `FailedAttempts++`; below the policy threshold: `401`; at or above: `PausedUntil = now + LockoutMinutes`, answer `423 paused` with `retryAfterSeconds` = LockoutMinutes x 60 (so the Nth wrong PIN is the first `423`) |
| Wrong PIN, not paused, not capped | not trusted | `UntrustedFailedAttempts++`, `401` |
| Wrong PIN, not paused, capped | not trusted | no change, `401` with no PIN consequence |
| Any PIN (right or wrong) while paused | trusted | `423 paused`, `retryAfterSeconds` = ceil(remaining seconds); no counter changes |
| Any PIN while paused | not trusted | `401` (identical to an unknown number); no counter changes |
| Right PIN, not paused | trusted | `ClearLockout` (`FailedAttempts = 0`, `PausedUntil = null`), tokens issued; `UntrustedFailedAttempts` is NOT reset |
| Right PIN, not paused, not capped | not trusted | `202 verification_required` (code issued); counters unchanged |
| Right PIN, not paused, capped | not trusted | `401` (cap check precedes everything; no code is issued) |
| Pause lapses | any | next A01/A02 attempt sees `now >= PausedUntil` and calls `ClearLockout` before anything else, so counting restarts from 0. A03/A10 treat a lapsed pause as "not paused" without clearing it |

### 3.3 Resets

| Counter | Reset by | Not reset by |
|---|---|---|
| `FailedAttempts`, `PausedUntil` (`User.ClearLockout`, `Entities.cs:29-33`) | lapsed pause (next A01/A02); right PIN on a trusted device (A01/A02); A03 success; A06/A09 success (PIN set or reset, so a reset by email lifts a pause) | `SessionTokens.Issue` (it never touches lockout: `SessionTokens.cs:10`, callers clear it); A10 refresh; sign-out; device revoke |
| `UntrustedFailedAttempts` (`ClearUntrustedFailedAttempts`, `SetPin`) | `User.SetPin` (A06/A09 success; `Entities.cs:22-27`); A03 success (a verified new device, `SignInService.cs:68`) | `ClearLockout` never resets it (`Entities.cs:29-33`); a right PIN from a trusted device; a lapsed pause |
| A code's `FailedAttempts` | nothing resets it; the 5th failure consumes the code | |

Callers of `ClearLockout`: `SignInService.cs:21` (lapsed pause), `:54` (trusted right PIN), `:67` (A03), `PinSetupService.cs:42` (A06/A09). Callers of `Issue` that DO NOT clear lockout: A10 refresh (`SessionService.cs:36`), which instead refuses while paused.

There is no operator command that clears a pause or the untrusted cap. Ways out: wait for the pause to lapse, or complete a PIN reset by email (A07-A09), which clears both. Re-provisioning (section 9) does not clear them.

The mobile client mirrors the trusted-device counter locally with `lockoutThreshold` and `lockoutMinutes` read from `GET /setup/appearance` (`Application/Settings/OrganizationSettingsUseCases.cs:91-92`, **(uncommitted)** directory); the server is authoritative.

## 4. Device trust and verification codes

### 4.1 Purposes (`CodePurpose`, `Domain/Entities.cs:4`)

| Purpose | Issued by | Account state required | Verified/consumed by | Mail timing |
|---|---|---|---|---|
| `NewDevice` | A01/A02 (right PIN, device not trusted) | active, has PIN (implied by the right PIN) | A03 (`Consume`) | before the reply, failure = 503 |
| `FirstSetup` | A04 | active, NO PIN | A05 (`Matching`, kept), A06 (`Consume`) | after the reply |
| `PinReset` | A07 | active, HAS a PIN | A08 (`Matching`, kept), A09 (`Consume`) | after the reply |

Stored on `verification_codes`: `UserId`, `DeviceId` (max 128), `Purpose`, `CodeHash`, `CreatedAt`, `ExpiresAt`, `Consumed`, `FailedAttempts`; index (`UserId`, `Purpose`) (`AuthDb.cs:53-55`). A code is bound to purpose AND device: lookup is `UserId` + `DeviceId` + `Purpose` + not consumed, newest by `CreatedAt` only (`AuthCodes.cs:45-46`); an older unconsumed code for the same key is never tried. A code issued for device X cannot trust device Y (`tests/api/AuthTests.cs:359`).

Mutations that end a code early: successful use (`Consume`), the 5th wrong try, supersession by a newer issue for the same user+purpose (any device), `ConsumeAll(user)` on PIN set/reset, `ConsumeAll(user, device)` on device revoke, withdrawal after a failed send.

### 4.2 How a device becomes trusted

Only two places call `AuthDevices.Trust`: A03 success and A06/A09 success (`SignInService.cs:69`, `PinSetupService.cs:45`). Sign-in never trusts. `Trust` upserts the (`UserId`, `DeviceId`) row (unique index, `AuthDb.cs:50-51`), sets `Revoked = false` and `TrustExpiresAt` = `now + Auth:TrustLifetimeDays` days or null. A device is valid while not revoked and (`TrustExpiresAt` null or `now < TrustExpiresAt`) (`Entities.cs:91`). The `deviceId` string is client-chosen (1-128 characters, any text) and is NOT authenticated beyond the codes and tokens bound to it.

Provisioning creates no trusted device: a provisioned person's first device is trusted by completing A04-A06.

### 4.3 Masking and logging

| Where | Rule |
|---|---|
| `maskedEmail` in A01/A02's 202 | first character of the stored email + `***` + everything from the first `@`; `***` when there is no `@` or it is the first character (`AuthAccounts.cs:19-23`). Computed from `users.Email` as stored |
| Phone numbers | never masked and never returned in an auth response; the server never logs the phone in auth code |
| Codes | never returned except as `developmentCode` (4.4); never logged by the production path. The development mailer logs email and code (section 7). Failure logs carry purpose, user id and correlation id only |
| Stored | codes and refresh tokens only as keyed hashes; PIN as PBKDF2 hash |

### 4.4 `developmentCode`

`AuthOptions.DevelopmentMode` is computed at startup, not bound from configuration: `ASPNETCORE_ENVIRONMENT == Development` AND the `ConnectionStrings:Auth` is "local" (`Program.cs:29-39`: empty, or contains `localhost`, `(localdb)`, `127.0.0.1`, `:memory:`, `mode=memory`, or `.db`, case-insensitive). When true: A01/A02's 202 and A04/A07's 202 carry the just-issued code in `developmentCode`, and the resend cooldown is skipped (`AuthCodes.cs:20,40`). It is null whenever the code was not issued (cooldown, caps, ineligible account) and always null in Testing and Production (`tests/api/AuthTests.cs:704`). A05/A06/A08/A09/A03 never return it.

## 5. Tokens

### 5.1 Issue (`SessionTokens.Issue`, `SessionTokens.cs:11-63`)

Access token: signed JWT (1.4, HTTP inventory 1.5), lifetime from the organization's clamped `AccessTokenMinutes`, carrying the user's `SecurityVersion` as the `version` claim, the `deviceId` as `device`, role name, membership first and last name, effective permissions. Refresh token: 48 random bytes in Base64, only its keyed hash stored with `UserId`, `DeviceId`, `ExpiresAt = now + RefreshTokenDays`, `Revoked = false`, `Version`. The raw value is returned once. The access token is not recorded anywhere; it is validated by signature plus the per-request session check (1.4).

### 5.2 Refresh rotation and reuse detection

A10 (2.6): single use; presenting a token revokes it and issues a pair. Re-presenting a revoked token for the same device revokes every live token the user has on that device and answers 401 (the device itself stays trusted and its access tokens keep working until `exp`). A token presented from another device id is 401 with no side effect. A removed or inactive user: every token revoked. Expiry check is `now >= ExpiresAt`.

### 5.3 Concurrency

| Mechanism | Detail |
|---|---|
| `User.Version` | `long`, `IsConcurrencyToken` (`AuthDb.cs:48`); incremented by `BumpVersions` for every `User` entry in state Modified at `SaveChanges` (`AuthDb.cs:67-74`, called from `OrganizationModel.cs:119,126`). Any counter change, `SetPin`, `Remove` or admin edit therefore changes it; a stale writer gets `DbUpdateConcurrencyException` |
| `RefreshToken.Version` | same, `AuthDb.cs:60`; bumped when a token is revoked |
| `SecurityVersion` | `int` on `User`, NOT a concurrency token; the value in the JWT `version` claim and the per-request check. Bumped by: `SetPin`, `Remove`, `BumpSecurityVersion` (admin person edit with changed name, role or single permissions; admin edit of email or phone; provisioning of a changed or revived existing user) |
| `TrustedDevice`, `VerificationCode` | no version column; last writer wins inside the serializable transaction |
| Conflict outcome | an auth request that hits a concurrency exception (for example against an admin edit made through `/setup`) is not caught: 500. `UnitOfWork` retry semantics for `/setup` writes are out of scope here (HTTP inventory and persistence inventory) |
| Unique constraints that matter | `refresh_tokens.TokenHash` unique; `trusted_devices` (`UserId`, `DeviceId`) unique; `users.Email` unique; `users.PhoneNumber` unique where not empty (`AuthDb.cs:41,45,51,59`) |

### 5.4 Revocation matrix (what stops working, and when)

"Access" = JWTs already issued. They are re-checked against the database on every request (user active, `SecurityVersion`, trusted device), so any change below that alters one of those three is effective on the very next request (immediate), not at `exp`. "Refresh" = refresh tokens. A pause is NOT in the matrix because it changes neither.

| Event | Where | Access tokens | Refresh tokens | Device trust | Notes |
|---|---|---|---|---|---|
| Sign-out (A11) | `SessionService.cs:39-47` | keep working until `exp` (<= 15 min) | the user's live tokens on that device revoked | unchanged | next sign-in on the device is a normal PIN sign-in |
| Device revoke (A12) | `SessionService.cs:49-59` | tokens of that device stop immediately (device row revoked); other devices unaffected | that device's tokens revoked | revoked | pending codes for the device consumed; next sign-in there needs an email code |
| `SecurityVersion` bump only (admin edit of name, role or single permissions) | `AccessUseCases.cs:192-193` (file has uncommitted edits) | ALL devices stop immediately (version mismatch) | untouched, so refresh works and issues new claims | unchanged | the person is not signed out; clients renew once |
| Admin edit of email or phone ("sign-in details") | `AccessUseCases.cs:151-160` (uncommitted edits) | all stop immediately | all revoked | all revoked | full sign-out; PIN kept; every device needs an email code, sent to the new email |
| Deactivate (admin `SetActive` false) | `AccessUseCases.cs:224-229` (uncommitted edits) | all stop immediately (status Removed + version bump + devices revoked) | all revoked | all revoked | sign-in and refresh are 401; PIN kept |
| Reactivate (admin) | `AccessUseCases.cs:219-223` | none restored (devices and tokens stay revoked) | none restored | none restored | no version bump; every device needs an email code (re-trust clears `Revoked`) |
| Admin "sign out of every device" | `AccessUseCases.cs:236-247`, `RevokeSessions` `:568-574` (uncommitted edits) | all stop immediately (devices revoked) | all revoked | all revoked | `SecurityVersion` NOT bumped |
| Remove by operator (`--remove-user`) | `Program.cs:224-236` | all stop immediately (status + version bump) | all revoked | NOT revoked (rows stay valid) | PIN and rows kept; sign-in 401 |
| PIN set or PIN reset complete (A06, A09) | `PinSetupService.cs:41-47` | ALL devices stop immediately (version bump); the new pair belongs to the completing device | ALL the user's tokens revoked (every device), then one new | completing device trusted; others unchanged | other devices' next call is 401, refresh 401 -> sign-in with the new PIN (they are still trusted, no email code) |
| Trust expiry (`TrustLifetimeDays`) | `Entities.cs:91`, `Program.cs:125` | the device's tokens stop immediately at expiry | refresh refused (device not trusted) | expired | re-verification (A03) replaces the expiry |
| Refresh token expiry / replay | A10 | unaffected | expired token refused; a replayed token revokes the device's tokens | unchanged | |
| Pause | `SessionService.cs:32` | unaffected | refresh refused while paused | unchanged | |
| Operator re-provision of a changed or revived user | `UserProvisioning.cs:65-75` | all stop immediately | all revoked | all revoked | see section 9 |

## 6. Enumeration resistance and timing

### 6.1 Responses that must be byte-identical

"Seen" in `tests/api/AuthTests.cs:38-45` = status code + every response header (`response.Headers` and `response.Content.Headers`) EXCEPT `Date`, `Content-Length`, `X-Request-ID`, sorted by name and joined, + the whole body. Two responses are equal only if all of that matches. Any new per-request header on `/auth/**` (a timing header, a trace id, a rate-limit header) breaks it unless it is added to the exclusion list in the test. `X-Request-ID` is set by the request middleware on every response (`Program.cs:151-162`, echoes the caller's header, else the trace id); `/auth/**` is never compressed (`Program.cs:165`).

| Pair that must be identical | Endpoints | Test |
|---|---|---|
| unknown number vs known account on an untrusted device whose account is paused, any PIN | A01, A02 | `AuthTests.cs:55-65` |
| unknown number vs known account past the untrusted cap (any PIN) | A01 (and A02) | `AuthTests.cs:112-127` (cap 10 via `SignInService.UntrustedAttemptLimit`) |
| unknown number vs wrong PIN on an untrusted device (counted, but answered `401 authentication_failed`) | A01, A02 | `AuthTests.cs:55-65`, `:112-127` |
| number that does not normalize vs unknown well-formed number | A01, A03, A04, A05, A06 | `AuthTests.cs:148-167` |
| inactive account vs unknown number | A01-A09 | HTTP inventory 2.2 common block |
| `setup-pin/request` for a number with no account vs one that is not eligible (nothing sent) | A04, A07: always `202 check_email` | `AuthTests.cs:160`, HTTP inventory |

Rules the port must keep: (1) the paused answer (`423`) only on a trusted device; (2) the capped untrusted answer equals the unknown-number answer; (3) A06/A09 validate the PIN shape before touching the account and reveal the policy `minimumPinLength` only to a request that proved a valid code (`AuthTests.cs:477`); (4) A04/A07 answer 202 for every input that passes pre-validation, never revealing whether a mail was sent.

### 6.2 Timing

| Behaviour | Where |
|---|---|
| Constant-time compares: PIN hash, code hash (`CryptographicOperations.FixedTimeEquals`) | `Security.cs:70`, `AuthCodes.cs:49` |
| A01/A02 always run one PBKDF2 (210 000 iterations), against the dummy hash for unknown, removed or PIN-less accounts | `SignInService.cs:15` |
| Everything else is NOT time-equalised: A03/A05/A08 skip the code lookup for unknown accounts; A06/A09 run PBKDF2 only on full success; A10 stops at an unknown token | `SignInService.cs:60-62`, `PinSetupService.cs:41` |
| A04/A07: the mail is sent after the reply so response time does not show whether an account exists (the database work for a known account is still done before the reply) | `AuthUnitOfWork.cs:35-44` |
| A01/A02 on a new device: the mail is sent BEFORE the reply (slower; reachable only with the right PIN) | `AuthUnitOfWork.cs:46` |
| No fixed delay, jitter or sleep anywhere | whole of `Application/Authentication` |
| Rate limit: 30 requests per minute per client IP across ALL `/auth/**`, 429 with empty body | `Program.cs:91-97` |

## 7. Mail

| Item | Value | Source |
|---|---|---|
| Contract | `IEmailSender.SendCode(email, code, purpose, ct)` | `Application/AuthContracts.cs:7-10` |
| Message record | `VerificationMailer.Message(CodeId, UserId, Email, Code, Purpose, CorrelationId)`; `CorrelationId` = the request id (`IOrganizationContext.CorrelationId`) | `Security.cs:121`, `AuthCodes.cs:40` |
| Recipient | `users.Email` as stored (never the request's `email` field) | `AuthCodes.cs:40` |
| Subject | `Your verification code` (same for all purposes) | `Security.cs:111` |
| Body | `Your {purpose} code is {code}. It expires in 10 minutes.` where `{purpose}` is the raw enum name: `FirstSetup`, `NewDevice` or `PinReset`; plain text; no HTML, no link | `Security.cs:111` |
| SMTP sender | `System.Net.Mail.SmtpClient`: host `Email:Host` (required), port `Email:Port` (default 587), SSL always on, credentials `Email:Username` / `Email:Password` always set (even if empty), From = `Email:From` (required). One client per send; no explicit timeout (framework default 100 s). The NewDevice send honours the request cancellation token; the after-reply send uses none | `Security.cs:103-114`, `appsettings.json` `Email` section |
| Which sender | Development or Testing environment AND a "local" connection string: `LogEmailSender`; anything else: `SmtpEmailSender` | `Program.cs:73-74` |
| Log mailer | writes `DEV EMAIL to {Email}: {Purpose} verification code {Code} (10 minutes)` at Information; never for production | `Security.cs:94-101` |
| Startup checks | outside Development and Testing: `Email:Host`, `Email:From` and `ConnectionStrings:Auth` must be non-empty or the process refuses to start | `Program.cs:42-47` |
| Delivery after commit | the code row is committed first; mail is sent only for the attempt that committed (a rolled-back retry's message is dropped because `AuthResult.Mail` comes from the last attempt) | `AuthUnitOfWork.cs:11-33` |
| NewDevice | awaited before replying; failure or exception = code withdrawn + `503 service_unavailable`; a withdrawn code does not start the cooldown, so an immediate retry sends a new one | `AuthUnitOfWork.cs:46`, `Security.cs:129-144` |
| FirstSetup / PinReset | `SendLater`: `Task.Run` with the request context suppressed, fire and forget, tracked in a set; failure = logged error + code withdrawn; the reply was already `202 check_email` | `Security.cs:146-154` |
| Withdraw | new scope and a new `AuthDb`: load the code by id, `Withdraw()` (Consumed, `ExpiresAt = CreatedAt`), save. A failure to withdraw is logged and swallowed (the code then stays live though nobody received it). No lock, no transaction | `Security.cs:162-177` |
| Logging of failures | `Error` with purpose, user id, correlation id and the exception; never the code or the address | `Security.cs:139,174` |
| Shutdown | on `ApplicationStopping` the host waits up to 10 s for in-flight after-reply sends (`VerificationMailer.Idle`) | `Program.cs:149` |
| Per-attempt consistency | the code in the mail is the code of the committed row; a superseded or rolled-back code is never mailed | `AuthCodes.cs:30-40` |

## 8. Organization security policy

`OrganizationSecurityPolicy` (`Domain/Organization.cs:280-300`), one row per organization (`security_policies`). The bounds live in three places that must agree: `SecurityPolicyBounds` (`Security.cs:23-35`, clamps on READ), `OrganizationSecurityPolicy.Validate` (rejects on WRITE with `ArgumentException "Invalid security policy."`, run from `ValidateWrites`, `OrganizationModel.cs:105-106`), and database check constraints added by migration `NormalizeSecurityPolicy` (`Infrastructure/Migrations/20260929200500_NormalizeSecurityPolicy.cs:13-30`; its `ClampSql` is a frozen one-time data fix).

| Field | Default | Min | Max | Read by auth? |
|---|---|---|---|---|
| `PinLength` | 4 | 4 | 8 | yes: minimum length of NEW PINs (A06/A09 step 3) |
| `LockoutThreshold` | 5 | 3 | 10 | yes: wrong PINs on a trusted device before a pause; also sent to mobile |
| `LockoutMinutes` | 15 | 1 | 60 | yes: pause length; also sent to mobile |
| `AccessTokenMinutes` | 10 | 1 | 15 | yes: access token lifetime |
| `RefreshTokenDays` | 30 | 1 | 90 | yes: refresh token lifetime |
| `IdleUnlockSeconds` | 300 | 30 | 3600 | no (client idle lock; returned by the settings endpoints) |
| `PasswordMinLength` | 12 | 12 | 128 | no (stored, unused by any auth flow) |
| `PasswordHistory` | 5 | 0 | 24 | no |
| `PasswordComplexity` (bool) | true | | | no |
| `AllowPinSignIn` (bool) | true | | | no; `Validate` refuses `false` ("PIN sign-in cannot be disabled.") |

How the policy is found (`AuthPolicy`, `AuthAccounts.cs:55-65`): `For(userId)` = the organization of the user's single active membership (tenant filters ignored); none -> the built-in defaults; `ForOrganization` reads the row without tracking, clamps it, and falls back to the defaults when no row exists. `SessionTokens.Issue` uses `ForOrganization(membership.OrganizationId)`. A saved policy takes effect on the next sign-in or issue; it bumps no `SecurityVersion` and revokes nothing. Settings screens save it through the `securityPolicy` merged section (`Application/Settings/SettingsSections.cs:40`, **(uncommitted)** directory). The `IValidatable` interface on the class is **(uncommitted)** (`Domain/Organization.cs` diff); the bounds themselves are committed.

## 9. Operator commands and provisioning

Process modes (`Program.cs:181-240`; all skipped when the environment is `Testing`). An option value is the next argument unless it starts with `--` (`Option`, `Program.cs:185`). After a mode finishes the process exits without starting the server. Errors are unhandled exceptions (non-zero exit, stack trace).

| Mode | Behaviour |
|---|---|
| `--migrate` | one-time rename of a legacy migration id in `__EFMigrationsHistory` when the database exists (.NET-specific, no Python equivalent), then apply pending migrations, log `Migrations applied.`, exit. Production never migrates on start; each release runs this once before replicas start (`apps/api/Dockerfile` comment) |
| Development start | when `DevelopmentMode` (Development env + local database): same history rename, `MigrateAsync`, and `DemoSeed.Run` when env `ALLOW_DEMO_SEED=true` (`Program.cs:201-213`). `DemoSeed` sets `db.Provisioning = true` (`Infrastructure/DemoSeed.cs:30,74`) |
| `--provision-user <email> --phone <mobile> [--role <role>] [--first-name <n>] [--last-name <n>] [--organization-name <n>]` | `UserProvisioning.Provision` (9.1); logs `Provisioned {Email}; they can now set a PIN with an email code.`; exit. `--phone` is required |
| `--remove-user <email>` | trim + lower-case the email; must parse as an address; unknown email = silent no-op save; known: `User.Remove()` (`Status = Removed`, `SecurityVersion++`) and all the user's refresh tokens revoked; trusted devices are NOT revoked and the membership is untouched; exit. Their access tokens die at once (status/version); refresh and sign-in are 401 |
| none of the above | a warning is logged when active users have no active membership: `{Count} active users have no organization membership and cannot sign in. Run --provision-user ...` (`Program.cs:237-239`); the server then starts |

There is no operator command to clear a pause, clear the untrusted cap, reset a PIN, revoke sessions or list users. Equivalents: pause or cap -> the person completes A07-A09; revoke sessions -> `POST /setup/people/{id}/sign-out` (`Api/SetupEndpoints.cs:93`, permission `people.manage`, `AccessUseCases.SignOut`) or deactivate; remove -> `--remove-user` or `POST /setup/people/{id}/deactivate`.

### 9.1 `UserProvisioning.Provision` (`Infrastructure/UserProvisioning.cs:16-84`, committed)

1. Validate: email parses (`MailAddress.TryCreate`) else `ArgumentException "A valid email is required."`; phone normalizes else `"A valid mobile number such as 0712345678 is required."`; `Role`, when given, must be a key of `PermissionCatalog.RolePermissions` else `"Unknown role. Use one of: ..."`. Email is stored trimmed and lower-cased.
2. Set `db.Provisioning = true` for the whole call (reset in `finally`). Effect: `ValidateWrites` skips the tenant guards (writes of tenant entities need no current organization; `Organization` writes allowed) (`OrganizationModel.cs:94,99`).
3. Organization: more than one exists -> `InvalidOperationException`; exactly one -> reuse; none -> create it (name `--organization-name` or `My fleet`, slug `my-fleet`) with default `OrganizationLocalization`, `OrganizationBranding`, `OrganizationSecurityPolicy`. Catalog roles missing from the organization are inserted (`EnsureRoles`; permissions live only in the code catalog).
4. Phone uniqueness: another user (different email) already has this normalized number -> `ArgumentException "That mobile number already belongs to someone else."`.
5. User: find by email (unique); create `Active`, or update `PhoneNumber` and set `Status = Active`. An existing PIN is kept.
6. Membership: create (names from `--first-name` / `--last-name`, else derived from the email local part split on `.`: Title-cased first and last, defaults `New` / `Member`) or reactivate an inactive one and overwrite names only when given.
7. Role: `--role`, else the existing role, else `Owner`. A different existing role link is replaced.
8. If the user already existed AND (phone changed, was not Active, membership was inactive, or role changed): `BumpSecurityVersion`, revoke ALL their trusted devices and ALL refresh tokens. A no-change re-run bumps and revokes nothing (idempotent).
9. `Owner` and `Office admin` roles get an all-companies `SetupDataScope` when they have none.
10. `SaveChangesAsync`. The new person has no PIN and no trusted device: they start with A04-A06.

## 10. Naming audit (C# names the rewrite should not copy)

Wire text (status strings, JSON property names, claim names, mail text) is NOT renamed; only internal names are.

| C# name | Where | Problem | Suggested name |
|---|---|---|---|
| `Auth` namespace, `Auth.Api.csproj`, `AuthDb` | everywhere | the product is "xcode"; `AuthDb` holds the whole domain (revenue, setup, petty cash), not only auth | package `xcode`; one session/unit-of-work type named for the app |
| `AuthDevices`, `AuthPolicy` defined in `AuthAccounts.cs` | `AuthAccounts.cs:26,55` | file name hides two services; `AuthPolicy` reads `OrganizationSecurityPolicy`, it is not a policy | `DeviceTrust`, `SecurityPolicyReader` |
| `AuthRequest` | `AuthContracts.cs:19` | one bag of six fields reused by every endpoint, most unused per endpoint | per-endpoint request models (wire shape unchanged) |
| `AuthResult.Accepted()` | `AuthContracts.cs:35` | never called | drop |
| `IssuedCode`, `VerificationMailer.Message` | `AuthCodes.cs:9`, `Security.cs:121` | two records for one outgoing mail | `PendingMail` |
| `TokenIssuer.Hash` | `Security.cs:76` | used for codes and refresh tokens, not only token issuing | `keyed_digest` (HMAC-SHA256, upper-case hex) |
| `User.Version`, `User.SecurityVersion`, claim `version` | `Entities.cs:15,17`, `Security.cs:81` | three different "versions"; the claim carries the security version | `row_version`, `security_version`; claim name stays `version` |
| `TrustedDevice.DeviceId` | `Entities.cs:87` | a client-chosen string, not the row id (`Id` is a Guid) | `device_key` (wire keeps `deviceId`) |
| `FailedAttempts`, `UntrustedFailedAttempts` | `Entities.cs:13,16` | unclear which applies to which devices | `trusted_device_failures`, `untrusted_device_failures` |
| `SignInService.UntrustedAttemptLimit` | `SignInService.cs:9` | public constant on a service class | module constant `UNTRUSTED_DEVICE_LIMIT` |
| `CodePurpose.FirstSetup` / `NewDevice` / `PinReset` vs URLs `setup-pin` / `verify-device` / `pin-reset` | `Entities.cs:4` | the enum names are also the text in the mail body (`Your FirstSetup code ...`), so the TEXT must be kept | internal `first_setup`, `new_device`, `pin_reset` plus an explicit label map to the three mail words |
| `VerificationMailer.Withdrawn` | `Security.cs:126` | static duplicate of `VerificationCode.IsWithdrawn`, unused | one predicate |
| `AuthOptions.DevelopmentMode` | `AuthContracts.cs:17`, `Program.cs:39` | looks like configuration but is computed (environment + "local" database) | `dev_conveniences_enabled`, computed, not bindable |
| `CurrentOganizationId` | `AuthDb.cs:9` | typo | `current_organization_id` |
| `organizationContext` (lower-case class) | `Program.cs:62` | class named like a variable | `RequestOrganizationContext` |
| `AuthDb.Provisioning` | `AuthDb.cs:10` | a mutable flag that bypasses tenant guards | an explicit `system_scope` context manager |
| `PinRules.MinimumLength` vs policy `PinLength` | `AuthContracts.cs:41`, `Organization.cs:286` | two minimums with different roles (shape floor vs per-organization minimum) | `PIN_FLOOR` and `policy.pin_length` |
| `AuthGate` | `AuthGate.cs` | a per-key mutex map | `KeyedLock` |
| `LogEmailSender` registered in Testing | `Program.cs:73` | test double in the production wiring | test-only sender |

## 11. Open questions

Numbered for reference from `docs/07-auth.md`. "Decide" = a choice the rewrite owner must make; "Verify" = a fact to confirm with a test vector against the running .NET API.

1. Decide: failure after committed state changes. `SessionTokens.Issue` returns `401` when the active user has no active membership or no role, but the caller has already changed state and the transaction commits: A03 consumes the code and trusts the device, A06/A09 set the PIN and revoke every token, A10 revokes the presented refresh token, A01/A02 clear the lockout. Reachable only for malformed data (user without membership or role). Copy it (byte-for-byte state) or roll back?
2. Decide: serialization in PostgreSQL. .NET relies on an in-process semaphore per key plus SERIALIZABLE (SQL Server blocks, so conflicts are rare) and treats a concurrency-token conflict as a 500. PostgreSQL SERIALIZABLE raises `40001` at commit instead. Options: a per-user row lock or advisory lock keyed by the lock key, plus retry on `40001`; and whether A10/A11 (key `device:<id>`) must also be serialised with the user's phone-keyed flows (today they are not).
3. Verify: email handling. `MailAddress.TryCreate` accepts forms such as `Name <a@b.c>`; the Python validator must be chosen to match (or the difference recorded in the HTTP contract). `users.Email` is unique under SQL Server's default case-insensitive collation; PostgreSQL needs `citext` or a lower-cased unique index. Provisioning lower-cases; the admin person-edit path was not checked here.
4. Verify: string lengths. All caps (deviceId 128, phone 14, pin 8, code 32, refreshToken 256, email 320) are UTF-16 code units in .NET; Python counts code points, so an astral character differs. Also confirm how `System.Text.Json` treats a lone surrogate in a PIN (PBKDF2 input is UTF-8; Python's encoder raises on a lone surrogate).
5. Verify: `PhoneNumber.Normalize` uses a Unicode-aware `\D` and a culture-sensitive `StartsWith("254")`. Build test vectors with full-width and Arabic-Indic digits, zero-width characters and a leading `+` before porting; the intended result for any non-ASCII digit is "not a number".
6. Decide: `IsLocalDatabase` (`Program.cs:29-36`) is a substring test on the connection string (`.db` matches any host with `.db` in it). The rewrite needs its own rule for "development conveniences allowed" (dev codes, no resend cooldown, log mailer) that cannot be switched on by accident in production.
7. Decide: mail robustness. No SMTP timeout (default 100 s) on the NewDevice path, so one sign-in can hang that long and a client disconnect (cancellation) is treated as a send failure (code withdrawn, 503). After-reply mail is in-process fire-and-forget: a crash loses it while the code row stays live and counts toward the caps. Keep, or add a timeout and an outbox?
8. Decide: the resend cooldown counts consumed codes too (only withdrawn ones are excluded), so a request right after a successful setup or reset within 1 minute is silently skipped (`202`, no mail). Intended? Copy as is.
9. Decide: JWT `version` is the only link to `SecurityVersion`, and pause is not checked per request (an access token issued before a pause keeps working). Intended; keep.
10. Verify: JWT details not visible in the C#: `nbf`/`exp` are integer seconds (truncated), header is `{"alg":"HS256","typ":"JWT"}`, a single `permission` claim is a string and several are an array (HTTP inventory 1.5 states this; confirm byte-for-byte with a captured token).
11. Decide: PIN hashes carry no iteration count, so changing 210 000 later needs a format change (for example rehash at next sign-in). Not a .NET behaviour; out of scope unless wanted.
12. Verify: refresh replay under concurrency. Two simultaneous refreshes with the same token are serialised by `device:<id>`: the first succeeds, the second hits the replay branch and revokes the first's new token. Confirm the web and mobile single-flight code makes this unreachable in practice.
13. Decide: more than one active membership for a user makes `SingleOrDefault` throw (500) in `AuthPolicy.For` and `SessionTokens.Issue`. The product is single-organization per user today; the rewrite should either keep the constraint or fail cleanly.
14. Verify: `Application/AccessUseCases.cs` has uncommitted edits; the revocation rows in 5.4 that cite it (person edit, deactivate, reactivate, sign-out) should be re-checked once it is committed. Reactivate does not bump `SecurityVersion` (devices and tokens were revoked on deactivate).
15. Discrepancy to correct in the HTTP inventory: A12's `400 invalid_request` for an over-long path id is unreachable (the `403` device-claim comparison runs first, and a valid token's device claim is at most 128 characters). Its cited lines for `AuthService.cs` no longer exist.
16. Not equalised timing (6.2): A03, A05, A08 and A06/A09 differ in cost between known and unknown accounts. The tests only compare bytes, not time. Decide whether the port adds dummy work.
17. `appsettings.Development.json` does not exist; only `appsettings.json` (empty `Auth:SigningKey`, empty `Email` values, SQL Server connection string). Environment-specific values come from environment variables (`.github/workflows/ci.yml:116-120` shows `Auth__SigningKey`, `Email__Host`, `Email__From`).
