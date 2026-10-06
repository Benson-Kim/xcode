MAINTAINABILITY REVIEW: revenue monorepo
(Paths are relative to C:\Users\user\Documents\Coding\PrioriTech\xcode-wt\revenue. Line numbers are approximate. I read all of packages/shared, both UI libraries, AuthFlow, steps.tsx, the test helpers and the lint config. I sampled the web, mobile and API tests rather than reading every one. Function-length figures come from a rough script that counts to the next top-level function, so treat them as upper bounds.)

SUMMARY
- The code is readable, well commented and consistently ordered. The shared package split is mostly clean, and no app imports the other.
- The main risks are:
  - Giant components with implicit state machines.
  - No module-boundary lint and no CI.
  - A mutable global in the shared package, set during render.
  - Thin test coverage on shared logic.
  - Tests duplicated across apps.
  - Several accessibility and UI-lib API gaps.

## 1. TEST QUALITY AND COVERAGE

T1 [HIGH] packages/shared/tests/*.ts: large untested areas in the shared logic.
- Never tested: kes, money, percentText's boundary at the source, plural, maskPhone, initials, ordinal.
- Also never tested: safeTimeZone's fallback for an invalid time zone, firstDayOfWeek's invalid-input fallback, revenuePeriodLabel.
- Also never tested: createAuthClient's Authorization header and non-JSON body fallback.
- Also never tested: formatTimestamp across midnight and day boundaries, and DST-free zones other than UTC and Nairobi.
- Recommendation: add table-driven tests for each. Add vitest coverage thresholds for packages/shared. It is the single source of truth for money, dates and PINs.

T2 [HIGH] packages/shared/tests/dates.test.ts:~12 asserts `isDate("2024-02-30") === true`.
- This pins lax validation as correct. `calendarDate("2024-02-30")` silently rolls to 1 March.
- Anything that trusts isDate for data integrity (mobile queue, week parsing) accepts impossible dates.
- Recommendation: make isDate round-trip validate, then flip the test to assert false. If the leniency is deliberate, rename the function (isDateShape) and document it.

T3 [MEDIUM] Duplicated tests across apps.
- apps/web/tests/format.test.ts and apps/mobile/tests/format.test.ts are byte-identical tests of `@xcode/shared/format#percentText`.
- That function has no test in packages/shared/tests/format.test.ts, so the real unit has no coverage of its own.
- Recommendation: move the tests to the shared package and delete both copies.

T4 [MEDIUM] Mixed import style in shared tests.
- auth.test.ts imports "@xcode/shared/auth" (the public entry point).
- dates, format and revenue tests import "../src/..." (internals).
- Recommendation: pick one. Use the package name, so the `exports` map is exercised too.

T5 [MEDIUM] Web tests have no shared fetch fake; mobile has one.
- Mobile has tests/fakeApi.ts, a route-based fake that records calls.
- Web tests each hand-roll `vi.stubGlobal("fetch", vi.fn().mockImplementation(...))` (e.g. OrganizationSettingsView.test.tsx:~50, AuthPanel, PreferencesView, session). The routing logic is duplicated and brittle.
- Fixtures are also duplicated: `appearance(...)` in Theme.test.tsx and `appearanceFixture` in renderInApp.tsx are near copies, and the settings fixture is inlined.
- Recommendation: add apps/web/tests/fakeApi.ts mirroring mobile's. Reuse appearanceFixture.

T6 [MEDIUM] Negative paths are thin on the web.
- Error, rejection and offline keyword hits per file are 0 to 1 in PreferencesView, OrganizationSettingsView, ScheduledTotals, Streaming, Theme, VehicleReport, VehicleInvestment, StaleSelections and RecurringScope.
- Settings saves are only tested on success (PUT always returns 200). There is no 409 version-conflict test, no 403, no network failure and no timeout.
- By contrast, mobile queue.test.ts, auth.test.tsx and revenue.test.tsx cover errors well.
- Recommendation: add a failure case per mutating view (save rejected, version conflict, offline), mirroring what mobile does.

T7 [MEDIUM] Brittle and implementation-coupled assertions.
- OrganizationSettingsView.test.tsx asserts the exact fetch URL "/api/setup/organization/settings".
- Theme.test.tsx asserts literal `color-mix(in srgb, #0B5CAD 80%, black)` strings. That is a change-detector test for the CSS formula.
- Mobile tests/setup.ts mocks a hash with a 31-multiplier stand-in.
- Many tests assert multiple behaviors (long scenario tests). The API test OrganizationAndLocalizationSettingsPersistCamelCaseValues does PUT invalid, PUT ok, PUT ok and GET in one `[Fact]` with no Arrange/Act/Assert separation.
- Recommendation: assert on user-visible outcomes and a captured request body. Keep the CSS-token assertions only where the formula is the contract. Split the multi-act tests.

T8 [LOW] Test setup hacks in mobile.
- apps/mobile/tests/setup.ts:~50-70 does a global warm-up render in beforeAll with a 120s timeout, plus 10s asyncUtilTimeout and 15s testTimeout. This masks slowness rather than fixing it.
- `--runInBand` is mandatory.
- Web: vitest testTimeout is 20000, so hangs are slow to surface. There are no fake timers outside 5 files, and `waitFor` is heavy (21 in RevenuePage.test).
- Recommendation: document why. Revisit when Expo or jest-expo caches improve.

T9 [LOW] The API test project is named Auth.Tests, namespace Auth.*, in a product called XCODE.
- Files such as Phase1ContractTests mix concerns. SqlServerTests and the MigrationSnapshot tests are slow integration tests with no trait or category.
- Recommendation: add `[Trait]` categories (unit/integration) so CI can split them.

T10 [LOW] Helpers.
- renderInApp.tsx is good: it provides Session, Appearance and Toast providers. It does not wrap a Router or QueryClient, if those exist.
- mobile/tests/helpers.tsx `storedText()` reaches into mock internals via require, and `as StoredPerson` casts hide schema drift.

No coverage tooling: there is no vitest `coverage` config and no jest `collectCoverage`, so gaps cannot be measured.

## 2. CODE CONSISTENCY

C1 [MEDIUM] "useGroupping" is a typo that has leaked into the API contract.
- It appears in packages/shared/src/format.ts (Formats), the web/mobile fixtures and the API settings (OrganizationSettingsTests.cs: `useGroupping = false`).
- Renaming now is a breaking change. Do it before more clients depend on it, or alias it.

C2 [MEDIUM] No formatter.
- There is an .editorconfig but no Prettier or equivalent.
- Formatting is visibly inconsistent: apps/web/components/ui/layout.tsx, feedback.tsx and dialog.tsx use long single lines, while button.tsx, form.tsx and table.tsx are wrapped at 80 columns.
- apps/mobile/src/ui/index.ts has a missing trailing comma after `type Theme`. Tests and shared use mixed wrapping.
- The branch is `fix/format`, so formatting churn is already hurting diffs.
- Recommendation: adopt Prettier (or Biome) and a `format:check` script.

C3 [LOW] File naming is mixed across the apps.
- Web ui/: lowercase (button.tsx, form.tsx, with cn.ts).
- Web components: PascalCase views plus camelCase helpers (revenueFormat.ts, recurringPresentation.ts).
- Mobile ui/: PascalCase (Button.tsx, Brand.tsx).
- Mobile src: camelCase (appearance.ts, session.ts).
- Web tests are PascalCase for components and camelCase for logic. That is defensible but undocumented.
- Mobile shell/screens.tsx and parts.tsx are vague bucket names.

C4 [LOW] Near-duplicate date wrappers with diverging behavior.
- apps/web/components/revenueFormat.ts (shortDate, longDate, rangeLabel) and apps/mobile/src/revenue/dates.ts (dayLabel, longDayLabel, rangeLabel) wrap the same shared helpers under different names.
- Web honors the organization's datePattern via formatDate. Mobile's dayLabel is hardcoded to the medium pattern.
- Mobile therefore ignores the "short" and "long" settings. This is a functional inconsistency, not just a naming one.
- Recommendation: move the revenue date helpers into shared and give them one name.

C5 [LOW] revenueFormat.ts `figure()` does `kes(value).slice(currencyCode().length + 1)`.
- This is fragile string surgery. It breaks if the locale or currency pattern ever changes. Expose a formatter in shared instead.

C6 [LOW] Import-style notes.
- All shared imports use sub-path entry points ("@xcode/shared/format", "/dates", "/auth", "/revenue"). Nothing imports the root barrel and nothing imports shared/src directly. This is consistent and good.
- The only deviation is the shared tests (T4).
- Export maps are ES source with `main` and `types` pointing to .ts. This is acceptable for a private workspace, but it forces every consumer to transpile (Next uses transpilePackages, Metro handles it natively).

C7 [LOW] eslint-rules/import-order.mjs.
- It is untracked in git (new). It has no tests.
- It sorts with `localeCompare`, which is locale- and ICU-dependent and may order differently on CI than on a dev machine. Use a plain `<` comparison or `Intl.Collator("en")`.
- It silently skips the file if any comment sits between imports (the `/\/\/|\/\*/` gap check), so reorder fixes just do not run.
- It treats `react`, `next/*`, `react-native` and `@/*` aliases all as group 0.
- It does not apply to packages/shared (its files are not in the `files` glob) or to the eslint-rules directory.
- It is the only auto-fix import rule. A mature plugin (`eslint-plugin-import` or `simple-import-sort`) would carry less maintenance cost.

## 3. COMPLEXITY

X1 [HIGH] apps/mobile/src/auth/AuthFlow.tsx:44-653 is one ~600-line component with an implicit state machine.
- It has about 24 `useState` calls and 4 `useRef` calls.
- Three overlapping enums (Step x Mode x Flow = 4x4x3 = 48 combos) are tracked in separate states. Only some combinations are valid and nothing enforces which.
- Many handlers call one another: complete -> checkPin -> signedIn, and openPad, pause and showCode all mutate multiple states.
- Wrong-PIN counting is duplicated in two places with different storage:
  - wrongPin() uses in-memory `pinTries.current[phone]`.
  - unlockOffline() uses persisted `loadOfflineTries`.
  - Both format `${left} ${left === 1 ? "try" : "tries"} left` verbatim; code tries has a third copy.
- Two `eslint-disable react-hooks/exhaustive-deps` lines (:119 and :127) sit under a lint config that sets the rule to "error". They hide stale closures: the pause tick calls openPad and trustedHere captured at the time the effect ran.
- The `setTimeout(..., 180)` at :248 is not cleared on unmount, so state can be set after unmount.
- Behavior gaps:
  - In checkPin(), a result with a status other than authenticated or verification_required falls through silently (busy resets, nothing shown).
  - savePin() has the same gap.
  - `failure()` re-implements the 429 text that AuthError already produces (shared/src/auth.ts).
- Recommendation: model it as a reducer or discriminated-union state (`{step:'pad', mode, ...}`) with a `useAuthFlow` hook. Split the pad, code and paused logic into hooks. Centralize the PIN-attempt and lockout policy in one module with unit tests. The existing auth.test.tsx (17 tests) is the safety net for that refactor.

X2 [HIGH] apps/mobile/src/shell/RevenueScreen.tsx is 1626 lines.
- RevenueScreen ~450 lines (183-630), CaptureSheet ~410, VehicleWeek ~260, QueuePanel ~155, `rowShell` ~155.
- It uses 20 `useState` calls and has another exhaustive-deps disable at :256 with a coupled-effect "attempt" counter.
- Recommendation: split into a folder: week fetch/retry hook, queue panel, capture sheet and week grid, each in its own file.

X3 [MEDIUM] Web components are also very large.
- RecurringEditor.tsx ~1030 lines with 23 `useState` calls (RecurringEditor ~900 lines).
- PeopleAccessView.tsx 1011 lines (PersonEditor ~650).
- OrganizationSettingsView.tsx 781 lines (SettingsForm ~575).
- AppShell.tsx 866 lines; AuthPanel.tsx 548 lines; VehiclesPage.tsx 736 lines.
- RevenuePage.tsx 820 lines; VehicleEditor ~360.
- Also: mobile queue.ts `openQueue` ~300 lines, and web `app/api/auth/[...path]/route.ts` POST ~135 lines.
- Recommendation: extract sections as subcomponents, extract form state into `useReducer` or a form hook, and set an eslint `max-lines-per-function` warning (~120) to stop further growth.

X4 [MEDIUM] Nested ternaries and unnamed booleans.
- packages/shared/src/auth.ts AuthError constructor has a 4-deep nested ternary building the message.
- AuthFlow.tsx:~550 header title/sub has nested ternaries across mode and flow.
- AuthFlow.tsx:~590 the `label` is a nested ternary, and `links` is a 3-way ternary containing a nested conditional chain.
- Unnamed predicates: `flow === "reset" && trustedHere && (await matchesPinCheck(entered))`, and the `longPin || next.length < pinLength` and `mode === "enter" && !known && pinLength === 4` conditions.
- `pinLength > 4`, `"123456789".slice(0, pinLength)` and `pinLength === 4 ? "four" : pinLength` are magic numbers and inline copy generation.
- Recommendation: lookup tables, such as a message map keyed by status, plus named predicates (isLongPinEntry, canSwitchToLongPin).

X5 [LOW] packages/shared/src/format.ts uses non-null assertions (`first! >= 0 && first! <= 6`) despite the already-narrowed number type.
- shared/auth.ts: `pinHelp(minimumLength = 4)` duplicates PIN_HELP's wording, and `validatePin` ignores the organization's minimum length entirely (only `pinHelp` reflects it).
- The result is the "4-8 digits" constant in two places, so org-specific minimum is enforced only by the API round trip. On mobile that surfaces late, in `savePin`'s invalid_pin branch.

X6 [LOW] A module-level mutable singleton in packages/shared/src/format.ts (`let formats`), set via `configureFormats`.
- It is called during render in apps/web/components/AppShell.tsx:297 and apps/mobile/App.tsx:139, so every re-render writes a global. Components read it by calling `kes()` and similar functions, so they will not re-render on a format change except by accident.
- If any code path runs on the Next.js server, the global leaks across requests.
- Tests need `afterEach(() => configureFormats(null))` (shared/tests/format.test.ts) to avoid cross-test bleed.
- Recommendation: use a React context with formatter factories (`createFormatters(formats)`), or at minimum set it in an effect with a version tick that forces consumers to re-render.

## 4. DEPENDENCY HEALTH

D1 [MEDIUM] TypeScript is split, and the split looks deliberate but is undocumented and fragile.
- package-lock: apps/web and packages/shared install typescript 7.0.2; apps/mobile (~6.0.3) and the hoisted root copy are 6.0.3.
- typescript-eslint 8.70.1 declares peer `typescript >=4.8.4 <6.1.0`. Lint resolves the hoisted 6.0.3, so lint is fine, but web and shared are type-checked by 7.x while linted against 6.x parsing.
- Anything that relies on 7-only behavior (or a 6-only API) passes `typecheck` but may fail in lint, or the reverse.
- Recommendation: either pin all workspaces to one version or document the split. Add a CI step that runs `tsc` in each workspace plus eslint. Move `typescript` to a root devDependency with an `overrides` entry.

D2 [MEDIUM] Two React versions.
- Web has 19.3.0 (and @types/react 19.3.0). Mobile has 19.2.3 (@types 19.2.18), both installed in separate node_modules (apps/mobile/node_modules/react).
- apps/mobile/metro.config.cjs works around the hoisting with a custom `resolveRequest` that re-roots react and react-dom to the mobile package. apps/mobile/jest.config.cjs does the same via `moduleNameMapper`.
- This is fragile: any new tool that resolves react from the root silently gets the wrong copy, causing "invalid hook call" errors.
- Shared has no React dependency, so it is safe today. Keep it free of React imports.
- Recommendation: document the constraint in the README, and add a check script that fails if shared imports react.

D3 [MEDIUM] Phantom dependency: eslint.config.mjs imports `eslint-plugin-react-hooks` and `typescript-eslint`.
- `eslint-plugin-react-hooks` is not listed in any package.json. It only resolves because eslint-config-next (^16.3.6) pulls it in (7.1.1 installed).
- Recommendation: add it explicitly to the root devDependencies.

D4 [LOW] There are no peer-dependency problems at install time.
- Vitest 5.0.1 peers (jsdom "*", vite ^8) are satisfied. The jest 29.7 plus @types/jest 29.5.14 pins are consistent. Expo 57 packages use `~` ranges as expected.
- `@types/node ^22.20.4` is declared in web but engines require node >=22.23.3. This is fine.
- Mobile mixes `^`, `~` and exact pins: react-native-svg 15.15.4, react 19.2.3, @types/jest 29.5.14.
- Recommendation: let `npx expo install --check` own the Expo-managed ranges.

D5 [LOW] Missing repository tooling.
- There is no .github (no CI), and no Dependabot or Renovate config.
- The root package.json has no `test`, `typecheck`, `lint:fix` or `test:mobile` aggregate scripts, so `npm test` at the root does nothing. It only has test:shared and test:web, and mobile has no root alias at all. There is no .nvmrc, no .gitattributes and no Prettier.
- apps/web/tsconfig.tsbuildinfo is tracked in git (it should be ignored).
- docs/reports contains large PDFs checked in.
- README.md says "Bootstrap in progress" and documents only the web server settings. There are no instructions for running the API, web or mobile apps, or the tests.
- Recommendation: add CI (lint, three TS typechecks, vitest, jest, dotnet test), a root `test` and `typecheck`, a real README and ignore build artifacts.

## 5. MODULE BOUNDARIES

B1 [HIGH] eslint.config.mjs has no boundary enforcement.
- There is no `no-restricted-imports` or `no-restricted-paths` rule, so nothing prevents web from importing mobile (or the reverse), or either app from reaching into packages/shared/src/* directly.
- Today the code is clean. I grepped and found no cross-app imports, no `@xcode/web` or `@xcode/mobile` references, and no deep shared imports.
- That is held up only by convention. Recommendation: add:
  - `no-restricted-imports` patterns for `@xcode/shared/src/*`, `**/apps/mobile/**` (in web), and `**/apps/web/**` (in mobile).
  - A restriction that forbids shared from importing react, react-native or next (see D2).
  - A shared-package-only rule against `Date.now()`/`window`.

B2 [MEDIUM] packages/shared/package.json.
- The `exports` map is good and explicit (".", "./auth", "./dates", "./format", "./revenue"), and apps use the right entry points.
- Missing: `"sideEffects": false`. `format.ts` holds mutable global state (X6), so tree-shaking assumptions are wrong either way.
- The `types` field points at .ts source, and there is no vitest config in shared (it relies on defaults).
- `build` is just `tsc --noEmit`, so it does not build anything.
- Recommendation: rename `build` to `typecheck`.

B3 [LOW] UI libraries sit inside the apps (apps/web/components/ui, apps/mobile/src/ui) with duplicated concepts and different APIs.
- The web ui/form.tsx imports `currencyCode` from @xcode/shared/format, which couples the generic UI layer to the global format state.
- Recommendation: keep ui/ free of shared domain imports. Pass `currency` in as a prop.

B4 [LOW] eslint.config.mjs applies `react-hooks` plugin rules to mobile only; the web app gets them through the Next config. `react-hooks/exhaustive-deps` is "error", but there are three eslint-disable lines for it in mobile (see X1, X2).
- The `settings.react.version: "19.3"` hardcode in the config must be bumped by hand with React.
- A fully ignored `design/**` is fine.
- No test files get any additional lint (for example `no-focused-tests`), and `@typescript-eslint/no-require-imports` is off for all mobile tests.

## 6. UI COMPONENT LIBRARIES

U1 [MEDIUM] apps/web/components/ui/dialog.tsx:~29-30 fires `onClose` twice on Escape.
- It binds both `onClose={onClose}` and `onCancel={onClose}`. Escape raises `cancel` and then `close`. The consumer's close handler therefore runs twice, as does the close button when the effect then calls `dialog.close()`.
- There is also a production fallback for `typeof dialog.showModal === "function"` that exists only for jsdom; the code carries test environment concerns.
- Recommendation: use onClose only (the native close event covers Escape too), or guard it.

U2 [MEDIUM] apps/web/components/ui/toast.tsx has a timer-reset bug.
- `ToastMessage` runs `useEffect(() => { setTimeout(onDone, 4000) }, [onDone])`, but `onDone` is an inline closure created on every ToastProvider render.
- Each new toast re-renders the provider, so every existing toast's 4-second timer restarts. Rapid saves keep older toasts alive.
- There is no live region on the container, and each toast has its own `role="status"` (acceptable).
- `useToast()` defaults to a silent no-op context, so a missing provider hides bugs.
- Recommendation: use stable `onDone` (`useCallback` on the id) or keep timers in the provider. Throw if no provider exists.

U3 [MEDIUM] Web accessibility gaps.
- `ErrorText` (form.tsx) has no `role` or `aria-live`, so errors that appear after validation are not announced. The ErrorSummary Banner does carry `role="alert"`.
- `ChoiceField` gives the group no `aria-describedby` for its hint and error, and its ErrorText has no id (Field handles this correctly; ChoiceField does not).
- `Tabs`: `tabpanel` has no `tabIndex={0}`, and the panel is shared by all tabs (acceptable). `aria-controls` points to a panel that always exists.
- `ColorInput` text field has no label of its own beyond the surrounding Field. `Spacer` is fine (aria-hidden).
- `SegmentedControl` uses `aria-pressed` buttons in a role="group" (ok), but is missing arrow-key navigation.
- `Skeleton`: `role="status" aria-busy aria-live` on the wrapper is fine.
- Good practices found: icon buttons require an `aria-label` in use (Close), `aria-invalid` is auto-wired via useFieldProps, and DataTable has an sr-only caption while loading.

U4 [MEDIUM] Inconsistent component API in web ui/.
- Button takes `tone` with 6 values, but `CardAction` takes `primary: boolean` and duplicates Button's pill styling (button.tsx, end of file).
- Chip, LinkButton, RowButton and IconButton each re-implement `type="button"` defaulting and cn merging. A shared base would remove ~5 copies.
- The `DENSITY` prop exists on TextInput, SelectInput and CurrencyInput but not ColorInput (hardcoded `h-12 w-14`).
- Comment typos and stubs: button.tsx has "// pill button ." and several one-line comments referencing legacy design class names (`.btn-pill`, `.toolbar`).
- `ui/index.ts` is a barrel of `export *` mixing server-safe and "use client" modules (dialog, form, toast). It also exports cn publicly.
- Naming collision risk: `Field` exists in both the web and mobile UI libraries with different props (id/label/hint/action vs label/error/digits), and `Button` takes ReactNode children on web but `children: string` on mobile.

U5 [MEDIUM] Mobile UI library.
- Button.tsx: no `accessibilityLabel`/`accessibilityHint` pass-through, and `children` must be a string.
  - There is no `tone` beyond primary/outline, while web has 6.
  - LinkButton lacks `accessibilityState.busy` and the `style` prop.
- Field.tsx:
  - The label is a separate Text, linked only through `accessibilityLabel`.
  - The error is not associated with the input (no accessibilityHint/`aria-describedby` equivalent).
  - `outlineColor: ${colors.blue}59` appends alpha hex to a 6-digit hex string. It silently breaks if the brand colour is ever 3- or 8-digit hex or `rgb()` (mix() output).
  - `digits` mode hardcodes `fontSize: 22` and `letterSpacing: 8`.
- Feedback.tsx: ErrorText uses `accessibilityLiveRegion="polite"` plus role alert (contradictory; alert implies assertive). Banner "offline" has no role, while web gives it role="status" (inconsistent).
- Text.tsx scales `fontSize`/`lineHeight` by the user's fontScale but multiplies after flatten. The base default 16/23 plus any style override then scales on top of the OS font scale unless `allowFontScaling={false}` is set. Verify this does not double-scale.
- theme.tsx: the palette is duplicated between mobile (palette/darkPalette) and web CSS tokens (globals.css). A comment says "kept in step with :root[data-theme=dark]", i.e. manual sync.
- Recommendation: move the palette to shared as a token source, and generate the CSS custom properties from it.

U6 [LOW] Demo credentials in source.
- apps/mobile/src/auth/steps.tsx:~30 hardcodes demo phone numbers and PINs (`DEMO_LOGINS`) in a `__DEV__` block. They are dev-only, but they live in a source file.
- Recommendation: move them to a seed doc or dev config so a PIN never ships in the bundle source.

## TOP RECOMMENDATIONS, IN ORDER
1. Add CI, root `test`/`typecheck`/`format:check` scripts, and a real README. (D5)
2. Add boundary lint rules with `no-restricted-imports`. (B1)
3. Refactor AuthFlow into a reducer/hook set, with the existing tests as the safety net; fix the unhandled statuses and the unmounted-timer setState. (X1)
4. Split RevenueScreen.tsx and the 1000-line web components; add a `max-lines-per-function` warning. (X2, X3)
5. Replace the `configureFormats` global with context, or at least stop calling it during render. (X6)
6. Add shared-package tests for money/percent/plural/phone/time-zone fallback and the auth client headers; fix `isDate` leniency; delete the duplicate format tests. (T1-T3)
7. Fix the Dialog double-onClose and the Toast timer reset; add `role="alert"` to ErrorText. (U1-U3)
8. Add web fake-API helper plus negative-path tests (409/403/offline) for the settings and people views. (T5, T6)
9. Adopt Prettier; fix the `useGroupping` typo before more clients depend on it. (C1, C2)
10. Document the TS 6/7 and React 19.2/19.3 splits, and declare `eslint-plugin-react-hooks` as a dependency. (D1-D3)

Key files:
- eslint.config.mjs
- eslint-rules/import-order.mjs
- packages/shared/src/format.ts
- packages/shared/src/auth.ts
- packages/shared/src/dates.ts
- packages/shared/tests/dates.test.ts
- apps/mobile/src/auth/AuthFlow.tsx
- apps/mobile/src/shell/RevenueScreen.tsx
- apps/web/components/ui/dialog.tsx
- apps/web/components/ui/toast.tsx
- apps/web/components/ui/form.tsx
- apps/mobile/src/ui/Field.tsx
- apps/mobile/metro.config.cjs
- apps/web/tests/renderInApp.tsx
- apps/mobile/tests/helpers.tsx