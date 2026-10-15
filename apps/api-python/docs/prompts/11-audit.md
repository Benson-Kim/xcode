# Prompt 11: conversion audit (read-only)

Paste everything below the line into a fresh Claude Code session running Opus, started
in the repository root, after prompts 00 to 10 and 08b have been run. It is the final
run of `docs/prompts/verify.md`, over every domain, by a session that wrote none of the
code.

---

You are auditing `apps/api-python` against its own specification. You change nothing
except one new report file. Your output decides whether the folder can be renamed to
`apps/api`, so every verdict needs evidence a reader can open.

## Read first

1. `CLAUDE.md`; `apps/api-python/README.md`.
2. Every document in `apps/api-python/docs/` from `00-principles.md` to `13-open-questions.md`.
3. `apps/api-python/docs/inventory/*.md` (the extracts from the .NET code and clients).
4. `apps/api-python/docs/prompts/00-bootstrap-app.md` to `10-data-migration.md` and
   `08b-expenses-reports.md`, for the deliverable lists; `docs/prompts/README.md` for
   the status, the drift register and the design register (every row closed, or open
   with an owner decision in `docs/13-open-questions.md`).
5. `apps/api-python/docs/prompts/verify.md` and `docs/14-verification.md`: the method.

## Method

Run `docs/prompts/verify.md` with `SCOPE: all`, `MODE: report`, `DEPTH: deep`. Its
stance, procedure, sweeps and challenge record apply in full; this prompt adds the
clause-by-clause sections below. Earlier audits in `docs/audit/` are read only after
your own pass.

For every clause, find the code (`file:line`, symbol) and the test that would fail without
it. A clause with code but no failing test is "unproven". A clause with a test that fakes
the capability under test (a mocked repository in a behaviour test, a mocked hasher, a
skipped RLS) is "unproven". A clause whose test weakens or skips an assertion is "failed".

Run, and attach trimmed outputs:

```
cd apps/api-python
ruff check . && ruff format --check . && mypy
pytest -n 3 -q -p no:cacheprovider > <scratchpad>/full.log 2>&1
xcode-api db migrate && xcode-api db status && xcode-api db verify ; echo "exit=$?"
xcode-api openapi > <scratchpad>/openapi.json
```

Mechanical sweeps (report each hit with file:line):
- names: `grep -rn "Auth\b\|AuthDb\|Auth\.Api" src db tests docs --include=*.py --include=*.sql --include=*.md` (allowed: `auth` as a feature name, `api.auth_*`, `/auth/` routes, `application/auth/`);
- plan or prompt identifiers in code or comments (`grep -rn "Prompt 0\|Phase [0-9]\|P[0-9]-[0-9]\|C[0-9]\b" src db tests`);
- `TODO`, `FIXME`, `XXX`, `HACK` anywhere under `src`, `db`, `tests`;
- SQL text in Python outside `db/session.py`, `db/pool.py`, `db/migrate.py`, `db/verify.py`;
- `print(` in `src`; `# type: ignore` and `# noqa` with their reasons;
- secrets: anything that looks like a key, password or connection string with credentials
  in the repository (`.env` must not be committed);
- every `XCODE_*` variable appears in `settings.py`, `.env.example`,
  `docs/08-operability.md` and `tests/unit/test_settings.py`;
- every routine file under `db/routines/` has an entry in `docs/05-routines.md` and a test
  in `tests/db/`; every `api.*` routine in the database has a file;
- every endpoint in `docs/06-http-contract.md` appears in `<scratchpad>/openapi.json`
  with the same method and path, every operation in the OpenAPI document appears in the
  contract, and every route of `apps/api/Api/*.cs` appears in both;
- every .NET test class in `docs/inventory/inventory-tests.md` has a row in the crosswalk
  of `docs/09-testing.md` section 4 naming an existing Python test.

## Report

Write `apps/api-python/docs/audit/<yyyy-mm-dd>-conversion-audit.md`:

1. Summary: counts of proven, unproven, failed, not applicable; the blocking items.
2. Principles (`docs/00-principles.md`): one row per rule: verdict, evidence, test.
3. Architecture (`docs/01-architecture.md`): import rule, package map, request lifecycle
   steps, error model, concurrency rules, locality table spot checks (pick three recent
   changes from `git log -- apps/api-python` and show which files they touched).
4. Database (`docs/03-database.md`, `docs/04-schema.md`, `docs/05-routines.md`): one row per
   table and per routine: exists, conventions met, tests present; `db verify` output.
5. HTTP contract (`docs/06-http-contract.md`): one row per endpoint: status codes, bodies,
   headers, permission, statement budget, tests; byte-for-byte checks for sign-in refusals.
6. Auth (`docs/07-auth.md`): parameters, flows, lockout model, enumeration resistance,
   token and refresh semantics, with tests.
7. Operability (`docs/08-operability.md`): settings, logging, health, CLI, startup and
   shutdown sequences, safety switches.
8. Security (`docs/12-security.md`): one row per control in the matrix: proven, unproven,
   failed, with evidence.
9. Testing (`docs/09-testing.md`): harness behaviour, layers present, crosswalk complete,
   suite duration.
10. Data migration (`docs/10-data-migration.md`): tool present, dry-run report attached.
11. Naming (`docs/11-naming.md`): sweep results.
12. Open questions: new ones you found, with file:line.
13. The challenge record of `verify.md`: findings, conceded challenges, the per-mode
    tables, and the drift register re-measured (every row closed or still open, with
    evidence).

## Rules

- You do not edit code, tests, documents or inventories; you report. If you believe a
  document is wrong, say so in section 12 with the evidence.
- Do not run `git stash`, do not kill processes, do not start long builds other than the
  commands above.
- Verdicts are per clause, never per section; "mostly done" is not a verdict.
