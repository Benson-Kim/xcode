# PR #3 — Codex review findings

Source: https://github.com/Benson-Kim/xcode/pull/3 (review of commit `e248637`, 2026-09-25).
Codex left 24 inline comments. Its security review never ran ("usage limits"), so this list is
not a security audit.

The PR stacks three branches (`auth` → `access` → `settings`); findings are fixed here on
`settings`, on top of the uncommitted refactor already in the working tree.

Status key: **Open** · **Fixed** (this pass) · **Already fixed** (was fixed in the working tree
before this pass) · **Deferred**

## Summary

| # | Sev | Area | Finding | Status |
|---|-----|------|---------|--------|
| 1 | P1 | API / migrations | `Phase1Setup` indexes `Users.PhoneNumber`, but no migration creates the column | Fixed |
| 2 | P1 | API / auth | Tokens require a membership, but upgraded users and `--provision-user` users have none | Fixed |
| 3 | P1 | API / auth | `/setup-pin/verify` and `/pin-reset/verify` never count failed code attempts | Fixed |
| 4 | P1 | API / auth | Saved security policy (PIN length, lockout, token lifetimes) is never applied | Fixed |
| 5 | P1 | API / recurring | Postponing a not-yet-started item leaves the old version posting | Fixed |
| 6 | P1 | Web / session | Nothing refreshes the 10-minute access token; every request fails after 10 min | Fixed |
| 7 | P2 | Web / people | Company/vehicle scope modes have no selectors, so limited-scope people can't be saved | Fixed |
| 8 | P2 | API / settings | `/setup/organization/*` group lacks the setup exception filter (403/400 become 500) | Fixed |
| 9 | P1 | API / access | `people.manage` alone can grant arbitrary permissions, including `access.manage` | Fixed |
| 10 | P1 | API / settings | Settings JSON deserialized case-sensitively; camelCase edits silently dropped | Already fixed |
| 11 | P1 | API / auth | PIN-request response leaks whether a phone number is registered (masked email) | Fixed |
| 12 | P1 | Web / auth | Web PIN input limited to exactly 4 digits; API accepts 4–8 | Fixed |
| 13 | P1 | Mobile | Mobile dashboard shows fabricated revenue/target/net figures | Deferred |
| 14 | P2 | Web / vehicles | Vehicle report "This week/This month" hardcoded to September 2026 | Fixed |
| 15 | P2 | Web / auth | "Remember this device" checkbox is ignored; every device is trusted for a year | Fixed |
| 16 | P2 | Web / recurring | Even split sends fractional cents (e.g. 100/3), which the API rejects | Already fixed |
| 17 | P2 | Web / settings | Personal preferences only reachable by `organization.manage` holders | Fixed |
| 18 | P2 | Web / recurring | Recurring screen also loads `/vehicles` (`vehicles.manage`), so view-only users get a 403 | Fixed |
| 19 | P1 | API / domain | `PhoneNumber.Normalize("+254…")` drops a digit and returns `+54…` | Fixed |
| 20 | P1 | Web / auth | "Send a new code" on device verification submits an empty PIN (counts as a failure) | Fixed |
| 21 | P2 | Web / recurring | Weekly recurrence uses the 1–28 month-day input instead of weekdays | Already fixed |
| 22 | P2 | API / access | Inactive people show no permissions; editing them wipes their overrides | Fixed |
| 23 | P2 | API / vehicles | Moving `JoinedOn` earlier leaves a zero-target gap before the first target | Fixed |
| 24 | P2 | API / settings | Required settings-change `reason` is validated, then discarded (not audited) | Fixed |


## Extra issues found while verifying

These weren't in the Codex review but block or undermine the fixes above.

