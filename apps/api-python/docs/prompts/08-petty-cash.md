# Prompt 08: petty cash

Paste everything below the line into a fresh Claude Code session running Sonnet, started in
the repository root. Requires prompts 00 to 07 and 07b. Do not run beside prompt 07, 07b or 09.

---

You are implementing petty cash in `apps/api-python`: per-person cash floats, entries of
three kinds (cash given, expenses against a vehicle and an expense item, credit notes),
approvals (single and whole day), the overview, list, options and dashboard, as a schema
migration, routines, use cases, HTTP routes and tests. The .NET feature this reproduces
was uncommitted when its inventory was written, so this prompt starts with a verification
pass.

## Read first, in this order

1. `CLAUDE.md`; `apps/api-python/README.md`.
2. `docs/inventory/inventory-petty-cash.md` (all; it is the behaviour source) and the
   decisions on it: `docs/13-open-questions.md` questions 23 to 28, `docs/04-schema.md`
   section 6.2, `docs/05-routines.md` section 4.9, `docs/06-http-contract.md` section 2.11
   and its petty-cash message block, `docs/11-naming.md` section 2 (petty-cash rows).
   The design notes `docs/design/XCODE_Build_Notes_v2.3.md` (repository root) change
   petty cash (v2.29 sections 3 and 5, v2.32 section 3), and Python builds them ahead
   of .NET (`docs/13-open-questions.md` question 46): design register row B19 in
   `docs/prompts/README.md`, and the back-dating check of row B12 on every petty-cash write
   (prompt 07b adds the setting, its helper and the 20 petty-cash rights). D0 designs them
   beside the inventory; where the notes and .NET differ, the notes decide.
3. `docs/01-architecture.md` sections 3, 7, 9; `docs/03-database.md` sections 4, 5, 6;
   `docs/09-testing.md` section 4 (the `PettyCashTests` row).
4. The code from prompts 00 to 07, in particular `tenancy.require_any_permission`,
   `tenancy.record_change`, the visibility predicate of `api.history_list`, `setup.vehicle_net`,
   `api.setup_vehicle_report`, `http/messages.py`, `http/errors.py` (the `current`
   extension member of the revenue 409 is the pattern to reuse), `tests/support/scenario.py`.

Do not read the C# sources except in D0.

## Environment

As prompt 01. `git status` first; write only under `apps/api-python/`.

## Deliverables

### D0 Verification pass (before any code)

