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
   - Run `SqlServerTests` against a SQL Server service container with `SQLSERVER_TEST_CONNECTION`, so migrations are proven in CI. Locally the category is filtered out.
   - Add root scripts `test`, `typecheck` and `format:check` (and `lint` if missing) that run exactly what CI runs.
   - Add production Dockerfiles for the API and web if they are still missing.
   - Deployment must use the explicit migration step from Phase 3 (the API's `--migrate` mode or bundle), never startup migration.
   - The API suite takes 10–12 minutes, so give it its own job.
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
   - Also fix the known gap: if loading the person fails after a PIN was set, retrying must not replay the consumed code. Send the person to sign in with the new PIN.
4. **Large components.**
   - Split RevenueScreen (mobile), RecurringEditor, PeopleAccessView and RevenuePage (web) into coherent hooks, components and modules, not one-function files.
   - Add a `max-lines-per-function` warning (or equivalent) at a level the split code meets.
   - Keep `useFormats()` usage: components read the formatter from context, and helpers take it as an argument.
5. **Shared test coverage.**
   - Add table-driven tests in `packages/shared/tests` for `createFormatter` (kes, money, firstDayOfWeek, dates), percentText, maskPhone, initials, ordinal, safeTimeZone, revenuePeriodLabel and the auth client's headers, with edge cases.
   - Add vitest coverage thresholds for the shared package.
   - Then delete the app duplicates (`apps/web/tests/format.test.ts`, `apps/mobile/tests/format.test.ts` and any other copies).
6. **Formatter and `useGroupping`.**
   - Adopt Prettier with `format:check`, and add a format-only commit step for the reformat, kept separate from logic changes.
   - The `useGroupping` typo is a contract, not a rename. It lives in:
     - the C# property `OrganizationLocalization.UseGroupping`, a database column created in migration `20260924172309_OrganizationsAndFleet`;
     - the settings JSON and its labels in `OrganizationEndpoints`;
     - the shared `Formats` type, web and mobile code and tests;
     - settings change-log snapshots already stored;
     - the phone's cached appearance JSON in secure store (`xcode.appearance`).
   - The fix needs an EF migration (`RenameColumn`), API, shared, web and mobile renames, and backward-compatible reads of the old key in stored phone data and history display.
   - Prove each with a test.
7. **Component correctness and accessibility.**
   - Fix the Dialog double `onClose`, the Toast timer reset, and the ErrorText/ChoiceField accessibility gaps the findings name, on web and mobile as applicable.
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
    - Delete the divergent copies, keeping dark-mode parity.

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
