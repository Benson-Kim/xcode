# Safety review: findings by severity

Scope read in full: `packages/shared/src/{auth,dates,format,revenue}.ts`, `apps/web/app/api/{body.ts, auth/[...path]/route.ts, setup/[...path]/route.ts}`, `apps/mobile/src/{session.ts, lib/api.ts, auth/AuthFlow.tsx}`, `apps/api/Domain/{Revenue,PhoneNumber,Organization}.cs`, `apps/api/Application/RevenueUseCases.cs`, `apps/api/Api/OrganizationEndpoints.cs`.

Not read: `AuthService.cs`, `AccessUseCases.cs`, the other `Application/Setup/*` files, `Domain/Setup/*`, `AuthEndpoints.cs`, `RevenueEndpoints.cs`, `SetupEndpoints.cs`, `Entities.cs`, `Access.cs`, the mobile `steps.tsx`/`PinPad.tsx`/`AuthLayout.tsx`, and `storage.ts`. Absence of findings there means nothing.

Nothing is CRITICAL. The tenant/authorization model and the proxy allowlists look sound.

## HIGH

**H1. `apps/mobile/src/auth/AuthFlow.tsx:182` and `:165`: sign-in succeeds with an empty identity if the session fetch fails.**
- `signedIn` calls `keepSession`, `savePinCheck` and `saveOfflineTries`, then `fetchPerson(...).catch(() => fallback)`.
- On a transient failure of `auth/session`, the app signs in with `firstName: ""`, `role: ""`, `permissions: []` and the default lockout policy.
- `onSignedIn` receives that person, so the user sees an empty greeting and a permission-less shell until something refetches.
- It also bypasses the organization's lockout policy for offline PIN attempts (`DEFAULT_PIN_POLICY`).
- A `StoredPerson` with empty `userId` is only persisted if `savePerson` ran. Check `storage.ts`; it was not read.
- Principle: fail-silent defaults, violating "fail fast".
- Fix: surface an error and stay on the pad, or retry.

**H2. `apps/mobile/src/auth/AuthFlow.tsx:248-251`: unguarded `setTimeout` race.**
- `press` sets `busy`, then a 180ms timer calls `setBusy(false)` and `complete(next)`. The timer is never cleared.
- If the component unmounts, or the user taps "Not you?" in that window, `complete` runs against stale closure state (`mode`, `flow`, `phone`, `chosen`). `LinkButton` is `disabled={busy}`, but `onDelete` and `press` read `busy` from a render closure.
- `setBusy(false)` fires before `complete` sets `busy(true)` again (`checkPin` and `savePin` do). There is a window where two `complete()` calls can both pass the `busy` guard.
- Fix: store the timer in a ref and clear it on unmount. Keep `busy` true across the whole operation.

**H3. `apps/mobile/src/auth/AuthFlow.tsx:99-120`: the pause effect reads stale closure state.**
- The tick calls `openPad(trustedHere ? "unlock" : "enter")` and `pinTries.current[phone]`, but only `pausedUntil` is in the dependency list (eslint-disable).
- Combined with `switchUser` setting `setPausedUntil(0)` and `setPhone("")`: if the interval fires before cleanup, it resets tries for the wrong `phone` key and can call `openPad` onto a stepped-away screen.
- Principle: hidden dependencies.

**H4. `apps/mobile/src/auth/AuthFlow.tsx:143-150, 329-361`: lockout counters are not atomic.**
- Online tries live in a plain in-memory ref (`pinTries`) and reset when the app restarts. The count is also keyed by `phone`, which the user can change.
- Offline tries use read-modify-write on storage (`loadOfflineTries`, then `saveOfflineTries`) with no serialization. Two concurrent `unlockOffline` calls both read `count`, so one failed attempt can be lost.
- A user can bypass the offline lockout by force-quitting? No: that count persists. But the online counter does not persist, so killing the app resets it. The server throttles via `paused`, so this is client-side convenience only. Do not rely on it for security.

