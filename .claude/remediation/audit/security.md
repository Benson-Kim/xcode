# Security audit: revenue app (api, web, mobile, shared)

I read the files you listed plus the rest of the API surface (Setup, Revenue, Access, Organization endpoints, domain and EF model), the web proxy routes and the mobile storage layer. I ran nothing; this is a static review. I found no CRITICAL issues and no remotely exploitable HIGH issue. The fundamentals are strong.

## What is already done well

- **No SQL injection.** There are no `FromSql` calls anywhere. The only raw SQL is a constant migration-rename statement in `Program.cs:123`. All filters go through LINQ, including the history `text` filter.
- **Strong tenant isolation.** Every tenant entity has a global query filter on the `org` JWT claim. `AuthDb.ValidateWrites` rejects cross-organization writes. The access use cases block privilege escalation (only an Owner can grant Owner, you can only grant permissions you hold, and you cannot edit yourself).
- **Tokens are sound.**
  - The JWT validates issuer, audience, lifetime and signing key, with zero clock skew.
  - `OnTokenValidated` re-checks user status, `SecurityVersion` and device revocation on every request.
  - Refresh tokens are 48 random bytes, stored only as an HMAC, rotated on use, and reuse revokes the device's token family.
  - PINs use PBKDF2-SHA256 at 210k iterations, compared in constant time, with a dummy hash for unknown users.
- **Web cookies and proxy are well built.**
  - Cookies are `httpOnly` and `SameSite=Strict`. Tokens never reach browser JavaScript; the auth proxy returns only a whitelist of fields.
  - Origin checks are in place, bodies are size-limited, and the auth route is an allowlist.
  - The setup proxy has a strict path allowlist and rejects `..`, `.` and encoded slashes. It also encodes each segment and builds the upstream URL from the `API_URL` env var only, so there is no SSRF.
- **Logo upload is safe.** Only PNG, JPEG and WebP are accepted, with magic-byte checks, a 256 KB cap and a restrictive data-URL regex. SVG is explicitly refused.
- **Headers and CSP are good.** CSP is nonce-based with `strict-dynamic`, `object-src 'none'`, `frame-ancestors 'none'` and `connect-src 'self'`. HSTS, nosniff, X-Frame-Options DENY, Referrer-Policy and Permissions-Policy are all set.
- **Secrets are handled correctly.** `.env*` is gitignored. There is no hardcoded secret. The signing key must be at least 32 bytes, and the API refuses to start without one outside Development and Testing.
- **Other positives.**
  - The OpenAPI endpoint is only mapped in Development and Testing.
  - Brand URLs must be HTTPS.
  - The only `dangerouslySetInnerHTML` is a static theme script that carries the nonce (`apps/web/app/layout.tsx:27`).
  - I found no `console.*` calls in web or mobile source.

## Findings

### MEDIUM

**M1. A Development environment on a production host is a full authentication bypass** (A05 Security Misconfiguration, A07 Authentication Failures)
- `apps/api/Application/AuthService.cs:520`, `:504`; `apps/api/Program.cs:39,129`; `apps/api/Infrastructure/DemoSeed.cs:12-17`
- If `ASPNETCORE_ENVIRONMENT=Development` is set in production:
  - The email code is returned in the HTTP response as `developmentCode`.
  - The resend cooldown is skipped.
  - `LogEmailSender` logs codes and emails instead of sending them.
  - Demo users with known PINs (4826, 1379, 2580) are seeded.
  - The signing key falls back to a random one.
- `apps/web/app/api/auth/[...path]/route.ts:236` forwards `developmentCode` to the browser regardless of `NODE_ENV`.
- Fix:
  - Strip `developmentCode` in the proxy unless `NODE_ENV !== "production"`.
  - Make `DemoSeed` and `LogEmailSender` require an explicit opt-in flag such as `Dev:EnableDemo=true`, not only the environment name.
  - Fail startup if Development is combined with a non-local DB host or `Auth:SigningKey` is set.

**M2. Account lockout can be triggered by anyone who knows a phone number** (A07)
- `AuthService.cs:658-667`. Failed PINs count per phone number from any device or IP, and the account pauses for 1 to 60 minutes.
- A remote attacker can lock out any known employee on demand, which is a targeted denial of service.
- Fix:
  - Count failures per (account, device) for untrusted devices, and apply the account-wide pause only after failures from a trusted device. Or add a progressive per-IP delay.
  - Alternatively, only lock the account globally after N failures from distinct trusted contexts.
