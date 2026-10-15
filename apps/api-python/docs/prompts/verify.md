# Verification prompt (adversarial, multi-purpose, repeatable)

Paste everything below the line into a fresh Claude Code session started in the repository
root. Fill in the three parameters first. Run it:
- after every implementation prompt, before anyone calls that prompt "validated";
- on a whole area before new features land on it;
- before a merge, a deploy or the rename to `apps/api`;
- on documents and prompts alone (`SCOPE: area:docs`), before handing them to the next
  session.

Model: Opus for `all`, `area:auth`, `area:tenancy`, `area:hosting`, any scope with a
migration, and `MODE: fix` on security or concurrency findings; Sonnet is enough for
`MODE: report` on one prompt's non-security area. Run it in a session of its own: a session
that wrote the code does not verify it.

---

You are verifying `apps/api-python`, the Python and PostgreSQL rewrite of the .NET API in
`apps/api`. You are not here to confirm that it works. You are here to find out where it
does not, and to prove each verdict with evidence a reader can open.

## Parameters

- `SCOPE:` <one of: `prompt:NN` (that prompt's deliverables and invariants), `area:NAME`
  (`auth`, `tenancy`, `setup`, `revenue`, `pettycash`, `expenses`, `reports`,
  `operability`, `hosting`, `data-migration`, `docs`), `change:<git range, or a list of
  files>`, `all`>
- `MODE:` <`report`: read-only, you write only the report | `fix`: you also fix the
  findings that survive, each with a test that fails without the fix>
- `DEPTH:` <`standard`: targeted test modules plus one full run | `deep`: adds the
  `EXPLAIN` evidence at 10x the demo seed, a run on every PostgreSQL version available, and
  a second, independent pass over D1 to D3>

## Stance (read twice; it overrides habit)

1. **Fresh eyes.** Assume nobody has ever challenged this code. Earlier audits,
   `docs/audit/*`, memory notes, "validated" statuses, commit messages, docstrings,
   comments, test names and the documents themselves are claims. You read earlier audits
   only after your own pass, to find regressions and what they missed.
2. **Steelman, then attack.** Write the strongest version of the claim before you
   challenge it.
3. **Ground or drop.** Every challenge has a `file:line`, a concrete input or state, and
   expected versus actual behaviour.
4. **Try to refute yourself.** Before a finding goes into the report, try to prove it
   wrong: look for the guard you missed, the constraint, the earlier check, the test.
   Concede what holds and say what defeated it.
5. **Synthesis, never a bare objection.** Each surviving finding ends as a fix with a
   failing-first test (`fix` mode), a corrected document, an open question with a default,
   or a recorded residual risk with an owner.
6. **Verdict per clause:** `holds`, `fails`, `unproven`, `n/a`, `not checked` (with why).
   Counts add up. A domain without findings lists the three hardest attacks you tried and
   why they failed.
7. **Measure, do not remember.** Versions, timings, file states and test counts come from
   commands you ran in this session.

The method is `apps/api-python/docs/14-verification.md`. It holds the five modes, the
red-team personas, the probe checklist per domain (D1 to D11), the evidence grades and the
finding format. Follow it exactly. If the `the-fool` skill is installed, its reference
files (`references/*.md`) give more depth on each mode; do not run its interactive mode
selection: here every mode runs, every time.

## Read first

1. `CLAUDE.md` (the shared-tree rules apply in full); `apps/api-python/README.md`.
2. `apps/api-python/docs/14-verification.md` (all), `docs/00-principles.md`,
   `docs/09-testing.md` section 1.
3. For the scope: the prompt in `docs/prompts/` (deliverables and invariants are the
   claims), the documents it cites, and `docs/prompts/README.md` (status and the drift
   register).
4. The code, tests and routines of the scope. For contract parity (D4), the .NET code that
   decides behaviour: `apps/api/Api/*.cs` for routes, the use cases and domain files the
   scope ports, and `tests/api/*Tests.cs`. Reading C# is required here, not forbidden.

## Procedure

### 1. Orient (facts only)

- `git status --short`; the modification times of the files in scope; whether another
  session is writing there now (files changed in the last 30 minutes you did not touch).
  In `fix` mode, never edit a file another session changed in the last 30 minutes; report
  it instead.
- Environment: `SELECT version()` on the test cluster (on the development machine
  `XCODE_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5433/postgres`, PostgreSQL 16,
  `docs/09-testing.md` section 5), `python --version`, the CI PostgreSQL image in
  `.github/workflows/xcode-api.yml` and whether CI has ever run it.
- The test template: its comment holds the fingerprint of the `db/` files and the runner
  it was built from (`tests/support/database.py` `template_fingerprint`); compare it with
  the current files. The harness rebuilds a stale template itself and refuses while another
  session runs; never drop it by hand under someone else's run (`pg_stat_activity`, the
  `test_gw*` databases).
- Drift: `git log --since=<inventory date> -- apps/api tests/api` and
  `git status --short apps/api tests/api`; compare with the drift register.
- Baseline: run the scope's targeted test modules once and record the counts before you
  change anything.

### 2. Steelman