**H5. `apps/web/app/api/auth/[...path]/route.ts:147-153`: request body fields are coerced without type checks.**
- `body.phoneNumber || ""` and similar pass whatever JSON type the client sent (number, object, array) straight into `JSON.stringify` for the upstream call.
- Only `body` being an object is checked (`!body || typeof body !== "object"`). An array passes that check.
- The API will presumably reject it, but the proxy's contract `AuthRequest` is not enforced. `JSON.parse(text)` is assigned to `AuthRequest` without validation.
- Fix: narrow each field with `typeof x === "string"` and drop non-strings.

**H6. `apps/web/app/api/auth/[...path]/route.ts:157-169, 192-201`: upstream response is trusted without runtime validation.**
- `response.json().catch(...)` is cast to `AuthResponse`, and `result.status` is forwarded to the client even for non-AuthStatus values.
- The `response.status` is also forwarded, so a 5xx body with an unexpected shape yields `status: undefined`.
- Cookies are only set when `result.accessToken && result.refreshToken` are truthy, which is good.
- `secondsUntilExpiry` returns `Math.max(0, exp - now)`. For an already-expired token, `maxAge: 0` deletes the cookie immediately, so a clock-skewed token silently signs the user out.

## MEDIUM

**M1. `packages/shared/src/dates.ts:67-99`: unvalidated date strings produce `Invalid Date`.**
- `calendarDate`, `shiftDate`, `daysBetween` and `weekdayIndex` accept any `string`. `isDate` exists but is not used inside them.
- A malformed value gives `NaN`. `shiftDate` then calls `toISOString()` on an Invalid Date, which throws `RangeError`.
- `weekdayShortName` and `shortMonthName` index arrays with `NaN` and return `undefined` typed as `string`. `mediumDateLabel` renders "undefined undefined".
- Fix: a branded `CalendarDate` type, or parse-then-validate at the boundary (API responses).

**M2. `packages/shared/src/dates.ts:100-121`: `dateParts` has unchecked assumptions.**
- `values.year!` is a non-null assertion on `Object.fromEntries` output, which is `any`-typed.
- `formatTimestamp` calls `new Date(value)` with no validity check. `formatToParts` throws `RangeError` on an Invalid Date.
- `formatCalendarDate` passes the raw `timeZone` to `Intl.DateTimeFormat`, which throws for an invalid zone. `safeTimeZone` is applied in `formatTimestamp` only, not in `formatCalendarDate`, `formatDateOnly` or `format.ts:formatDate`. A bad zone from settings would crash those paths.
- `format.ts` `Formats.timeZone` is `string`, but `configureFormats` takes `Partial<Formats>` straight from the server with no validation.
- Fix: apply `safeTimeZone` in one place (`formatCalendarDate`).

**M3. `packages/shared/src/dates.ts:177-191`: `compactDateRange` is fragile.**
- It strips the year with `replace(/ \d+$/, "")`, which only works for the "medium" pattern's output. It is called by `formatCalendarDateRange` only when `datePattern === "medium"`, but `compactDateRange` is exported and takes any `formatDate`.
- No ordering check: `from > through` renders a backwards range.

**M4. `packages/shared/src/format.ts:33-37`: module-level mutable singleton.**
- `let formats` is mutated by `configureFormats`, and the formatters (`kes`, `formatDate`, ...) read it implicitly.
- This is global hidden state. It is not safe with concurrent React renders or with server rendering in Next.js (state is shared across requests/users in the same Node process).
- Server rendering with per-organization formats could leak one tenant's currency or locale into another's render.
- Principle: DIP/SRP, global state. Prefer a context or an explicit `Formats` argument.
- The `useGroupping` typo is also baked into the shared contract and the API (`UseGroupping`). It is consistent, but a rename would be a breaking change.