- Separately, `ClearPause` (`:652-653`) zeroes `FailedAttempts` when the pause ends. That allows indefinite guessing at roughly threshold per lockout period (default 5 per 15 minutes). A new device still needs the emailed code, so the PIN alone does not give a session. Keep a decaying counter and escalate the pause length instead of resetting.

**M3. Default rate limiting breaks down behind the web proxy, and the serialized auth gate is a DoS lever** (A04 Insecure Design, A05)
- `apps/web/app/api/body.ts:339-346`; `Program.cs:56-62`; `AuthEndpoints.cs:380,434`
- With the default `TRUSTED_PROXY_HOPS=0`, every web user reaches the API from one IP. That gives them a single 30-requests-per-minute bucket across `sign-in`, `refresh` and `GET /auth/session`, so legitimate load can trip 429 for everyone.
- The inverse is the risk: if `TRUSTED_PROXY_HOPS` or `KnownProxies` is misconfigured, `X-Forwarded-For` can be spoofed to bypass the per-IP limit.
- Every auth call also takes a global `SemaphoreSlim(1,1)` and runs PBKDF2 at 210k iterations (including for a PIN of up to 128 characters, `AuthEndpoints.cs:431`). An attacker distributing across many IPs can saturate sign-in for the whole system.
- Fix:
  - Add per-account and per-phone rate limiting in addition to per-IP.
  - Cap `Pin` at 8 characters before hashing.
  - Replace the global semaphore with per-user locking, relying on the serializable transaction.
  - Document or enforce `TRUSTED_PROXY_HOPS` as required in production.

**M4. Unauthenticated email-code requests can spam victims and allow slow code guessing** (A07, A04)
- `AuthService.cs:499-521`, `:693-703`
- `setup-pin/request` and `pin-reset/request` are unauthenticated and only need a phone number. They can email a real user's inbox once per minute (email bombing).
- The 6-digit code allows 5 guesses per code, and a new code is allowed every minute. That is about 5 guesses per minute against a 1,000,000 space, roughly 0.7% per day for a continuous attacker.
- This is a real exposure for accounts that have no PIN yet (first-setup), because a successful guess lets the attacker set the PIN.
- Fix: add a per-account hourly or daily cap on code issuance (not just 1 per minute). Count failed guesses per account across codes, and lock the flow after a threshold. Consider longer or alphanumeric codes.

**M5. The mobile offline PIN check is an unsalted-cost SHA-256 of a 4 to 8 digit PIN, and the retry counter lives next to it** (A02 Cryptographic Failures, A04)
- `apps/mobile/src/lib/storage.ts:344-366`, `:368-384`
- The stored value is `SHA256(salt:pin)`. If the vault contents are extracted (rooted device, backup, forensic access), the PIN falls instantly (10^4 to 10^8 candidates).
- The offline tries and pause counter are also stored in the vault, so someone with write access can reset them.
- The refresh token is stored in the same vault, so the incremental risk is the PIN, which is likely reused elsewhere.
- Fix:
  - Use a slow KDF (PBKDF2 or scrypt with 100k+ iterations) for the offline check.
  - Better, put the PIN verifier behind a Keystore or Keychain key that requires user presence (`requireAuthentication`, biometric or device credential).
  - Do not rely on a counter the attacker can reset.

### LOW

**L1. Trusted devices never expire by default** (A07). `appsettings.json:7` has `TrustLifetimeDays: null`, which `AuthService.cs:496` turns into no expiry. The web "remember" cookie lasts 365 days (`route.ts:138`). Fix: set a default of 30 to 90 days.

**L2. Access tokens remain valid after sign-out until they expire (at most 15 minutes)** (A07, token replay). `SignOut` (`AuthService.cs:783`) revokes refresh tokens but not the device, and `OnTokenValidated` only checks device revocation, user status and `SecurityVersion`. Fix: bump `SecurityVersion` on explicit sign-out, or track a revoked-session id (`jti`).

**L3. Concurrent refresh can sign users out** (A04). `AuthService.cs:765-770` treats a second use of a just-rotated token as theft and revokes the whole device family. Two tabs or a retried request can trigger this, since the dedupe in `apps/web/lib/api.ts:485` is per tab only. Fix: allow a short grace window (about 10 seconds) in which the previous token is accepted once more, returning the same result.

**L4. Cookie hardening** (A05)
- `route.ts:125-130`: `secure` is only set when `NODE_ENV === "production"`.
- Cookies lack the `__Host-` prefix.
- The refresh cookie is sent on all paths. Scope it to `/api/auth` and use `__Host-` names (`__Host-access`, `__Host-refresh`).

