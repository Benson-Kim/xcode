# One hard finding (prompt 8)

We are solving exactly one remediation issue in this session:

[PASTE ONE FINDING HERE — include its source: plan item, audit report + id, or README residual]

Treat this as an implementation task.

## 1. Understand it
- Read CLAUDE.md (traps, shared-tree rules, evidence standard) and `.claude/remediation/README.md`.
- Read any matching entry in `.claude/remediation/findings/` and in `.claude/remediation/audit/*.md`.
- Inspect the current implementation, every caller (web AND mobile), relevant tests, data model/configuration, stored client data, and conventions.
- Confirm the risk still exists. If it does not, prove that with code and stop.
- Record a baseline of the tests that cover the area.

## 2. Choose the smallest coherent fix
The fix must remove the underlying risk, not mask the symptom. Write the acceptance criteria as externally observable behavior: status codes, stored state, UI text, timing.

## 3. Delegate only past the gate
If the issue meets the CLAUDE.md complexity gate, delegate the core work to `remediation-opus`. The brief must contain:
- the exact problem and its evidence;
- the desired observable behavior;
- files already found;
- invariants that must not regress;
- the tests required;
- the verify commands;
- the shared-tree rules;
- an explicit instruction to modify code rather than recommend.

Otherwise do it yourself or with `remediation-sonnet`. Integrate the result yourself; never paste a helper's report as the outcome.

## 4. Finish
- Migrate all affected callers.
- Add regression tests that fail without the fix. Do not fake the capability under test.
- Run targeted tests, then the relevant broader typechecks and suites (all three typechecks when TS changed).
- Fix failures you introduced, and attribute the others.
- Remove implementations that the fix makes obsolete.
- No TODOs, placeholders, disabled tests, or parallel old/new paths without a real compatibility reason.
- Update the README residuals list and the findings file for that phase.

Completion means:
1. root cause resolved;
2. callers migrated;
3. regression tests added and passing;
4. builds and typechecks pass;
5. no actionable work remains for this finding.

End with the outcome, changed files, the tests run and their results, and any genuine external blocker.
