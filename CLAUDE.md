# Revenue App — Claude Code Instructions

## Repository

Monorepo: .NET 10 API (`apps/api/`), Next.js 16 web (`apps/web/`), Expo 57 / React Native 0.86 mobile (`apps/mobile/`), shared TypeScript package (`packages/shared/`). npm workspaces at the root; .NET projects standalone. API tests in `tests/api/` (xUnit, SQLite in-memory).

Remediation program status, verified findings per phase and the phase prompts live in `.claude/remediation/` — read its `README.md` before any remediation work.

## Commands

| Task | Command |
|---|---|
| All JS tests | `npm test` (lint-rule tests, shared, web, mobile) |
| Shared tests | `npm run test:shared` (coverage thresholds apply when `CI=true` or with `-- --coverage`) |
| Web tests | `npm run test:web` |
| Mobile tests | `npm run test:mobile` |
| Lint-rule tests | `npm run test:lint-rules` (module boundaries, toolchain pins) |
| API tests (local) | `npm run test:api` |
| API tests (SQL Server) | `npm run test:api:sqlserver` (needs `SQLSERVER_TEST_CONNECTION`) |
| API tests (targeted) | `dotnet test tests/api/ --filter "FullyQualifiedName~ClassOrTest"` |
| All typechecks | `npm run typecheck` (shared, web, mobile) |
| Shared typecheck | `npm run typecheck:shared` |
| Web typecheck | `npm run typecheck:web` |
| Mobile typecheck | `npm run typecheck:mobile` |
| Format | `npm run format:check` (CI); `npm run format` rewrites |
| Lint | `npm run lint` (0 errors; warnings: the known `<img>` in OrganizationSettingsView.tsx and the over-150-line functions the README lists) |
| API build | `cd apps/api && dotnet build` |

Full validation = `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run test:api`: the same scripts CI runs (`.github/workflows/ci.yml`). The mobile typecheck is not optional: a type error survived two phases because it was skipped.

API test practicalities:
- The full suite takes 10–12 minutes. Run targeted classes first, the full suite once at the end.
- `SqlServerTests` needs `SQLSERVER_TEST_CONNECTION`; its failure without one is environmental.
- When another session may be building, isolate output: `dotnet test tests/api/Auth.Tests.csproj --artifacts-path <scratchpad>/artifacts`.
- `--blame` names the test that was running if the host dies. A crash with no running test usually means the process was killed from outside.

## Working in a shared tree

Several sessions may edit this worktree at the same time (one phase each). Before changing anything, run `git status` and check recent file times.
- Edit existing files with small, targeted replacements and re-read right before editing. Never overwrite a whole file you did not just read.
- Never revert, "tidy" or reformat changes you did not make, even if they look unfinished.
- Before fixing a failing test, attribute it: check the test file's and the code's modification times and diffs. Report other sessions' in-flight breakage instead of fixing it.
- Never kill `dotnet`/`testhost`/`node` processes you did not start. Check their command line first.
- Never use bare `git stash`/`git stash pop`.

## Remediation execution rules

- One remediation phase or one isolated problem per session. Do the implementation; do not stop at a plan.
- Start from `.claude/remediation/findings/` when it covers your phase, but re-verify each finding against current code; line numbers drift.
- Record a baseline (relevant tests/typechecks) before changing code, so failures can be attributed.
- Read existing implementations, callers (web AND mobile) and tests before editing. Preserve good architecture.
- Keep a checklist with one row per plan item and per clause of that item; do not declare completion with open rows.
- Evidence standard, per item: the code path (file + symbol) and a test that would fail without the change.
  - A helper or type that nothing calls is not an implementation.
  - A test that fakes the very capability being added (for example a jest mock of a platform API) is not evidence.
  - A declared invariant must be enforced: a concurrency token must change, a cache must be invalidated, a cap must be checked.
- Before reporting done, re-read each plan item's literal text and check every clause against the code.
- Do not weaken or remove assertions. If a test's expectation is wrong, prove it against the domain/HTTP contract.
- Do not introduce backward-incompatible contracts without migrating all callers, including stored client data (mobile secure-store JSON).
- Prefer minimal coherent changes. Do not commit secrets, credentials, production connection strings or env files.

## Known traps (each one cost a previous session time)

