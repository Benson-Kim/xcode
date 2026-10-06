# Phase 6 — Maintainability, CI & tooling (prompt 6)

Implement Phase 6 of the Revenue App Remediation Plan completely. The repository must end up easier to validate automatically, not merely cleaner-looking.

## Start here
1. Read CLAUDE.md (commands, shared-tree rules, known traps, evidence standard), `.claude/remediation/README.md` (status, residuals) and `.claude/remediation/findings/phase-5-6.md` (verified findings with file:line; re-verify before relying on them). The original audit details are in `.claude/remediation/audit/maintainability.md` and `extensibility.md`.
2. Run `git status` and check recent file times; another phase may be running in this tree. Record a baseline of the full validation path from CLAUDE.md before changing anything.
3. Make a checklist with one row per clause below. Delegate:
   - routine slices to `remediation-sonnet`, with at most two helpers and disjoint files;
   - the AuthFlow reducer and the `useGroupping` contract migration to `remediation-opus` only if they meet the gate.

## Items

1. **CI.**
   - Add a pull-request pipeline with a reproducible install (`npm ci`; restore from lock files), lint, all three typechecks (shared, web, mobile), shared/web tests, mobile jest, and `dotnet restore/build/test`.
   - `SqlServerTests` fails by assertion (it does not skip) without `SQLSERVER_TEST_CONNECTION`. Give CI a SQL Server service container and set the variable, so migrations are proven. Everywhere else, filter with `Category!=SqlServer`.
   - Root `lint` already exists. Add root `test`, `typecheck` and `format:check` scripts that run exactly what CI runs.
   - Add production Dockerfiles for the API and web if they are still missing.
   - Deployment must use the API's explicit `--migrate` mode (Program.cs), never startup migration.
   - The API suite takes 7–12 minutes, so give it its own job.
   - The remote is GitHub (`Benson-Kim/xcode`), so use GitHub Actions; `.gitlab/` holds only a Duo agent config.
2. **Module boundaries.**
   - Use `no-restricted-imports` (or the custom rule in `eslint-rules/`) to forbid: web↔mobile imports; deep imports of `@xcode/shared/src/*`; React, React Native or Next inside `packages/shared`.
   - Existing legitimate imports must pass.
   - Prove each rule with a lint fixture or test, not just config.
3. **AuthFlow.**
   - Turn `apps/mobile/src/auth/AuthFlow.tsx`'s implicit state machine into a reducer or discriminated union plus focused hooks, so invalid states cannot be represented.
   - Remove the exhaustive-deps workarounds by fixing state and effect ownership.
   - Clear PIN refs and state after success, cancellation or flow switch.
   - Preserve the Phase 1 fixes:
     - a failed person fetch keeps the user on the current step with a visible error, on the pad AND the code step;
     - the busy/completing guard covers the whole setup, reset, sign-in and offline-unlock operation;
     - the offline PIN check uses `src/lib/pbkdf2.ts` (no WebCrypto on phones).
   - Also fix the known gap. After a profile-load failure that follows `verify-device`, `setup-pin/complete` or `pin-reset/complete`, retrying replays a consumed code. Send the person to the PIN pad with a clear message instead.
   - Handle every auth status explicitly, because AuthFlow currently falls through silently on unexpected statuses.
4. **Large components.**
   - Split RevenueScreen (mobile), RecurringEditor, PeopleAccessView and RevenuePage (web) into coherent hooks, components and modules, not one-function files.
   - Add a `max-lines-per-function` warning (or equivalent) at a level the split code meets.
   - Keep `useFormats()` usage: components read the formatter from context, and helpers take it as an argument.
5. **Shared test coverage.**
   - Add table-driven tests in `packages/shared/tests` for `createFormatter` (kes, money, firstDayOfWeek, dates), percentText, maskPhone, initials, ordinal, safeTimeZone, revenuePeriodLabel and the auth client's headers, with edge cases.
   - Add vitest coverage thresholds for the shared package.
   - `safeTimeZone` is not exported. Test it through `createFormatter` and `formatTimestamp`, or export it deliberately.
   - Then delete the app duplicates. The only ones are the two `percentText` tests (`apps/web/tests/format.test.ts`, `apps/mobile/tests/format.test.ts`).
6. **Formatter and `useGroupping`.**
   - Adopt Prettier with `format:check`. Prettier is entirely absent today, and 101 of 140 TS files have lines over 100 columns, so the reformat touches most files. Do it as its own format-only commit, separate from logic changes.
   - The `useGroupping` typo is a contract, not a rename. It lives in:
     - the C# property `OrganizationLocalization.UseGroupping`, a database column created in migration `20260924172309_OrganizationsAndFleet`;
     - the settings JSON and its labels in `OrganizationEndpoints`;
     - the shared `Formats` type, web and mobile code and tests;
     - the phone's cached appearance JSON in secure store (`xcode.appearance`).
   - Stored change-log snapshots need no compatibility read. The real risks are:
     - the phone's cached appearance;
     - installed phones and open web tabs that still PUT `useGroupping`, which `Save<T>` would silently drop.
   - The fix needs an EF migration (`RenameColumn`), API, shared, web and mobile renames, the API accepting both names during a transition, and reading the old key from stored phone data.
   - Prove each with a test.
7. **Component correctness and accessibility.**
   - Fix the Dialog double `onClose`, the Toast timer reset, and the ErrorText/ChoiceField accessibility gaps the findings name, on web and mobile as applicable.
   - Adding `role="alert"` to ErrorText can break tests that expect a single alert (e.g. `AuthPanel.test.tsx`). Adjust those deliberately.
   - Add regression tests.
8. **Web test infrastructure.**
   - Add a reusable fake-API helper for web tests, mirroring `apps/mobile/tests/fakeApi.ts`'s style.
   - Add negative-path tests (409, 403, offline/transient 503) for the settings and people flows.
9. **Toolchain.**
   - Align TypeScript versions across workspaces where feasible; `packages/shared` declares `typescript ^7`, so check web and mobile.
   - Declare `eslint-plugin-react-hooks` explicitly if it is used.
   - Document or resolve the React version split instead of relying on hoisting.
   - Verify the lock file is consistent (`npm ci` from clean).
10. **Design tokens.**
    - Make `@xcode/shared/tokens.ts`, framework-free, the canonical source.
    - Derive the web CSS custom properties and the mobile palette from it.
    - Delete the divergent copies.
    - The palettes already disagree (mobile light `blueTint`/`blueWash` hold web's `blue-soft`/`blue-tint` values), and no parity test exists. Reconcile them deliberately, and add a test that both apps derive from the same tokens.

## Done means
- All ten items are implemented with evidence (file + symbol + a test or CI step that fails without it).
- The documented local command path (root scripts) runs the same checks as CI, and you have run it.
- A `remediation-auditor` pass over the ten items reports no PARTIAL. Fix whatever it finds.
- Do not mark CI done because a YAML file exists. Every script it calls must work.
- Update `.claude/remediation/README.md` and the `remediation-program` memory.

End with:
- a ten-item matrix;
- the CI jobs and checks created;
- local commands with exact results;
- the files changed;
- any CI secret or platform configuration that can't be created from the repository.