- Start from row 7 of the drift register in `docs/prompts/README.md` (bulk approve,
  approve-day `to`, the overview's waiting figures, the optional credit-note payee):
  commit 9276c51 and the uncommitted working tree changed the feature after
  `inventory-petty-cash.md` was written, so the inventory is known to be stale. The
  screen export (row 4) belongs to 08b.
- Find the commit (or the working tree, if still uncommitted) that holds
  `apps/api/Domain/PettyCash.cs`, `apps/api/Application/PettyCashUseCases.cs`,
  `apps/api/Application/PettyCashContracts.cs`, `apps/api/Api/PettyCashEndpoints.cs`,
  `apps/api/Infrastructure/PettyCashRepository.cs` and `tests/api/PettyCashTests.cs`.
  Compare their modification times and `git log -1` with the appendix of
  `inventory-petty-cash.md`. For every file that changed after the inventory's reading
  time, read the diff (`git diff <inventory commit>..HEAD -- <file>` or the file region
  the inventory cites) and correct the inventory's rules, check orders, DTO fields and
  messages in place, listing every correction in the report. This is the only step that
  reads C#.
- Then re-check `docs/04-schema.md` section 6.2, `docs/05-routines.md` section 4.9 and
  `docs/06-http-contract.md` section 2.11 against the corrected inventory and fix them in
  the same change.

### D1 Migration `0012_pettycash.sql` (0008 to 0011 are prompt 07b's, `docs/04-schema.md` section 13)

- Schema `pettycash` (`AUTHORIZATION xcode_owner`, `USAGE` to `xcode_api_executor`), code
  tables `pettycash.kinds` and `pettycash.statuses` with their rows, table
  `pettycash.entries` exactly as `docs/04-schema.md` section 6.2 (generated `total`,
  the three `CHECK`s, partial indexes, composite foreign keys, RLS and `tenant_isolation`,
  `INSERT` and `UPDATE` grants only), `updated_at` trigger not used (the column is set by
  the routines, as in .NET).
- Evidence: `tests/db/test_schema_structure.py` and `test_constraints.py` extended (one
  failing insert per `CHECK`: a cash entry with a vehicle, an expense without an item, a
  credit without a payee, a sent-back entry without a note, a removal with no reason, a
  zero total); `test_enum_parity.py` for the two code tables; `db verify` exit 0.

### D2 Helpers and routines (`db/routines/55_pettycash/`)

- Every helper and routine of `docs/05-routines.md` section 4.9 with the check orders of
  `inventory-petty-cash.md` section 4.3 and the rules `PC-1` to `PC-32`; the line checks in
  the order of section 2.3 with the exact sentences as codes `pettycash_line_<n>` named
  after their meaning (`pettycash_line_date_required`, `pettycash_line_amount_zero`, ...),
  listed in `http/messages.py` (D4).
- Replays: create with a known own `id` answers `replayed` without reading the body;
  change with a matching line (status not sent back) answers `replayed` before permission
  and version checks; approve and send back replays per `PC-16`; the client-supplied `id`
  is the only client id in the system (`docs/04-schema.md` section 6.2).
- Approved expenses post into the vehicle report (`PC-31`) through `setup.vehicle_net` and
  `api.setup_vehicle_report` (`source = pettycash`, bucket from the item's category);
  the visibility predicate of `api.history_list` admits `pettycash` rows for scoped viewers
  only with a visible `vehicle_id` (`PC-32`).
- Evidence: `tests/db/test_pettycash_helpers.py` (balance, holders, visibility for the
  three scope kinds, `can_change` and `can_review` truth tables from `PC-13` and `PC-14`,
  week bounds for each first day of week, the rounding vectors of `PC-3`:
  `11.875 x 182.40 = 2166.00`, `4.5 x 1250.50 = 5627.25`, `0.125 x 0.1 = 0.01`,
  `1.005 x 1 = 1.01`), `tests/db/test_pettycash_routines.py` (one test per numbered step of
  section 4.3 per endpoint, every `PC` rule, the 17 line checks, the float guard for cash
  given, taken back, changed and removed with and without `issue_negative`, the replays,
  the version conflicts with `current`, approve-day skipping, the reason sentences byte
  for byte including `Removed Wanjiru Kamau's petty cash spending on KAA 501A for 9 Oct 2026. Reason: Recorded twice.`
  and `Recorded petty cash given to Wanjiru Kamau`, snapshots with the PascalCase keys,
  the change-log `vehicle_id`, the vehicle report posting, the history visibility rule),
  and the behaviours `inventory-petty-cash.md` section 5.4 says no .NET test covers
  (search `q` with `%` and `_`, status filter, `from > to`, paging bounds, the 80, 200 and
  500 limits, the ten-year window, kind and holder change refusals, audit rows).

### D3 Domain, ports, gateway, fakes

- `domain/pettycash.py` (`PettyCashKind` and `PettyCashStatus` as `IntEnum`s with their
  wire words, `PettyCashEntry`, `SavePettyCashEntry` command, the overview, float, figures,
  options and dashboard records, `PettyCashSaved` with `outcome`); `application/repositories.py`
  `PettyCashRepository`; `db/routines/pettycash.py` `PettyCashRoutines`;
  `tests/support/fakes.py` `FakePettyCashRepository` with parity cases for a create, a
  create replay, a change conflict, an approve and a removal under the float guard.

### D4 Messages, use cases and HTTP

- `http/messages.py`: the petty-cash block of `docs/06-http-contract.md` section 3 (every
  sentence of `inventory-petty-cash.md` sections 2.3, 2.4 and 4.3; the 409 titles
  `This entry has changed.` and `This entry was changed by another save.` with their
  details; the `balanceAfter` 400); `test_message_codes.py` green.
- `application/pettycash/*` use cases (one per endpoint); `http/schemas/pettycash.py`
  with the DTOs of `inventory-petty-cash.md` section 4.4 in wire order (`kind` and
  `status` as words, `bucket` as an integer, `float` served from a field named `float_`,
  the `from`/`to` query parameters aliased); `http/routers/pettycash.py` under
  `/setup/pettycash` with the tag `Petty cash`, the operation ids of section 4.2, 200 for
  create (never 201), the `kind` and `status` comma lists parsed as the inventory says, the
  409 bodies with `current` (null for a foreign id) and the 400 with `balanceAfter`.
- Evidence: `tests/api/test_petty_cash.py`: every row of `PettyCashTests` in
  `inventory-petty-cash.md` section 5.2 as a scenario with the same assertions, plus the
  client expectations of section 6 (web and mobile paths, statuses, messages, dashboard
  cards), the statement budget 2 per request, DTO names and order, and the vehicle report
  showing the approved expense.

## Invariants at the end

- Every rule `PC-1` to `PC-32` has a test naming it; the seventeen line checks run in the
  inventory's order with its sentences.
- `pettycash.entries` is never deleted; `total` is never written by a routine (generated);
  the kind shape, review and removal rules hold on every path (constraint tests).
- The client-supplied `id` is accepted only by `api.pettycash_entry_create`; no other
  routine takes an id it did not generate.
- Lint, types, all tests green; `db verify` exit 0; no TODO/FIXME; no plan or prompt ids.

## Verify (paste the outputs into the report)

```
cd apps/api-python
ruff check . && ruff format --check . && mypy
pytest <the test modules you touched> -q
pytest -n 3 -q -p no:cacheprovider > <scratchpad>/full.log 2>&1
xcode-api db migrate && xcode-api db routines && xcode-api db verify ; echo "exit=$?"
```

Run the touched modules while you work and the full suite once at the end, in the
background, with its log in your scratchpad; report passed, failed, skipped and errors
from the log. Before that run, drop `xcode_template` if you changed a migration or routine
file, after checking that no other session's run uses the cluster (`docs/09-testing.md`
section 5).

## Challenge pass (before the report)

Apply `docs/14-verification.md` to your own work as if nobody, including you earlier in
this session, had reviewed it:
1. Steelman: list every deliverable bullet and invariant above as a claim, with the code
   that carries it.
2. Falsify: for each claim, name the observation that would disprove it and look for it;
   grade the evidence (section 5). Tenancy, security and integrity claims need grade A.
3. Run the five modes over D1, D3, D4, D5, D6 and D7, with the gamer persona first (self-approval, float inflation, reopened days, splitting under a limit), plus D10 (tests as evidence) and D11 (documents);
   give every probe of section 4 for those domains a verdict.
4. Try to refute each finding; fix the survivors with a test that fails first, or record
   them (corrected document, open question, residual risk).
5. Report the findings table (section 7), the conceded challenges with the guard that
   defeated each, and the three hardest attacks for any domain without findings.

This pass does not replace the separate `verify.md` run on this prompt; it makes that run
cheaper.

## Report format

1. D0 first: the reference commit, every inventory and document correction with the .NET
   `file:line` that caused it.
2. Checklist: one row per deliverable D1 to D4 and per bullet: done or not, `file:symbol`,
   test name.
3. Verify outputs, trimmed.
4. Deviations from the documents with reasons; document lines changed.
5. Items left for later prompts.

Add the challenge-pass results and the drift-check corrections as the last section of
the report.

## House rules

- Shared tree: `git status` first; edit only under `apps/api-python/`; never revert or
  reformat others' changes; never kill processes you did not start; never bare `git stash`.
- No commits unless the user asks. No AI attribution anywhere.
- No comments unless needed; routine files carry the header the conventions require and
  nothing decorative; no plan or prompt identifiers anywhere.
- Never weaken a test to make it pass. If a document is wrong, fix the document and report
  it.