**M5. `packages/shared/src/format.ts:49-62`: number formatting edge cases.**
- `kes(NaN)` and `kes(Infinity)` render "KES NaN" or "KES ∞".
- `toLocaleString` throws `RangeError` if `numberDecimals` is outside 0-100, or if `minimumFractionDigits > maximumFractionDigits`. For a non-integer with `numberDecimals = 0`, minimum 0 and maximum 0 is fine, but the server's range `0..6` is the only guard.
- `money(-0)` is not negative, fine.
- `percentText` does not guard `NaN` or negative values. The type allows `percent: number | null`, so callers must handle null (not shown here).

**M6. `packages/shared/src/format.ts:99-135`: phone logic is duplicated and inconsistent with the API.**
- `normalisePhone` here returns a local `07xx` form. The API `PhoneNumber.Normalize` returns `+254...`. Two normalizers with different canonical forms (DRY violation).
- Client edge case: a pasted 9-digit `7xxxxxxxx` becomes `07...`, but `"254"` followed by garbage (e.g. 254 plus 5 digits) becomes `0` plus the rest and then fails `phoneError`. That is acceptable.
- `normalisePhone` takes `value: string` but guards `(value || "")`, a type/runtime mismatch.
- `apps/api/Domain/PhoneNumber.cs:13`: `Regex.Replace` is called on each use without a timeout, and `\D` also matches non-ASCII digits' complement, so Unicode digits such as Arabic-Indic are stripped. `[0-9]` in the second regex is correct. Low risk.
- `PhoneNumber.cs:15` and `:24` use culture-sensitive `StartsWith(string)`. Use `StringComparison.Ordinal` (CA1310).

**M7. `packages/shared/src/auth.ts:105-128`: `createAuthClient` boundary.**
- The JSON body is cast `as AuthResponse` with no validation. A 200 with an HTML or empty body yields `{status:"authentication_failed"}` and then returns normally (since `response.ok`), so a caller sees a "successful" response with a failure status. Callers branch on `result.status`, so a missing branch means a silent no-op. See `AuthFlow.tsx:289-295, 371, 422`: when `status` is something unexpected, nothing happens and the UI just stops spinning with no message.
- Fix: throw `AuthError` when `status` is not recognised, or return a discriminated union.
- `baseUrl` and `operation` are interpolated unencoded. The `devices/${string}/revoke` template permits arbitrary text, so the caller must encode (mobile `authApi` does).
- `AuthRequest`: all fields are optional, so the compiler cannot enforce the "API rejects missing fields" rule that `authApi` comments on.

**M8. `packages/shared/src/auth.ts:4-13` and `AuthFlow.tsx:241-261`: PIN validation mismatch.**
- `validatePin` ignores the organization's `minimumLength` (the helper `pinHelp(minimumLength)` exists, but `validatePin` doesn't take it). Client accepts a 4-digit PIN; the server then returns `invalid_pin`, handled at `AuthFlow.tsx:373-383`. It works through a round trip but is Ask-not-Tell.
- `[...pin]` spreads by code point, so a non-digit never reaches there thanks to the regex. Fine.
- "Weak" detection only catches fully ascending or descending sequences, not partial or repeated patterns. Policy question, not a safety bug.
- `AuthFlow.tsx:258-260` maps every weak result to one message and discards `validatePin`'s text.