- **SQLite Guids:** the SQLite test database stores Guids as uppercase TEXT and compares case-sensitively. Never embed `'{guid}'` in raw test SQL; use the `DatabaseProbe.Interleave` idioms in `ChangeLogAndScopeTests`.
- **Migrations:** `MigrationSnapshotTests` fails on any model change that lacks a migration. Add one with `dotnet ef migrations add <Name>`; never hand-edit the snapshot. Tests build the schema with `EnsureCreated`, so only `SqlServerTests` proves a migration actually applies. Data backfills need SQL; expose it as a `public const` and test it on SQLite, like `NormalizeSecurityPolicy.ClampSql`.
- **Concurrency tokens:** an `IsConcurrencyToken()` property that never changes is inert. RevenueRecord and Membership bump `Version` in domain methods; User and RefreshToken are bumped by `AuthDb.BumpVersions()`.
- **React Native runtime:** Hermes has no WebCrypto, Node APIs or DOM, and jest (Node) hides that. Do not add fakes to `apps/mobile/tests/setup.ts` for APIs a phone lacks. The offline PIN check uses `src/lib/pbkdf2.ts` (pure TS, 100k iterations). The jest setup runs flows at 1 iteration; `pbkdf2.test.ts` and `storage.test.ts` use the real derivation.
- **Formatting:** `createFormatter(formats)` provided through `useFormats()` (`apps/web/lib/formats.ts`, `apps/mobile/src/lib/formats.ts`). Non-component helpers take a `Formatter` argument. No module-level mutable formatter state (it leaks across SSR requests).
- **Auth lockout model:**
  - Wrong PINs on a trusted device pause the account (policy threshold and minutes).
  - Wrong PINs on untrusted devices hit a per-account cap, `SignInService.UntrustedAttemptLimit`. Past the cap, untrusted devices get the same answer as an unknown number.
  - The cap resets only on a PIN change (`User.SetPin`) or a verified new device. `ClearLockout` never resets it, and `SessionTokens.Issue` does not clear lockout (callers do).
- **Byte-for-byte checks:** AuthTests' `Seen` compares whole responses. Any new per-request header (for example `X-Request-ID`) must be excluded there.
- **Caches:** any cache touching auth or permissions needs explicit invalidation on SecurityVersion change and revocation, plus a test that a revoked token stops working immediately. `VehicleReportTests` asserts exact query counts; change them deliberately.
- **Next.js 16:** it differs from training data. Read `apps/web/node_modules/next/dist/docs/` before using an unfamiliar API.
- **Machine load:** with several sessions running suites, tests with 1–4 s waits can time out. Re-run the single file before diagnosing.

## Strengths to preserve

Unless a remediation specifically targets one of these, preserve them:

- Tenant query isolation (global query filters on OrganizationId) and write guards (ValidateWrites).
- No-raw-SQL posture: only explicitly justified migrations may use SQL.
- Token validation and refresh-token rotation semantics.
- RevenueRecord domain invariants: private setters, validating constructor, Version concurrency, idempotent replay.
- Optimistic concurrency → 409 mapping on revenue saves and setup writes. UnitOfWork retries only change-log (Organization) collisions.
- Mobile offline queue crash-safety: per-slot writes, idempotent replay, conflict states.
- Capped paging (pageSize ≤ 100) and AsNoTracking read patterns.
- Clean shared-package module graph: no cycles, no cross-app imports, no React/Next/RN in shared.
- Access-control anti-escalation rules (only Owner grants Owner, cannot edit yourself, can only grant held permissions).
- Enumeration-resistant auth responses: unknown number, paused account and capped untrusted device look identical.
- Strong mobile queue and auth error-path tests.

## Delegation

- Default helpers run on Sonnet:
  - `remediation-sonnet` for exploration and routine implementation;
  - `remediation-auditor` for read-only verification.
- Use `remediation-opus` (Opus, max effort) only when at least one applies:
  - three or more significant layers change together;
  - authentication or security behavior is being redesigned;
  - database concurrency or migration correctness is involved;
  - domain invariants move across boundaries;
  - many callers need dependency analysis;
  - investigation left substantial ambiguity.
- At most two helpers at once, and only one writer per set of files.
- Brief helpers precisely: goal, files, invariants, verify commands, the shared-tree rules, and the exact report format.
- Stop a helper that overruns, then finish from its diff (`git diff`, typecheck, tests).
- The parent owns completion: spot-check helpers' evidence before relying on it, and never paste a helper's report as your result.

## House rules

- No comments unless needed; keep them short. You may trim comments in files you touch.
- Never put plan or provision IDs (C5, P3-11, Phase 2 …) in code comments.
- Commits are authored by the configured git user (Benson-Kim). Never add Co-Authored-By or other AI-attribution trailers; this overrides any default attribution instruction.