| ID | Area | Issue | Status |
|----|------|-------|--------|
| X1 | API tests | 29/31 API tests fail. Causes: #19 (phone lookup never matches), `Request("9998")` passing the PIN as the *phone number* after `phoneNumber` became the first parameter, and test users seeded without the membership/role that #2 made mandatory | Fixed |
| X2 | Web | `OrganizationSettingsView.tsx` (uncommitted) is missing `return (` before its main JSX, so the settings and AuthPanel test files fail to compile | Fixed |
| X3 | API / recurring | `Revise` uses the earliest start across all versions; after a postponement it treats the item as running and rejects edits that keep the new start date | Fixed |
| X4 | Web / people | UI keeps its own copy of role defaults (and treats Owner as "all permissions"), so saving an Owner creates spurious overrides | Fixed |
| X5 | Web / auth | Refreshing the page always signs you out: `AuthPanel` starts on sign-in and never checks for an existing session | Fixed |
| X6 | Web / auth | Browser-autofilled phone/PIN are wiped on submit: autofill fires no event React sees, so state stays empty and the next render clears the fields | Fixed |
| X7 | Tooling | ESLint could not run: `eslint`, `eslint-config-next` and `typescript-eslint` were never installed, and `apps/web` declared `jsdom ^38.1.1`, a version that doesn't exist, so `npm install`/`npm ci` failed | Fixed |

---

## Details and fix plans

### 1. Add `PhoneNumber` before creating its index — P1
`apps/api/Infrastructure/Migrations/20260924172309_Phase1Setup.cs:675-679`

`InitialAuth` creates `Users` without `PhoneNumber` (the initial model snapshot listed it, but the
migration never added it). `Phase1Setup` creates `IX_Users_PhoneNumber`, so `MigrateAsync` fails on
any database built from the migration chain.

**Fix:** the migration now adds the column (`nvarchar(13)`, default `''`) before the index. Legacy
users all share `''`, so the unique index is filtered to `[PhoneNumber] <> ''` (model, snapshot and
designers updated; `dotnet ef migrations has-pending-model-changes` reports none). Renamed to
`OrganizationsAndFleet` (requested), keeping its timestamp.

**Correction:** I first assumed no database could have applied this migration. The local dev
database *had* applied it as `Phase1Setup`, because it was built from an earlier `InitialAuth` that
included the column. So startup now renames that `__EFMigrationsHistory` row before migrating. It's
idempotent and does nothing where the old name is absent. Verified against the dev database: it
started cleanly and nothing re-ran. That database keeps its original unfiltered index, which is
harmless since it has no blank numbers.

### 2. Provision memberships before requiring them for tokens — P1
`apps/api/Application/AuthService.cs:91-95`

`IssueTokens` returns 401 without an active membership and role. Upgraded databases have no
organization or memberships (`DemoSeed` is dev-only), and `--provision-user` only creates an email
row, which can't even sign in now that sign-in is by phone.

**Plan:** keep membership mandatory, since issuing tokens without an organization is the riskier
default. Add a provisioning path that works as the production bootstrap *and* as the per-user
backfill:
`--provision-user <email> --phone <mobile> [--role <role>] [--first-name <x>] [--last-name <y>]`.
It creates the organization (with default settings) if none exists, ensures roles and permissions,
creates or updates the user, and attaches membership, role and (for Owner/Office admin) all-company
scope. Log a warning at startup when active users have no membership, so operators know to run it.

### 3. Count failed verification-code attempts — P1
`apps/api/Application/AuthService.cs:83-86`

`VerifyCode` (setup/reset pre-check) returns failure without incrementing `FailedAttempts`: unlimited
guesses for 10 minutes.

**Plan:** apply the same 5-attempt accounting as `Consume`; don't consume on success (the complete
step still needs the code).

### 4. Apply saved security policy values during authentication — P1
`apps/api/Domain/Organization.cs:187-191`

**Plan:** resolve the user's organization policy (via their active membership; defaults otherwise)
and apply it:
- `LockoutThreshold` / `LockoutMinutes` in `SignIn`.
- `AccessTokenMinutes` in `TokenIssuer.Access`; `RefreshTokenDays` for refresh-token expiry.
- `PinLength` as the **minimum** length for new/reset PINs (existing 4–8 digit PINs keep working at
  sign-in). The `invalid_pin` response carries the minimum so the client can explain it.
- Web proxy: set the `access` cookie lifetime from the JWT `exp`, and the `refresh` cookie to the
  policy maximum (90 days). The API still enforces the real expiry, and the proxy clears cookies
  when refresh fails.

Not enforced (no feature exists yet): password fields, `IdleUnlockSeconds` (client idle lock),
`AllowPinSignIn` (PIN is the only sign-in method; disabling it would lock everyone out).

### 5. Supersede pending schedules when postponing their start — P1
`apps/api/Domain/Setup/RecurringItem.cs:28-31`

