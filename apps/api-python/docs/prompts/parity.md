# Parity prompt: .NET and Python answer the same, byte for byte

Paste everything below the line into a fresh Claude Code session started in the repository
root, on Opus, after the Python side of an area is built and has passed its own `verify.md`
run. This session proves the Python API returns the same responses as the .NET API in
`apps/api` for the same requests on the same data — the one check Claude cannot supply by
reading its own code, because both sides came from one model reading the same documents.

Run it per area first (`AREA: auth`, then `tenancy`, `setup`, `revenue`, `pettycash`,
`expenses`, `reports`), and once with `AREA: all` before the rename to `apps/api`.

---

You are comparing two running APIs: the .NET API in `apps/api` (the source of truth for
behaviour, except the design-register rows) and the Python API in `apps/api-python`. You are
not confirming that Python works; you are finding every response where the two differ and
deciding, with evidence, whether the difference is allowed.

## Parameters

- `AREA:` <`auth`, `tenancy`, `setup`, `revenue`, `pettycash`, `expenses`, `reports`, `all`>
- `MODE:` <`report`: write only the report and the comparison harness | `fix`: also fix a
  Python-side difference that is a defect, each with a failing-first test>

## What may legitimately differ (and nothing else)

Only the **design-register rows B1–B22** in `docs/prompts/README.md`, which Python builds
ahead of .NET (`docs/13-open-questions.md` question 46): there the design notes decide
behaviour, so Python is expected to differ from .NET. For every such difference, cite the
register row and the `docs/15-design-v2-3.md` rule. Every other difference is a finding:

- a different HTTP status, or a different error `code` in the body;
- a different JSON shape, key set, key order where the client depends on it, number format
  (`useGrouping`/legacy `useGroupping`), or money representation;
- a different header the client reads (`WWW-Authenticate`, `Content-Type`, CORS, caching);
- a 200 on one side and a refusal on the other for the same input;
- a value present on one side and absent on the other.

A difference that is .NET being wrong against its own documented contract is still a finding,
recorded "for the user" — do not change the Python side to match a .NET bug without saying so.

## Read first

1. `CLAUDE.md`; `apps/api-python/README.md`; `docs/06-http-contract.md` for the area;
   `docs/prompts/README.md` (the drift register and the design register — the allowed
   differences).
2. The .NET routes for the area in `apps/api/Api/*Endpoints.cs`, their use cases and
   `tests/api/*Tests.cs` (the request shapes and the expected responses live there).
3. `docs/09-testing.md` for how the Python suite seeds data, and
   `tests/support/scenario.py` / `tests/support/client.py` / `tests/support/setup_client.py`
   for the token and organization helpers.

## Procedure

### 1. Stand both APIs up on the same data

- Start .NET against its SQLite in-memory or the shared `XCodeTest` SQL Server database as
  `tests/api/` does; start Python with `xcode-api serve` against a fresh local database on
  the 5433 cluster. Record both versions and the commit/SHA of each tree.
- Seed the **same** fixture into both: the same organization, the same people with the same
  PINs, the same vehicles, targets, periods and records. Reuse the Python
  `tests/support/scenario.py` builder as the definition of the fixture and replay the
  equivalent setup against .NET through its own API, so the data is identical by construction,
  not by hand. Capture the seed as a fixture the harness can rebuild.

### 2. Build the request corpus from the clients and the tests

The requests must be the ones real clients send, not ones you invent:
- every request shape in `apps/api/tests/api/*Tests.cs` for the area;
- every call site in `apps/web/` and `packages/shared/` for the area
  (`grep -rn "fetch(\|/auth/\|/setup/" apps/web packages/shared`), with their bodies;
- the released v2.11 mobile shapes in `tests/api/test_contract_released_clients.py`
  (Python) and the .NET `Phase1*` contract tests;
- for each, the positive case and the documented refusals (bad token, cross-tenant id,
  oversized body, missing permission, stale version).

Record each as a method, path, headers and body in a corpus file in your scratchpad.

### 3. Fire the corpus at both and diff

- Send each request to both APIs with the matching token for each side. For auth flows that
  issue codes, read the code from each side's development-code hook, not from mail.
- Normalise only what is legitimately environmental before diffing: the signing key, token
  values, timestamps, generated ids, and `X-Request-ID`. Everything else is compared exactly
  (status, headers the client reads, and the JSON body with keys sorted — but flag any place
  the client depends on key order).
- Produce a diff table: request → .NET response → Python response → `same` / `allowed
  (register row Bn)` / `DIFF`.

### 4. Triage every DIFF

For each `DIFF`, decide and record: a design-register allowance (cite the row), a Python
defect (fix in `fix` mode with a failing-first test, or report in `report` mode), or a .NET
defect against its own contract (for the user, with the contract clause).

### 5. Exports and files (`AREA: reports`, `expenses`)

Excel and PDF are built on both servers. Compare the generated workbook's cell values and
sheet structure and the PDF's text content (not the byte stream, which differs by library).
Confirm no cell that .NET emits as text is emitted by Python as a live formula, and vice
versa (this overlaps cluster SC3 of `docs/16-security-matrix.md` — formula injection).

## Invariants at the end

- Every request in the corpus has a verdict; counts add up.
- Every `DIFF` is a register allowance (cited), a filed finding, or a fix with a test.
- The comparison harness is committed under `apps/api-python/tools/parity/` (or reported as
  a deliverable) so the next session reruns it without rebuilding it.
- No Python response was changed to match a .NET contract bug without a "for the user" note.

## Verify (paste the outputs into the report)

```
# versions and SHAs of both trees
# the corpus size and the counts: same / allowed / DIFF
# for fix mode: ruff check . && ruff format --check . && mypy
#               the new parity tests, failing before and passing after
```

## Challenge pass (before the report)

Run the five modes of `docs/14-verification.md` over the parity work itself:
- assumptions: is the fixture truly identical on both sides, or did a default differ?
- falsification: pick three responses you marked `same` and prove they are byte-identical,
  not merely similar;
- pre-mortem: which client call site is not in the corpus, and would its difference have been
  caught?
- red team: can a request be crafted that one side accepts and the other rejects within the
  same contract (encoding, duplicate query key, header casing, trailing dot in a host)?
- dialectic: for each allowed difference, argue that it is a defect, then that it is allowed,
  and record which won and why.

## Report format

Write `apps/api-python/docs/audit/<yyyy-mm-dd>-parity-<area>.md`:
1. Verdict line: `parity holds`, `parity holds with allowed differences`, or `parity fails`,
   with counts.
2. Both versions and SHAs; how the fixture was built identically.
3. The diff table (or, if large, the summary plus every `DIFF` row in full).
4. Allowed differences, each citing its design-register row and `docs/15` rule.
5. Findings (Python defects), blockers first, in the `docs/14` section 7 format.
6. `.NET`-side defects for the user, with the contract clause.
7. The challenge pass.
8. Commands and outputs; the corpus and harness location.

## House rules

- Shared tree: `git status` first; never revert or reformat others' changes; never bare
  `git stash`; never kill a `dotnet`/`node`/`python` process you did not start (check its
  command line — a .NET Kestrel often holds port 5000).
- `report` mode writes only the report and the harness. `fix` mode edits only under
  `apps/api-python/`. Differences in `apps/api` or the clients are reported, never fixed here.
- Run both servers on local ports only. No commits unless asked; no AI attribution; no plan,
  prompt or finding identifiers in code.
- At ~100k context or three hours, write the report with the areas done, mark the rest `not
  checked`, and say where to resume.
