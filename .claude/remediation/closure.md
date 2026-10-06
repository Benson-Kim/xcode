# Closure session — report-to-code crosswalk (prompt 7)

The six phases are reported done. Your job is to prove the Revenue Remediation Plan is closed against the current repository, and to implement every repository-actionable item that is not. Do not produce another audit and stop.

## Sources (read all of them)
- `.claude/remediation/README.md`: status, handover notes and known residuals. Start with the residuals; they are pre-confirmed gaps.
- The plan: artifact https://claude.ai/artifact/2uETHfTRdMZCP4j2skjzvW (read it with the Artifact tool, `action: read`). There is no plan `.md` in the repo.
- The seven detailed audit reports: `.claude/remediation/audit/{security,safety,integrity,operability,scalability,extensibility,maintainability}.md`. They hold many findings the phase summaries compress or omit, including lows. All of them must be crosswalked, not only the phase bullets.
- Verified findings and outcomes per phase: `.claude/remediation/findings/phase-*.md`.

## Method
1. Baseline: run `git status`, then the full validation path from CLAUDE.md, and record failures before you change anything.
2. Crosswalk with two `remediation-auditor` helpers in parallel. Split by report, e.g. A = security, safety, integrity, operability and B = scalability, extensibility, maintainability. Each writes `.claude/remediation/findings/closure-<A|B>.md` with one row per finding: id, finding, verdict, evidence path:line + symbol, covering test, remaining work.
3. Verdicts:
   - IMPLEMENTED: the code path plus a test that would fail without it.
   - SUPERSEDED: a redesign removed the risk; show where.
   - NOT IMPLEMENTED
   - NOT REPRODUCIBLE: prove it with code.
   - BLOCKED: names the external dependency.

   Comments, TODOs, docs, test names or issue links are not evidence. Neither is a test that fakes the capability under test.
4. Spot-check at least one evidence line per IMPLEMENTED row yourself, and every row that a phase report claimed but the auditor doubts.
5. Fix every NOT IMPLEMENTED item this session. Group the fixes by area and use one writer per file set:
   - `remediation-sonnet` for routine fixes;
   - `remediation-opus` only past the CLAUDE.md gate, one issue per brief.
   Integrate each result, migrate web AND mobile callers, and add tests.
6. Run the full validation path again: format check (if Phase 6 added one), lint, all three typechecks, shared/web/mobile tests, API build and tests. Run `SqlServerTests` too when `SQLSERVER_TEST_CONNECTION` or CI provides a server. Attribute failures before fixing them, and do not weaken tests.
7. Write `REMEDIATION-CLOSURE.md` at the repo root. For each finding give: original finding (report + id); disposition; implementation evidence (file/symbol); regression-test evidence; remaining deployment/manual dependency. Keep it factual and concise.
8. Update `.claude/remediation/README.md` (status, residuals) and the memory file `remediation-program`.

## Known areas to check first
- Every item listed under "Residuals" in the README.
- Plan clauses that are easy to half-do:
  - "always display with the same fraction digits" (kes);
  - "require an explicit flag" (LogEmailSender);
  - "fail startup if Development with a non-local DB";
  - "validate upstream response shape" (GET session, shared auth client);
  - "mirror in shared TS" (PhoneNumber);
  - "bust on revoke or SecurityVersion change" (auth caches);
  - device-runtime claims (mobile crypto, timeouts).
- Cross-cutting invariants: concurrency tokens actually change; caches invalidate; schema changes have migrations; the shared package has no React/RN/Next imports.

The task is not complete while any repository-actionable NOT IMPLEMENTED finding remains. Do not end with an offer to continue later.