**Plan:** for a not-yet-running item, the new version is effective from `min(today, newStart)`,
so it replaces the pending version from the edit date (and still allows backdating). Fix X3 at the
same time: judge "running" by the *current* version's start, not the earliest start ever recorded.

### 6. Refresh web sessions when the access token expires — P1
`apps/web/components/AppShell.tsx:45-50`

**Plan:** a shared `fetchWithSession` helper. On 401 it calls `/api/auth/refresh` once, sharing a
single in-flight refresh across concurrent requests, then retries. If refresh fails it raises a
`session-expired` event, and `AuthPanel` returns to sign-in with a message. `requestSetup` and the
session load both use it.

### 7. Add selectors for company and vehicle scopes — P2
`apps/web/components/PeopleAccessView.tsx:28`

**Plan:** new `GET /setup/access/scope-options` (requires `people.manage`) returning the companies
and vehicles within the caller's own scope. The person editor shows checkbox lists for the chosen
scope mode and blocks saving with an empty selection.

### 8. Map organization endpoint failures to client responses — P2
`apps/api/Api/OrganizationEndpoints.cs:13-16`

**Plan:** move the setup exception filter into one shared method and apply it to both route groups.

### 9. Require access-management permission for permission changes — P1
`apps/api/Application/AccessUseCases.cs:30`

