# Remediation program

Plan: artifact https://claude.ai/artifact/2uETHfTRdMZCP4j2skjzvW (from the 2026-10-06 seven-agent audit). Branch `fix/format`, worktree `xcode-wt/revenue`.

## How to run a session
Paste: `Implement Phase N as specified in .claude/remediation/phase-N.md.` Use `closure.md` for the final crosswalk and `single-finding.md` for one hard issue.

Every phase prompt starts the same way:
1. Read CLAUDE.md, this file, and `findings/phase-N*.md`.
2. Check for other sessions in the tree.
3. Record a baseline.
4. Make a checklist with one row per clause.
5. Delegate to Sonnet by default.
6. Run an auditor pass before reporting done.

## Files
- `audit/*.md`: the seven original review reports (security, safety, integrity, operability, scalability, extensibility, maintainability). They hold far more detail than the plan, including lows. Their line numbers are from 2026-10-06 morning and drift.
- `findings/phase-*.md`: findings re-verified against the code, with current file:line, state and implementation pointers.
- `phase-4.md`, `phase-5.md`, `phase-6.md`, `closure.md`, `single-finding.md`: the session prompts.

## Status
| Phase | State | Notes |
|---|---|---|
| 1 Safety & security | Done | Gaps found and closed during the Phase 2 session on 2026-10-06 (see handover). |
| 2 Domain integrity | Done | 2026-10-06. |
| 3 Operability | Started, stopped mid-flight | Its state when it stopped is residual 9. |
| 4 Scalability | Pending | `phase-4.md`, `findings/phase-4.md` |
| 5 Architecture & DRY | Pending | `phase-5.md`, `findings/phase-5-6.md` |
| 6 Maintainability & CI | Pending | `phase-6.md`, `findings/phase-5-6.md` |
| Closure | Pending | `closure.md` |

Update this table and the residuals at the end of every session.

## Commit hygiene
Phases 1–2 and Phase 3's partial work are committed on `fix/format` (4318865, titled "phase 1" but covering all three) and pushed to origin. Commit each later phase on its own, including every new file it adds. Commits are authored as Benson-Kim with no AI trailers.

## Handover: mechanisms later phases build on
- **Formatting:** `createFormatter(formats)` in `packages/shared/src/format.ts`, provided through `useFormats()` (web `lib/formats.ts`, mobile `src/lib/formats.ts`). Helpers take a `Formatter`. There is no global formatter.
- **Concurrency:**
  - Revenue saves map `DbUpdateConcurrencyException` to 409 (`RevenueEndpoints`), and `UnitOfWork.Execute` retries only change-log (Organization) collisions.
  - `User.Version` and `RefreshToken.Version` are concurrency tokens bumped by `AuthDb.BumpVersions()`, with migration `20261006084351_UntrustedFailedAttempts`.
- **Auth:**
  - `AuthGate` locks per account and does not dispose evicted semaphores.
  - PINs are capped at 8 before hashing.
  - Codes are capped per account at 5 per hour and 10 per day.
  - Trusted-device failures pause the account. Untrusted-device failures are capped per account (`AuthService.UntrustedAttemptLimit` = 10) and answered like an unknown number; the cap resets on `SetPin` or a verified new device. `IssueTokens` does not clear lockout; its callers do.
  - Value objects: `PhoneNumber` (E.164), `TimeZoneId`, `Locale`, `HexColour`.
- **Mobile:**
  - The offline PIN check is PBKDF2-SHA256 at 100k iterations in pure TS (`src/lib/pbkdf2.ts`), byte-identical to WebCrypto's; v1 checks are upgraded on the next online sign-in.
  - Requests time out (Phase 3), and 5xx responses raise `ServerError`, a subclass of `OfflineError`.
- **Web proxy:**
  - `developmentCode` is forwarded only outside production.
  - Bodies are narrowed with `typeof` checks.
  - Any upstream 5xx on POST and on GET session becomes 503 `service_unavailable` with a `requestId`.
  - `upstreamUrl()` requires https except for exact `localhost`/`127.0.0.1` (parsed, so `localhost.evil.example` is refused), and requires `API_URL` in production.
- **Mobile AuthFlow:**
  - `complete` awaits the save and offline-unlock work, so `busy` covers the whole operation.
  - A failed profile load shows on the current step.
  - `tests/fakeApi.ts` handlers may return a Promise, to hold a reply.