**M9. `apps/mobile/src/lib/api.ts:93-109, 112-125`: token renewal.**
- Positive: refresh is single-flight (`renewing ??=`) and cleared in `finally`.
- Problem: `authApi("refresh")` reads the refresh token from storage at call time, and `forgetThisPhone` calls `renew()` outside the shared promise chain's protection if `renewing` is null. That is OK.
- Problem: a rotated refresh token is saved only after the response. If the app dies between server rotation and `saveSession`, the stored refresh token is already invalid and the next launch is signed out. Unavoidable without server grace, but note it.
- `OfflineError` thrown during `renew()` propagates to the caller as `OfflineError`, not `SessionEndedError`. This is correct, since the session isn't known to be dead.
- `authorized`: `init.headers as Record<string,string>` is an unchecked cast. A `Headers` instance or array would be spread incorrectly and drop headers silently.
- `authorized` retries only on 401 and re-sends `init.body`. A body that is a stream would already be consumed; the current callers use strings, so it is fine.
- `apiGet:130-138`: `response.json().catch(() => ({}))` on a 204 or 200 with an empty body returns `{}` cast to `T`. `body.detail` is accessed on `{}`. `body` is `any`, so there is no type safety. A "successful" empty body is returned as `T`.
- `keepSession:78-86`: `accessToken: result.accessToken || ""` stores empty tokens for a malformed authenticated response. It should throw instead. A session with empty tokens makes `loadSession()` truthy (maybe) and `Bearer ` is sent.
- `apiUrl` falls back to `http://` for production if `EXPO_PUBLIC_API_URL` is unset. Cleartext tokens are possible if the env var is missing in a release build. Fail the build instead.

**M10. `apps/mobile/src/session.ts:15`: dense expression with an implicit trust decision.**
- `kept.userId ? kept.userId === session.userId : kept.phoneNumber === phoneNumber` decides whether the previous person's lockout policy applies. `StoredPerson` is returned as `kept` (it extends the policy fields), but the type of `policy` is a union and its fields are read directly.
- Race: `fetchPerson` can run concurrently from two paths. `loadPerson` then `savePerson` is non-atomic, so last-write-wins.
- `session.permissions` comes from the network with no validation (a missing array would store `undefined`).
- `apiGet<AuthenticatedPerson>` is only a type assertion.

**M11. `apps/api/Api/OrganizationEndpoints.cs:178-181`: preference write ordering.**
- The entity is mutated and (for a new row) added to the context before `Validate()` and `EnsureAllowed` run. If either throws, nothing is saved because `SaveChangesAsync` is not reached, so no corruption. But `Validate()` mutates `Locale` and `TimeZone` in place to normalised values, which is fine.
- `preference.FontScale = input.FontScale` with `double`: `Validate` checks `IsFinite` and the range. OK.
- Returns the tracked entity `UserPreference` directly (`Results.Ok(preference)`), exposing the persistence model as the API contract (SRP/ISP). Same for `OrganizationSettingsResponse`, which embeds `Organization`, `OrganizationLocalization` and other entities (mutable public setters, EF entities as DTOs).

**M12. `apps/api/Api/OrganizationEndpoints.cs:60-66`: the localization section does a second `FindAsync` after `Save`.**
- `FindAsync` for a freshly `Add`ed entity returns the tracked one, so it works, but `!` hides a possible null.
- `OrganizationCalendarDate(...)` is called with the new zone *after* the entry has been mutated. If the date check throws (`ArgumentException`), the tracked changes remain in the `db` context but are never saved. Fine for per-request scope.
- The `businessDate` case (lines 69-76) uses `new OrganizationLocalization()` (default Nairobi) when no row exists, but the GET path (line 25-27) uses an `OrganizationId`-scoped default. Equivalent, but the default is repeated in 6 places (DRY). Extract `OrganizationLocalization.Defaults`.

**M13. `apps/api/Api/OrganizationEndpoints.cs:199`: `JsonDocument.Parse(after)` is never disposed.**
- Resource leak (`JsonDocument` rents pooled buffers). Use `using` or `JsonSerializer.Deserialize<JsonElement>(after).Clone()`.
- `RecordChange` also runs `JsonDocument.Parse` on strings such as `"null"` (valid).
- `AutomaticReason:260`: `JsonNode.Parse(after)!.GetValue<string>()` throws `InvalidOperationException` if `after` is not a string. Reachable only via `businessDate`, which serializes `DateOnly?` as a string or `null`. Safe by construction but implicit.
- Line 274: `value.GetValue<int>()` cast to `DayOfWeek` is unchecked, but the server validated 0-6.