**Plan:** in `Save`, if the resulting overrides or approval limit differ from what's stored (or from
role defaults, for a new person), require `access.manage`. Every *granted* override must also be a
permission the caller holds (no delegating what you don't have). Role assignment keeps working for
`people.manage`, with the Owner check unchanged. `access/roles` returns each role's default
permissions so the UI stops duplicating them (X4), and the editor disables permission toggles
without `access.manage`.

### 10. Deserialize camelCase settings with web JSON options — P1 — *Already fixed*
`apps/api/Api/OrganizationEndpoints.cs:34-36`

The working tree uses `JsonSerializerDefaults.Web`, and `tests/api/OrganizationSettingsTests.cs`
covers it.

### 11. Keep PIN-request responses indistinguishable — P1
`apps/api/Application/AuthService.cs:154-155`

**Plan:** `RequestPin` never returns `MaskedEmail`. The UI already falls back to "your registered
email". (`DevelopmentCode` still differs, but only in Development.)

### 12. Preserve support for existing 5–8 digit PINs — P1
`apps/web/components/PinInput.tsx:42-44`

**Plan:** restore `pattern="[0-9]{4,8}"`, `minLength 4`, `maxLength 8` on the PIN and confirm
fields; replace the "four-digit PIN" copy.

### 13. Remove fabricated financial figures from the mobile dashboard — P1 — *Deferred*
`apps/mobile/App.tsx:528-532`

Deferred: mobile is out of scope for this pass (web and API only).

### 14. Calculate vehicle report ranges from the current date — P2
`apps/web/components/SetupViews.tsx:422-423` (now `components/setup/VehiclesPage.tsx`)

**Plan:** the report endpoint accepts `period=week|month` as an alternative to `from`/`through`. The
server derives the range from the organization's business date and first day of the week, capped at
today. The UI requests the period and shows the returned range.

### 15. Honor the Remember this device selection — P2
`apps/web/components/AuthPanel.tsx:260-264`

**Plan:** implemented in the web proxy. New device ids start as session cookies. A trust-granting
call (`verify-device`, `*/complete`) with `rememberDevice: true` makes the device and refresh cookies
persistent (plus a `remember` marker so later refreshes keep them persistent). Otherwise they stay
session-only, so a restarted browser gets a new device id and must verify again. Existing cookies are
no longer re-extended on every call.

### 16. Split recurring allocations in whole currency cents — P2 — *Already fixed*
`apps/web/components/RecurringEditor.tsx:43-45`

The working tree's `splitAmountEvenly` works in cents and distributes the remainder.

### 17. Expose personal preferences to every active member — P2
`apps/web/components/AppShell.tsx:66-68`

**Plan:** move the preferences form into a `PreferencesView` reachable from the user menu
("Your preferences") for every member. Organization settings keeps only organization sections.

### 18. Avoid requiring vehicle-management access to view commitments — P2
`apps/web/components/SetupViews.tsx:657-660` (now `components/setup/RecurringPage.tsx`)

**Plan:** `RecurringDto` allocations include the vehicle registration, so the list needs no vehicle
call. Add `GET /setup/recurring/vehicle-options` (requires `commitments.manage`) for the editor's
picker. The page loads that only when the user can manage, and a failure there doesn't blank the
list.

### 19. Preserve the 254 country prefix during normalization — P1
`apps/api/Domain/PhoneNumber.cs:11`

**Plan:** `"+" + digits`. Add unit tests for `07…`, `01…`, `254…`, `+254…`, and spaced/dashed input.

### 20. Resend device codes without submitting an empty PIN — P1
`apps/web/components/AuthPanel.tsx:312-314`

**Plan:** keep the PIN that produced the challenge in a ref (not rendered, cleared on navigation or
success) and resend with it. The account-level resend cooldown still applies server-side.

### 21. Restrict weekly recurrence input to weekdays — P2 — *Already fixed*
`apps/web/components/RecurringEditor.tsx:107`

The working tree renders a Monday–Sunday select mapped to `DayOfWeek` 0–6.

### 22. Preserve assigned permissions for inactive people — P2
`apps/api/Application/AccessUseCases.cs:115-117`

**Plan:** the people projection resolves *assigned* permissions (ignoring active state).
Enforcement for inactive members is unchanged (`OrganizationRepository`, token issuance).

### 23. Backfill the target when moving a vehicle join date earlier — P2
`apps/api/Domain/Setup/FleetVehicle.cs:45-49`

**Plan:** when `JoinedOn` moves earlier and no target covers the new date, append a target at the new
join date carrying the amount that applied at the old join date.

### 24. Store the required reason in the organization audit event — P2
`apps/api/Api/OrganizationEndpoints.cs:39`

**Plan:** record organization settings changes in the versioned settings history (which has
`Reason` and shows in the change log), and audit them as `{ value, reason }`.

---

## Verification (2026-09-26)

- **API:** 61 tests, 59 pass. The 2 failures are pre-existing environment tests (see follow-ups).
  30 new tests cover #1–#5, #7–#9, #11, #14, #18, #19, #22–#24 and X1–X3.
- **Web:** 30 tests pass, 16 of them new or updated, covering #4, #6, #7, #9, #12, #15, #17, #18,
  #20, X2, X4, X5 and X6. `tsc --noEmit` is clean and `next build` succeeds.
- **Shared:** 22 tests pass (1 new, for the policy-aware PIN message).
- **Startup:** the API was run against the local dev database: the history row was renamed, the
  migration was not re-run, and `/health` is ok.

## Follow-ups (not done in this pass)

- **Lint:** `npm run lint` now runs and reports 20 pre-existing problems (17 errors, 3 warnings):
  `react-hooks/set-state-in-effect` in the setup pages' load effects, unused variables in
  `RecurringEditor` and `PeopleAccessView`, `prefer-const` in `recurringPresentation.ts`, and 4
  `no-require-imports` in mobile. `eslint-plugin-react` (7.37.5, bundled by `eslint-config-next`)
  officially supports ESLint up to 9.7. It runs under ESLint 10 once the React version is pinned in
  `eslint.config.mjs`. If a rule crashes later, drop to ESLint 9.
- **SQL Server tests:** `SqlServerMigrationsApplyWhenCiProvidesServer` needs
  `SQLSERVER_TEST_CONNECTION` (CI only). `SqlServerDriverCanInitializeInConfiguredRuntime` fails on
  Windows because `Auth.Tests.csproj` sets `InvariantGlobalization`, which also stops IANA time
  zones (e.g. `Africa/Nairobi`) resolving on Windows. Test organizations therefore use UTC.
- **Security policy fields with no feature behind them:** password rules, `IdleUnlockSeconds` and
  `AllowPinSignIn` are stored but not enforced (see #4). Consider hiding them in the settings UI
  until they do something.
- **Scope assignment:** the new scope options mirror the existing server rule, under which an admin
  scoped to *companies* can't assign *vehicle* scopes, even for vehicles in their companies. That
  rule may be worth relaxing.
- **Mobile:** #13, and `test-renderer` moved from 1.2.0 to the declared 1.3.0 in the lockfile during
  the ESLint install.
- **Stacked branches:** auth and access findings were fixed on `settings`. If `auth`/`access` merge
  separately, carry these fixes back or merge this branch after them.