Write the thesis for the scope ("prompt 06 delivers D1 to D7, its invariants hold, and the
behaviour equals the .NET code at <commit>") and extract its claims into a table: claim,
where stated, the code that should carry it. Include every deliverable bullet, every
invariant, and every doc clause the scope implements.

### 3. Challenge: five modes over every domain in scope

Domains D1 to D9 as the scope touches them; D10 (tests as evidence) and D11 (documents and
prompts) always. For each domain:
- give every probe of `docs/14-verification.md` section 4 a verdict, with evidence;
- run the five modes and keep the 3 to 5 strongest challenges per mode:
  assumptions inventory, falsification table with grades, pre-mortem narratives with an
  inversion check, red-team vectors against the personas, dialectic on each decision the
  scope relies on.

Mechanical sweeps (always; report every hit with `file:line`):
- routes: the .NET route table versus `docs/06-http-contract.md` versus the Python routers
  versus `xcode-api openapi` (write the document to your scratchpad, not `/tmp`);
- `api.*` routines: each has a file, a `docs/05-routines.md` entry, a test per `Raises:`
  code, and the tenant guard where it takes an organization;
- `now()`, `current_date`, `clock_timestamp()`, `random()` in `db/routines`;
- `EXECUTE` and `format(` in `db/routines`; `SECURITY DEFINER` without `SET search_path`;
- `skip`, `xfail`, `importorskip`, `sleep(`, bare `except` in `tests/`;
- `TODO`, `FIXME`, `XXX`, `HACK`, plan or prompt identifiers (`Prompt 0`, `Phase [0-9]`,
  `P[0-9]-[0-9]`) in `src`, `db`, `tests`;
- log calls that pass a body, phone, email, PIN, code or token;
- `XCODE_*` names across `settings.py`, `.env.example`, `docs/08-operability.md`,
  `tests/unit/test_settings.py`.

### 4. Self-refutation

For each surviving challenge, spend real effort proving it wrong. Run the test that would
show the guard. Read the constraint. Ask whether the .NET code behaves the same way (then
it is parity, and the finding moves to "for the user" or an open question, not a fix).
Record conceded challenges with the guard that defeated them.

### 5. Fix (`MODE: fix` only)

- Order: blockers, then majors. Minors and notes go in the report.
- For each fix: write the test first, run it and see it fail for the reason in the
  finding, make the smallest coherent change, run it green, then rerun the targeted
  modules.
- After changing a migration, a routine file or the runner, the next run rebuilds
  `xcode_template`; if it refuses because another session is running, wait and rerun.
- Never weaken or delete an assertion; never mark a test skipped or expected to fail. If a
  test's expectation is wrong, prove it against the .NET code or the HTTP contract and
  say so.
- Documents follow the code in the same change: `docs/04` to `docs/06`, the inventory, the
  prompt, the README drift register, `docs/13-open-questions.md`.
- Fixes outside `apps/api-python` (the .NET API, the clients) are not yours: report them.

### 6. Full run and regression check

- Run the full suite once, in the background, with a log file in your scratchpad:
  `pytest -n 3 -q -p no:cacheprovider > <scratchpad>/full.log 2>&1` (one to two hours on
  this machine). Report passed, failed, skipped, errors and duration from the log. If a
  failure belongs to another session's in-flight work (check the file times and diffs),
  attribute it instead of fixing it.
- `ruff check . && ruff format --check . && mypy`; `xcode-api db routines` and
  `xcode-api db verify` against the CLI database (`docs/08-operability.md` section 8).
- Only now read the earlier audits and validation reports for the scope: list every
  finding they recorded as fixed that is broken again, and every finding of yours they
  missed.

## Report

Write `apps/api-python/docs/audit/<yyyy-mm-dd>-verify-<scope>.md` (the scope with `:`
replaced by `-`), in this order:

1. **Verdict line**: `pass`, `pass with findings` or `fail`, and the counts per verdict and
   per severity. `fail` if any blocker survives, or if the full suite did not run to
   completion.
2. **Thesis and claims**: the steelmanned thesis and the claims table with a verdict and an
   evidence grade per claim.
3. **Findings**: one row per surviving finding in the format of
   `docs/14-verification.md` section 7, blockers first.
4. **Per domain**: probe verdicts; for a domain without findings, the three hardest attacks
   tried.
5. **Per mode**: the assumption inventory, the falsification table, the pre-mortem
   narratives with the inversion check, the red-team vectors, the dialectic verdicts.
6. **Conceded**: challenges that did not survive, with the guard that defeated each.
7. **Fixes** (`fix` mode): finding id, files changed, the test that failed before and
   passes now.
8. **Commands and outputs**: trimmed; the full-run counts and duration; versions measured.
9. **Regressions and misses** against earlier audits.
10. **For the user**: only decisions that are irreversible or purely business, each with
    your recommendation and its reason.

## House rules

- Shared tree: `git status` first; never revert or reformat changes you did not make;
  never bare `git stash`; never kill processes you did not start (check the command line).
- `MODE: report` writes only the report file. `MODE: fix` edits only under
  `apps/api-python/`.
- No commits unless the user asks. No AI attribution anywhere.
- No comments unless needed; no plan, prompt or finding identifiers in code or comments
  (finding ids live in the report only).
- Work inline. At most one read-only helper (`remediation-auditor`) for a mechanical sweep,
  with the exact file list and a word limit; judgement is never delegated, and you
  spot-check any helper result you rely on.
- If the session passes about 100k tokens of context or three hours, write the report with
  what is done, mark the rest `not checked`, and say where to resume.
