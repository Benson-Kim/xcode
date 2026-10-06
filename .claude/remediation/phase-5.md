# Phase 5 — Architecture & DRY consolidation (prompt 5)

Implement Phase 5 of the Revenue App Remediation Plan completely while preserving observable behavior. This is a controlled refactor, not modernization.

## Start here
1. Read CLAUDE.md (commands, shared-tree rules, known traps, evidence standard), `.claude/remediation/README.md` and `.claude/remediation/findings/phase-5-6.md` (verified findings with file:line; re-verify them). The original details are in `.claude/remediation/audit/extensibility.md`.
2. Run `git status` and check recent file times. Record a baseline of the full validation path before changing anything.
3. Before moving any logic, list every implementation and every test of it, in web AND mobile AND API, so the duplicate is deleted, not copied a third time.
4. Delegation:
   - `remediation-opus` (only if the gate holds) for item 1 (organization settings extraction) and item 8 (AuthService split);
   - `remediation-sonnet` for items 2–6 and 9;
   - at most two helpers, with disjoint files.

## Items

1. **Organization settings application layer.**
   - Add `OrganizationSettingsUseCases` behind `ISetupExecution`, so `OrganizationEndpoints` no longer orchestrates over `AuthDb`.
   - Endpoints keep routing and transport only.
   - Replace section-name branching with an `ISettingsSection` strategy where it really removes the branching. `SettingsSectionRegistry` is registered (Program.cs) but dead: it covers 3 sections and nothing consumes or tests it. Complete or replace it, and do not assume it works.
   - Today the settings, logo and preference endpoints bypass `UnitOfWork` (`OrganizationEndpoints.cs` ~83/105/119/182). Moving them onto the pipeline adds the serializable transaction and the change-log retry, which is a deliberate behavior change.
   - `UnitOfWork.Read` throws if tracked entities change. `Settings()` uses tracked queries and `UserPreference.Validate()` mutates, so use `AsNoTracking` or validate copies.
   - Route time-zone changes through `Organization.ChangeTimeZone`. Today it is called only by a unit test, while the endpoint calls `EnsureBusinessDateWithin` directly. `ChangeTimeZone` bumps `SettingsVersion` itself, so remove the endpoint's separate bump or the version moves twice.
   - Keep these exactly: the HTTP contract (statuses, problem titles and details that the tests pin, e.g. the 400 "held business date" message), the change-log entries, and the 409 on version conflicts.
   - Add the missing test for the 409 on a slug conflict.
2. **Shared capture rules.**
   - Move `missingOn`, `firstGap`, `nextMissing`, `opens` and the week capture rules into `@xcode/shared/capture.ts` as pure functions over `RevenueWeek`.
   - Migrate web `RevenuePage` and mobile `RevenueScreen`. The mobile copies live in `RevenueScreen.tsx` (~82–177, ~285–311, ~806); `src/revenue/week.ts` does not duplicate them.
   - Delete the copies.
   - Add table tests in `packages/shared/tests`.
3. **Shared appearance.**
   - Put the `Appearance` type, `resolveTheme` and brand-token derivation in shared, free of frameworks.
   - Today web `lib/appearance.ts` and mobile `src/appearance.ts` each define them.
   - No web↔mobile palette parity test exists, and the palettes already disagree: mobile light `blueTint`/`blueWash` hold web's `blue-soft`/`blue-tint` values. Reconcile them deliberately and add a parity test.
4. **Status metadata.**
   - Use one exhaustive `Record<RevenueStatus, { counted, label, tone, recorded }>` (or equivalent) in shared.
   - Migrate every switch and mapping in web and mobile, and delete them.
   - Adding a status must fail typechecking until every consumer is handled.
   - Define each field from its actual uses. "Counted" is used two different ways on mobile (`RevenueScreen.tsx` ~412 vs ~970–973).
5. **Revenue date formatting.**
   - Provide one shared revenue date formatter built from the organization's `Formats`, as a member of `createFormatter`'s result. Phase 2 removed the global formatter, so do not reintroduce module state.
   - Mobile must honor the organization's `datePattern`.
   - Components get it from `useFormats()`.
   - The offline queue persists already-formatted date text (`QueuedCapture.message`, `queue.ts` ~321). Derive that sentence at render time, and keep `periodLabel` as `appearance.test.tsx` pins it.
6. **Permissions.**
   - Make `PermissionCatalog` (C#) the single source for permission keys, with an exported TS union (generated or checked by a test that fails on drift) and a shared nav-visibility predicate.
   - The server remains the final authority.
7. **Dead abstractions: verify first.**
   - `IUnitOfWork` and `OrganizationUseCase<,>` are NOT dead today. They carry the serializable transaction, authorization-before-validation, and the change-log-collision retry used by setup, revenue and organization writes. `ChangeLogAndScopeTests` pins that behavior.
   - Delete or collapse them only if you replace that behavior one-for-one, with those tests still green; otherwise record NOT REPRODUCIBLE with the evidence.
   - `Organization.ChangeTimeZone` is handled by item 1.
8. **Split AuthService.**
   - Create cohesive services, e.g. `SignInService` (sign-in, unlock, device verification), `PinSetupService` (code issuance, setup, reset) and `SessionService` (refresh, sign-out, device revocation).
   - Share no hidden mutable state. Today the `outgoing` mail field couples IssueCode to `Deliver`, so design that hand-off explicitly.
   - Preserve all of these:
     - `AuthEndpoints.Run`'s per-account `AuthGate` lock and serializable transaction under the execution strategy;
     - mail delivery after commit (`Deliver`);
     - the hourly and daily code caps;
     - `UntrustedAttemptLimit`, and the rule that `IssueTokens` does not clear lockout;
     - enumeration-resistant responses (AuthTests `Seen` comparisons);
     - policy clamping;
     - refresh rotation and reuse detection;
     - the public constants `AuthService.UntrustedAttemptLimit`, `HourlyCodeLimit` and `DailyCodeLimit`, which tests reference (move them deliberately).
   - Fix while splitting: `outgoing` is never reset between execution-strategy retry attempts, so a code from a rolled-back attempt could still be mailed. Also note the device-revoke route locks on `device:{id}`, not on the account.
   - Migrate DI and all callers.
9. **Shared package root export.**
   - `packages/shared/package.json` points `main`, `types` and `exports["."]` at `src/index.ts`. That file existed at HEAD and was deleted by the uncommitted split into `auth`, `dates`, `format` and `revenue` modules.
   - Either add a deliberate barrel or remove the root export.
   - Prove it with a typecheck or test that imports each public entry.

## Done means
- All nine items are implemented with evidence (file + symbol + a test that would fail without it).
- Behavior is unchanged except where an item says otherwise.
- Stale imports and dead code are gone. Do not leave adapters that keep both the old and new implementations unless compatibility requires it, and name that reason.
- The full validation path is green, including the mobile typecheck, apart from attributed failures that belong to other sessions.
- A `remediation-auditor` pass over the nine items reports no PARTIAL.
- Update `.claude/remediation/README.md` and the `remediation-program` memory.

End with a nine-item matrix that names the duplicate or dead implementation removed for each item.