## Residuals: verified open or partial, needing a decision or a later phase
1. **`IsLocalDatabase` (Program.cs) matches substrings** (`.db`, `localhost`, `:memory:`), so a remote SQL Server host such as `sql.db.internal` counts as local. Under a mistaken `ASPNETCORE_ENVIRONMENT=Development` that re-enables the log mailer and development codes.
   - Fix: parse with `SqlConnectionStringBuilder` and compare the host exactly.
   - Phase 1 wording also asks for an explicit opt-in flag for the log mailer, and for a startup failure when Development is combined with a non-local database; neither exists.
   - Program.cs was being restructured by Phase 3 on 2026-10-06; check whether that session handled it.
2. **`kes()` decimals:** whole amounts show no decimals ("KES 1,500") while others show `numberDecimals` digits. Phase 2 item 4 says "always display with the same fraction digits". This needs a product decision, because it changes every money string and many test expectations.
3. **PhoneNumber mirror:** the C# value object is E.164. The TS helpers keep local formatting but accept exactly the same inputs; there is no TS E.164 type because nothing needs one. Revisit only if a client must send E.164.
4. **Device check:** the pure-TS PBKDF2 takes about 0.7–1.0 s per derivation on a heavily loaded desktop (V8 JIT), and Hermes interprets, so phones may be several times slower.
   - Measure unlock on a low-end Android.
   - If it is too slow, options are a native PBKDF2 (react-native-quick-crypto, which needs a dev build) or a keystore-backed verifier. Do not lower iterations silently.
5. **AuthFlow recovery after a profile-load failure.** The error now shows on whichever step the person is on, but "Check your connection and try again" can't work as worded:
   - On the new-phone code step, `VerifyDevice` has already consumed the one-time code, so confirming again is refused. The working path is Cancel, then re-enter the PIN (the device is trusted by then).
   - After setup or reset, the PIN is already set, and retrying replays a consumed code.
   - Fix this in Phase 6 item 3: change the message, or return the person to the PIN pad.
6. **Web `API_URL`:** a missing value is a logged 503 per request, not a startup failure. Startup fail-fast would need Next.js instrumentation; check `node_modules/next/dist/docs`.
7. **Response shape validation:** GET `/api/auth/session` now maps upstream 5xx to 503 `service_unavailable`, but it still forwards a 2xx body without validating its shape, and the shared auth client casts JSON.
8. **Mobile unlock on a 5xx:** shows an AuthError instead of the offline fallback (Phase 3 item 10 territory).
9. **Phase 3 state when its session stopped (2026-10-06 ~14:15)** (verify before relying on it):
   - The 30s session cache in `OnTokenValidated` existed around 13:35 (it accepted revoked tokens: `AccessLifecycleTests` ×2, `Phase1AuthContractTests.SwitchUserRevokesThisPhone`, and it changed `VehicleReportTests` query counts). It was gone again by 13:44: Program.cs has no `AddMemoryCache`.
   - `tests/api/OperabilityTests.cs` was updated at 13:54 to match: plain revocation tests and no cache expectations. The full API suite (284 tests, excluding the SqlServer category) passed at 14:40.
   - `/health/ready` filters on tag "ready", but no check is registered, so readiness never touches the database. `ReadinessProbeChecksDatabase` asserts only a 200 and cannot fail. Phase 3 item 3 is therefore not done.
   - Mobile `ServerError` (new, a subclass of `OfflineError`) is treated as offline by `src/revenue/week.ts` (`instanceof OfflineError` fallback), so a server 500 shows the cached "No internet" list. `revenue.test.tsx` › "loads the week again with Try again after it failed" fails. `RevenueScreen.tsx` already excludes `ServerError`; `week.ts` does not.
   - `P3-*` plan IDs appear in comments in Program.cs and `tests/api/OperabilityTests.cs`, which the house rules forbid.
   - Already fixed by that session at 13:42: AuthTests `Seen` now ignores `X-Request-ID`.
   - Fixed in the Phase 2 session at 14:20: `src/revenue/week.ts` rethrows `ServerError` instead of treating it as offline, so `revenue.test.tsx` passes.
10. **`AuthService.outgoing` is not reset between execution-strategy retry attempts.** Phase 3 added `EnableRetryOnFailure`, so a code issued in a rolled-back attempt could still be mailed. Fix it in the Phase 5 item 8 split, or at closure.
11. **Owned by no phase** (from `findings/phase-4.md` N1–N9 and the "Unowned" section of `findings/phase-5-6.md`; for closure unless a phase folds them in):
    - about 11 context queries per setup request;
    - heavy visibility predicates;
    - no ETag or reference-data caching;
    - non-revenue web lists not memoized;
    - rate limiting only on `/auth`;
    - `DotNetEnv` loads `.env` in every environment;
    - `AllowedHosts: "*"`, `TrustServerCertificate=True`, and no HTTPS redirection or HSTS;
    - a hot `Organization.SettingsVersion` row that serializes bursts of captures.