**L5. Origin check allows requests with no Origin header** (A01/A05). `route.ts:98-104,160-171` and the setup proxy do the same. `SameSite=Strict` is the real CSRF defence and is adequate. For defence in depth, also require `Sec-Fetch-Site: same-origin` or reject a missing Origin on POST/PUT/DELETE.

**L6. API has no HTTPS or HSTS handling and uses permissive host config** (A05). There is no `UseHttpsRedirection` or `UseHsts` (`Program.cs`), and `AllowedHosts` is `"*"` (`appsettings.json:22`). The connection string uses `TrustServerCertificate=True` (`appsettings.json:3`), which disables certificate validation for the DB link. Fix: set a real `AllowedHosts`, and use a proper certificate or `TrustServerCertificate=False` in production config. The default CORS origin `http://localhost:3000` (`appsettings.json:11`) should be overridden per environment.

**L7. Mobile has no HTTPS enforcement** (A02). `apps/mobile/src/lib/api.ts:513-517` accepts any `EXPO_PUBLIC_API_URL`, defaulting to `http://`. Tokens and PINs could cross the network in clear text if a release build is mis-configured. Fix: throw if the URL is not `https` in non-dev builds. Consider certificate pinning for a financial app.

**L8. The same secret is used for JWT signing and token or code hashing** (A02). `TokenIssuer.Hash` (`Security.cs:259`) keys HMAC with `Auth:SigningKey`. Rotating the key invalidates every refresh token and code; leaking it exposes both. Use a separate derived key (HKDF) for hashing.

**L9. Cross-organization user enumeration for people managers** (A01). `AccessUseCases.cs:128` returns "That mobile number or email already belongs to someone", revealing that a number or email exists in any tenant. Only users with `people.manage` can reach it; give a generic message.

**L10. `DotNetEnv.Env.TraversePath()`** (A05). `Program.cs:16` loads the first `.env` found walking up the directory tree, so a stray `.env` above the app could change configuration. Prefer an explicit path.

**L11. PII in logs** (A09). `Program.cs:138` logs an email address, and `LogEmailSender` logs email and code in Development and Testing only. There are no other findings: error responses to clients are generic, and the mailer logs user IDs, not emails. Do not run Development logging in production (see M1).

**L12. CSP and header gaps** (A05)
- `style-src 'unsafe-inline'` is required by the inline styles; the risk is low given the script policy.
- Not set: `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` and `Cache-Control: no-store` on the HTML shell.
- The CSP matcher in `proxy.ts:65` excludes any path starting with `api`, so a path like `/apiary` gets no CSP. Such paths currently just 404.
- Prefetches are intentionally excluded; they are not rendered.

**L13. Server-supplied error text shown in mobile** (A09). `apps/mobile/src/lib/api.ts:629-631` shows the API's `detail`/`title` directly. It is rendered as plain text, so it is not an XSS vector, but it can reveal internal validation wording.

## OWASP Top 10 (2021)

| Category | Status |
|---|---|
| A01 Broken Access Control | Protected. Tenant filters, per-request permission checks, scope checks and anti-escalation rules. Minor L9. |
| A02 Cryptographic Failures | Mostly protected (PBKDF2, HMAC-hashed tokens, SecureStore). Weak points: M5, L7, L8. |
| A03 Injection | Protected. No raw SQL, parameterised EF, no `dangerouslySetInnerHTML` of user data, no command execution. |
| A04 Insecure Design | Partly vulnerable: M2, M3, M4, L3. |
| A05 Security Misconfiguration | Partly vulnerable: M1, L4, L6, L10, L12. |
| A06 Vulnerable Components | Not assessed (no dependency scan run). Recommend `npm audit` and `dotnet list package --vulnerable` in CI. |
| A07 Identification and Authentication Failures | Strong design, with the gaps in M2, M4, L1, L2. |
| A08 Software and Data Integrity | Protected. Logo magic-byte validation, concurrency tokens, append-only audit events. |
| A09 Logging and Monitoring | Partly. Audit trail exists for settings and people changes. There is no failed-login alerting or logging, and some PII in logs (L11). |
| A10 SSRF | Protected. Upstream URL comes only from `API_URL`; the path is allowlisted and encoded. |

## Suggested priorities

1. M1: strip `developmentCode` in the proxy, and require an explicit flag for demo seed and the log email sender.
2. M3 and M4: per-account limits and a cap on email-code issuance.
3. M5: a slow KDF or Keystore-backed PIN check on mobile.
4. L1 and L2: default trust lifetime and sign-out token invalidation.