**M14. `apps/api/Api/OrganizationEndpoints.cs:39-85`: SRP and OCP violation.**
- A single lambda does authorization, a switch over section names, validation, persistence, change-log and audit writing, and reason formatting.
- Adding a section means editing the switch (OCP). Each section has different rules (`organization` has its own inline validation returning `Results.BadRequest`, others throw), so there are two error conventions.
- Endpoints talk directly to `AuthDb` (`db.Organizations`, `db.Localizations`, ...), bypassing the Application layer, unlike Revenue, which uses `RevenueUseCases` and repositories. Layering inconsistency (DIP).
- Suggest an `IOrganizationSettingsSection` strategy per section and an `OrganizationSettingsUseCases` class.

**M15. `apps/api/Domain/Organization.cs`: anemic and mutable entities (Tell Don't Ask).**
- `Organization.Id`, `Slug` and `Name` have public setters. `OrganizationLocalization`, `OrganizationBranding`, `OrganizationSecurityPolicy`, `UserPreference` and `OrganizationMembership` have all-public setters, and `Validate()` is a separate call. Nothing prevents persisting an invalid state, and an endpoint must remember to call `Validate()` (done in `Save<T>` and the preferences endpoint, but it is not enforced by the type).
- `OrganizationMembership.Version { get; set; }` is public settable while `Deactivate` and `Reactivate` bump it. `ApprovalLimit` has no validation (negative values allowed).
- `OrganizationMembership.FirstName/LastName` have no length validation here.
- `Organization.EnsureBusinessDateWithin` (line 100): `BusinessDate > organizationCalendarDate` compares `DateOnly?` with `DateOnly`. A null returns false, which is correct, but it relies on lifted-operator semantics.
- `ChangeBusinessDate` returns a bool that every caller ignores (`organization.ChangeBusinessDate(...)` at line 73). It also mutates before the caller can reject.
- `OrganizationLogo.Data` has a public setter and a mutable `byte[]`. The endpoint replaces fields via tuple assignment (line 103) instead of an `existing.Replace(uploaded)` method (Tell Don't Ask).
- `Locale.Direction` is allocated per call (low).
- `using System.Drawing;` is unused, and on non-Windows it pulls in a dependency. Remove it.
- `Regex.IsMatch` runs without `RegexOptions.CultureInvariant` or a timeout. Patterns are simple, so ReDoS risk is low.

**M16. `apps/api/Domain/Organization.cs:63-69`: `ContrastValidator` only checks against two fixed surfaces.**
- Dark-theme contrast is not validated, even though the dark theme was just added.
- `Primary`, `Secondary` and `Accent` are all required to pass 4.5:1 against both white and `#F6F3EC`. `Secondary` and `Accent` are not necessarily text colours. This is a product-rule question, not a safety bug.

**M17. `apps/api/Application/RevenueUseCases.cs:42-100`: `Save` does too much, and its ordering allows a TOCTOU.**
- It handles auth rules, idempotent replay, date rules, optimistic concurrency, the earliest-missing rule, entity mutation, snapshots and change-log text (SRP).
- There is a race between `repository.Record` and `repository.Add`. Two concurrent first-time saves for the same (vehicle, date) both see `existing is null`. Correctness depends on a unique index and on translating the resulting `DbUpdateException` into a conflict. I did not verify the repository or DbContext configuration. If there is no unique index on (OrganizationId, VehicleId, BusinessDate), duplicates are possible. For updates, `RevenueRecord.Version` needs to be a concurrency token (`IsConcurrencyToken`), otherwise the check at line 71 is not atomic. Verify the EF config.
- Line 71 `input.Version != existing.Version`: the type of `input.Version` is nullable on the client (`version?: number | null`), so a client that omits a version on an existing record always gets a conflict. This is correct and safe.
- Line 53: `date == default || date > actor.Today` is checked *after* the replay shortcut. A replay for a future date can only match an existing record, which cannot exist. Fine.
- Line 104: `PermissionCatalog.Groups.SelectMany(...).Single(...)` throws `InvalidOperationException` if the key is missing, turning a 403 into a 500. The keys are static, so this is only a refactoring hazard (it is not in a test).
- Snapshot returns `object`, so the audit shape is untyped (stringly-typed, loses compile-time safety).

**M18. `apps/web/app/api/body.ts:10-11, 17-23`: body-limit edge cases.**
- `Number(request.headers.get("content-length"))`: a missing header gives `Number(null) === 0` (finite and not over). A non-numeric value gives NaN and is skipped. Both then fall to the byte-count guard, so this is safe.
- `Buffer.concat(chunks).toString("utf8")` is fine.
- `forwardedFor` (line 33-40): `TRUSTED_PROXY_HOPS` is parsed correctly, and `isIP` validates. A huge `hops` yields `entries.length >= hops` false, so an empty string gives `{}`. Safe.

**M19. `apps/web/app/api/setup/[...path]/route.ts:53-69`: path allowlist.**
- Segments are checked for `.`, `..` and slashes, and then regex-matched on the *encoded* join. `(\/[^/]+)*` after any allowed prefix means any depth beneath (e.g. `people/anything/anything/...`), so this is a prefix allowlist, not an endpoint allowlist.
- `encodeURIComponent` after the check means `%2e%2e` is decoded by Next.js params into `..` before the check (it is, so it is caught). OK.
- `request.nextUrl.search` is forwarded verbatim, so the query is not validated. Harmless since the API validates.
- `method` is always from the set (the `allowedMethods` check is dead code, since the exports are only those four). Remove it or make it meaningful (YAGNI).
- A GET-only `Origin` check: `origin &&` means a request with no `Origin` header (curl, same-origin GET) passes. CSRF protection relies on `sameSite: "strict"` cookies plus the origin check. Acceptable, but note that a missing Origin on POST/PUT/DELETE is allowed. Consider requiring Origin (or `Sec-Fetch-Site`) for state-changing methods.
- `sameOrigin` compares `parsed.host` with the `Host` header, which is client-controlled. An attacker request supplying a matching Origin and Host is not a browser scenario, so this is fine in practice.
- `sameOrigin` is duplicated verbatim in both route files (DRY). Move it to `body.ts` or a shared `guards.ts`. The base URL `process.env.API_URL || "http://localhost:5000"` is also duplicated three times.
- `response.headers.get("Content-Type") || "application/json"`: the upstream content type is forwarded. An error body with `text/html` from an intermediary would be passed to the browser as-is. The browser would render it on the app's origin if navigated directly, but `Cache-Control: no-store` is set. Low.

**M20. `apps/web/app/api/auth/[...path]/route.ts:46`: GET `/session` returns raw upstream text** with `Content-Type: application/json` forced, and no timeout handling difference. Fine, but the 15s `AbortSignal.timeout` throws `TimeoutError`, which is caught by the generic `catch` and reported as 503. OK.

## LOW

- **L1.** `packages/shared/src/dates.ts:58-65`: `ordinal` mishandles negative or non-integer input (`-1 % 10 = -1` gives `undefined || "th"`). Result is "th", OK.
- **L2.** `packages/shared/src/dates.ts:92-93`: `daysBetween` returns `NaN` on invalid input; `Math.round` handles DST (UTC-based), so it is fine.
- **L3.** `packages/shared/src/dates.ts:98`: `firstOfMonth` uses `slice(0, 8)` and assumes a valid `YYYY-MM-DD`.
- **L4.** `packages/shared/src/dates.ts:13, 74-76`: `weekdayName(index)` and `shortMonthName(index)` return `string` but yield `undefined` out of range (no `noUncheckedIndexedAccess`). Enable `noUncheckedIndexedAccess` in the shared tsconfig. Also `WEEKDAY_NAMES` and `SHORT_WEEKDAY_NAMES` duplicate the same data (DRY).
- **L5.** `packages/shared/src/format.ts:43-46`: `first!` non-null assertions are redundant after `Number.isInteger`. `firstDayOfWeek` silently falls back to 1 on bad data, hiding the server defect.
- **L6.** `packages/shared/src/format.ts:137-139`: `initials` on an empty or undefined name gives "" (safe). For an emoji or surrogate pair, `charAt(0)` splits the pair. Cosmetic.
- **L7.** `packages/shared/src/format.ts:1-6` imports `formatDateOnly` as an alias and then re-exports a function of the same name with different arity: confusing API surface, with two `formatDateOnly` exports across modules.
- **L8.** `packages/shared/src/revenue.ts:17-23`: `parseRevenueAmount` strips commas and whitespace *anywhere* ("1,2,3,4" becomes 1234, `"1 0 0"` becomes 100). The pattern then caps at 12 integer digits and 2 decimals. The server's `SetupValue.Money` is the real bound (not read), so client and server limits can diverge. `Number(text)` for 12 digits plus 2 decimals is exact within double precision (14 significant digits), safe. No `REVENUE_NOTE_LIMIT` check here, and the C# side hardcodes `80` separately (`Revenue.cs:33`) (DRY, magic number duplicated across languages).
- **L9.** `packages/shared/src/revenue.ts:3-4, 86`: `reason: string | null` on `RevenueCell` but `RevenueReason | null` on `SaveRevenue`. The server's enum label is "No Crew" and is mirrored by hand in `REVENUE_REASONS`, with no compile-time link. `Revenue.cs` `Label()` and `REVENUE_REASONS` must stay in sync manually.
- **L10.** `packages/shared/src/revenue.ts:107-109`: `revenuePeriodLabel` falls back to the raw value (fine, defensive).
- **L11.** `packages/shared/src/auth.ts:86-103`: `AuthError` message is built in the constructor via a nested ternary (Open/Closed: a new status needs an edit). Does not set `this.name` or restore the prototype (matters under older transpile targets: `instanceof AuthError` can fail with ES5 targets). Verify the tsconfig target for mobile (Hermes) and web. This one is important if the target is ES5, since every `instanceof AuthError` check in `AuthFlow.tsx` would then silently fail. `AuthStatus` includes `"payload_too_large"`? No, but the web route returns `{status:"payload_too_large"}`, a value outside the union (type drift).
- **L12.** `packages/shared/src/auth.ts:130-132`: `pauseSeconds` is fine.
- **L13.** `apps/mobile/src/auth/AuthFlow.tsx:60`: `online` is computed but only passed to `PhoneStep`.
- **L14.** `AuthFlow.tsx:300`: `retryAfterSeconds ?? lockoutSeconds` is fine; a `NaN` or negative from the server would produce an immediate unpause (clamped by `pauseSeconds`).
- **L15.** `AuthFlow.tsx:403-408`: `confirmCode` has `if (busy) return` but `typeCode` calls `confirmCode(digits)` from a render closure, so a double-fire is possible if `busy` is stale. Minor.
- **L16.** `AuthFlow.tsx`: God component (about 650 lines, 24 `useState` hooks, a flow/mode/step state machine encoded as three string unions plus refs). SRP/OCP violation. Illegal combinations such as `step:"code"` with `mode:"unlock"` are representable. A reducer or state machine (e.g., a discriminated union) would make the unsafe transitions unrepresentable. `verifiedCode` and `challengePin` are held in refs and never cleared after use, so a PIN stays in memory. Clear `challengePin.current` and `verifiedCode.current` after success or `switchUser`.
- **L17.** `AuthFlow.tsx:262`: `matchesPinCheck` returns `boolean | null` (`match === null` is used at line 331), but `if (... && (await matchesPinCheck(entered)))` treats null as false (OK).
- **L18.** `apps/api/Domain/Revenue.cs:40`: `Note.Trim()` after `IsNullOrWhiteSpace` is safe under NRT flow analysis (`IsNullOrWhiteSpace` has `[NotNullWhen(false)]`). `Validate()` compares `note.Length > 80` after trimming, but a note containing only a reason that is not `Other` throws, which is correct. Magic number 80.
- **L19.** `Revenue.cs:78-96`: the constructor does not defensively check `capturedAt` beyond the offset, and `Replace` does not check `entry` null (a record cannot be null by NRT contract only). `RevenueEntry.Validate()` is a separate step: an invalid `RevenueEntry` can exist, but it is always validated in `RevenueRecord` before use (good).
- **L20.** `Revenue.cs:64`: `Id = Guid.NewGuid()` field initializer plus the private parameterless constructor: EF overwrites it. Fine. Consider `Guid.CreateVersion7()` for index locality (.NET 9+).
- **L21.** `apps/api/Domain/Organization.cs:80-82`: `Organization.Id/Slug/Name` have public setters (aggregate root with no invariants), see M15.
- **L22.** `apps/api/Api/OrganizationEndpoints.cs:301`: `JsonObject.Create(...)!` and `JsonObject.Create(input)!` use null-forgiving operators. `input` is verified as an Object, so it is safe. A client sending `"field": null` for a non-nullable property (e.g. `"currency": null`) deserializes to null, then `Validate` runs `Currency ?? ""` for that one, but `Locale`, `TimeZone` and `DatePattern` nulls throw `ArgumentException` or `NullReferenceException`. `new Locale(null)` throws ArgumentException (OK), and `DatePattern is not (...)` handles null. `OrganizationBranding.Validate` calls `DisplayName.Length` after `IsNullOrWhiteSpace`, which is safe, but `Primary = null` goes to `new HexColour(null)`, which throws ArgumentException (OK). So the nullable-null cases appear covered, though `LogoAlt`/`LegalName` use the same guard. Verified safe, but only by convention.
- **L23.** `OrganizationEndpoints.cs:49`: `SingleAsync` on `db.Organizations` relies on a global query filter by tenant. A missing org gives an `InvalidOperationException` (500). Acceptable.
- **L24.** `OrganizationEndpoints.cs:205-219`: `FindSystemTimeZoneById` is called on every request (cached by .NET, fine). Failure surfaces as a 400 `ArgumentException` for a server-side data problem, which is arguably a 500.
- **L25.** `OrganizationEndpoints.cs:16`: `SettingsJson` uses `JsonSerializerDefaults.Web`. The change-log `before`/`after` strings are sensitive-ish (security policy). Audit is intended, fine.

## Positive observations
- The web proxy has solid defense in depth: origin checks, strict SameSite, httpOnly cookies, body size streaming limit, path traversal checks, a timeout on every upstream call, and no token exposure to the browser (tokens are stripped from the JSON response).
- The mobile `renew()` is single-flight and the 401 retry is bounded to one.
- Domain `RevenueRecord` enforces tenant immutability, UTC instants, and business-date immutability, and the idempotent replay + optimistic version check is well designed.
- `OrganizationLogo.FromDataUrl` validates length before decoding, magic bytes, and a raster-only whitelist.

## Suggested priority
1. M7/H1: the auth client and sign-in fallback (silent failure paths).
2. M2/M1/M4: crash vectors and global state in the shared date and format modules.
3. M17: confirm the DB unique index and concurrency token for revenue.
4. H2/H3/L16: restructure `AuthFlow` into a reducer and clear timers.
5. M14/M15: extract the organization settings use case and remove public setters.
6. L11: check the TS target so `instanceof AuthError` works.