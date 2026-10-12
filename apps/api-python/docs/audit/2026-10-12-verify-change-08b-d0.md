# Verify: the 08b design change (D0 documents), report mode, 2026-10-12

Parameters: `SCOPE: change:<the 08b D0 documents>` (the files of the board's 19:33 entry:
`docs/inventory/inventory-expenses-reports.md`, `docs/04` 14, `docs/05` 11, `docs/06` 2.13, `docs/02` ADR-16,
`docs/12` 2.8 and section 7, `docs/09` 4.2, `docs/10` 3.2, `docs/13` questions 74 to 80, `docs/15` B18 and
`DEC-30` to `DEC-46`, `docs/11`, `docs/inventory/README.md`, `docs/prompts/README.md`, the 08b prompt, and the
design report `docs/audit/2026-10-12-design-08b-d0.md`), `MODE: report`, `DEPTH: standard`.

Who ran it: revenue-ff [9fea06], the session that wrote the D0 documents, after its context was compacted, at
the user's request (`verify.md` asks for a session of its own; the user chose speed). Every fact below was
measured in this run, none copied from the design report, which was read only for section 9. A fresh session
may re-run this scope; nothing here stops the build.

## 1. Verdict

**pass with findings.** Findings: 0 blocker, 0 major, 4 minor, 4 notes (section 3). Claims: 19, of which
10 hold, 4 fail (each to a minor or a note), 3 are unproven by nature (document claims about code that does not
exist yet; grade D until the build's tests), 1 is n/a (build invariants), 1 not checked (licence rows of the
ADR; no network in this run).

The scope holds no code, so the full-suite requirement is met by the measured log of D4's shared run on the same
code tree (section 8: 3 failed, 5733 passed, 1:55:20, ended 19:31; the three failures are D1's
`tests/db/test_gateway.py`, outside this scope and already owned on the board), plus this run's 432 passed of
the three doc-parsing unit modules (the documents break no parser). Nothing under `src/` or `db/` changed after
19:31; under `tests/` two files changed at 20:39 and 20:47 by their own sessions.

The four minors are one-line document corrections (section 7 gives the words); the build session folds them in
as its first step (its gate B0 b) and needs no second verify for them.

## 2. Thesis and claims

Thesis: the 08b design documents describe, completely and without contradiction, what the .NET API gained on 9
and 10 October 2026 (drift rows 1 to 6, 8, 12 and the new row 14) and where Python follows the design notes
instead, so that a build session reading only those documents (no C#) produces routes, routines, tables and
tests equal to .NET's behaviour at `HEAD` 493bf82 plus the working tree, with the notes' rules B18, B9, B15,
B16 and B12 on top.

Evidence words: "read" means measured in this run against the file named; "D" means the only evidence is the
document itself (the method's grade for words).

| # | Claim | Where stated | Checked against | Verdict |
|---|---|---|---|---|
| C1 | The inventory names its reference commit and every uncommitted file whose facts it cites | inventory basis and appendix | `git status --short apps/api tests/api` (27 entries); the two cited files absent from the appendix (`PettyCashRepository.cs`, `PettyCashUseCases.cs`) have their uncommitted hunks at lines 145 to 156 and 72 to 498, and the inventory cites `PCR:18-24`, `:112-133` and no `PCU` line, so no cited fact comes from an unmarked uncommitted line; no commit after 9276c51 touches `apps/api` or `tests/api` | holds (read) |
| C2 | Every rule id carries a .NET `file:line` that says what the rule says | inventory section 2 | 25 of the 69 cites re-read (CE-1 to CE-4, CE-9, CE-12 to CE-14, CE-17, CE-23, SR-2, SR-3, RP-2, RP-9, RP-11, RP-14, RP-15, RD-1, RD-4 to RD-6, FP-2): every sentence and constant matched (`MaxVehicles` 50, `ReasonLength` 500, `MaxRows` 10 000, `MaxDays` 367, the day limit 500) | holds (read; 44 cites not re-read) |
| C3 | Every route with method, path, permission, check order, status codes, DTOs in wire order, messages verbatim, operation id and tag | inventory section 4, `docs/06` 2.13 | all 83 `WithName`/`ProducesExport` ids of `apps/api/Api/*.cs` appear in `docs/06`; the 16 routes of the scope match in method, path, tag and id; the DTO records of `CentralExpenseContracts.cs`, `ReportContracts.cs`, `SetupContracts.cs:89-101` and `RevenueDayContracts.cs` match 2.13's orders; 38 sentences matched byte for byte; the check order of `BuildPettyCash` differs from `docs/05` 11.4 | fails: V-D4-1 (minor); the rest holds (read) |
| C4 | The tests that pin each rule, with their counts | inventory section 5, `docs/09` 4.2, README row 12 | `[Fact]` count of `CentralExpenseTests.cs:40-812` is 17, the documents say 15; the other five classes' counts match (13, 4, 4, 3, 5) | fails: V-D11-1 (minor) |
| C5 | What the web, mobile and shared clients read | inventory section 6, `docs/06` 2.13.7 | the nine cited client files exist with the cited line ranges (`exportReport.ts:28-49` reads `detail` and names the file itself; `useFleetDay.ts:118-119` reads the 409's `vehicleId`; `shared/src/revenue.ts:238-264` holds the day types; `reports.ts:146-161` the three export paths); `apps/mobile/src` has no call to the routes | holds (read) |
| C6 | The new tables with constraints, RLS, grants, append-only rules and an index per query | `docs/04` 14 | internal consistency read: `btree_gist` in `ops` since `0005:6`, the away-period exclusion syntax at `0005:118`, the membership FK form of `0012:64-74`, `recurring_versions` PK `(organization_id, id)`, the code-table grant pattern `0005:400`, the `ck_change_log_vehicle` form of `0012:136-140`, frequencies 1 to 4 in `setup.recurrence_frequencies` and in `recurring_due_days`; the tables themselves exist only on paper | unproven (D) |
| C7 | The helpers and `api.*` routines with check orders and budgets | `docs/05` 11 | all 23 existing functions section 11 calls exist (`setup.report_window`, `vehicle_active_on`, `revenue.vehicle_days`, `tenancy.check_page`, `check_money`, `fmt_money`, `pettycash.check_line`, ...); `tenancy.current_actor()`/`current_organization()` (`0003_tenancy.sql:7-11`, used by 14 routine files) carry the actor and organization the `revenue.capture_entry` signature leaves out; the 61 new names collide with nothing; two notes (V-D6-1, V-D10-1) | unproven (D) |
| C8 | The HTTP sections, the message block and the client facts | `docs/06` 2.13 | the 43 planned codes collide with no entry of `messages.py` (0 of 43) and no row of section 3; the four 403 sentences use the labels of `0009_access.sql:141-173` (`Edit an expense`, `See the investment report`, `View petty cash reports`) in place of .NET's, as the inventory's section 7 records | holds (read) |
| C9a | The ADR's measurable claims: pure Python, the invariant switch, fixed zip times, the formula guards | `docs/02` ADR-16 | the wheels on this machine: reportlab 5.0.0 has 0 compiled modules and `rl_config.invariant`; it requires `charset-normalizer` and `pillow`; XlsxWriter 3.2.9 fixes every part's zip time at 1980-01-01 (`workbook.py:813-814`) and has `strings_to_formulas` and `quote_prefix` | holds (read; the ADR names 5.0.1, the pin is the build's) |
| C9b | The licence column and the fpdf2 and WeasyPrint rows | `docs/02` ADR-16 | no network in this run; not re-read from wheel metadata | not checked |
| C10 | The controls of `docs/12` 2.8 and their tests | `docs/12` 2.8 | the "Proven by" cells name tests that do not exist yet, as 2.8 says itself | unproven (D) |
| C11 | The crosswalk rows for the test classes of drift row 12 | `docs/09` 4.2 | every class of row 12 has a row; the count of C4 | fails: V-D11-1 (the same minor) |
| C12 | The data-migration rows for the new tables | `docs/10` 3.2 | rows 32 to 37 name every table of `docs/04` 14; row 36 keeps a migrated saving's end while `docs/05` 11.3 refuses any end on a saving's save | fails: V-D11-2 (minor) |
| C13 | Every decision not takeable on the merits is an open question with a default | `docs/13` questions 74 to 80 | seven questions, each with a default and what it blocks; question 73 answered by `DEC-40`; one business rule the design did not raise is V-D5-1 | holds (read) |
| C14 | Drift rows 1 to 6 and 8 marked, additions registered | README drift register | rows 1 to 6 "documented by 08b D0"; row 8 "checked against `ListFilterTests` by 08b D0: nothing missing"; row 12 annotated; row 14 new; the status row names the report and the next step | holds (read) |
| C15 | The prompt amended (`0013`, the D6 bullets per `DEC-42`) | `docs/prompts/08b-expenses-reports.md` | D1 heading `0013_expenses.sql`; the day-capture bullet names `revenue.capture_entry` and 10.5's steps | holds (read) |
| C16 | The build invariants (routes in routers and OpenAPI, nothing summed outside SQL, exports scoped and logged, lint, tests, `db verify`) | the prompt's "Invariants at the end" | no code exists | n/a (the build's) |
| C17 | B18 and the report parts of B9, B15, B16 and B12 are designed from the notes | `docs/15` B18, `DEC-30` to `DEC-46` | DN-B18-1 to 10 and 17 decision rows read; each names its `docs/0x` section and that section exists | holds (read) |
| C18 | The design report's own counts and fixes | `docs/audit/2026-10-12-design-08b-d0.md` | its V-D11-1 is fixed (`docs/05` 11.4 names `report_investment_permission` and `report_pettycash_permission`); its "47 planned message codes" (line 86) counts 43 rows | fails: V-D11-3 (note) |

Counts: 19 claims; holds 10, fails 4, unproven 3, n/a 1, not checked 1.

## 3. Findings

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| V-D4-1 | falsification | `docs/05` 11.4 `api.report_get`: "the report's own right; the period (dated reports); a `holder_id` not among the person's floats -> `XC404`" | .NET checks the holder before the period: a petty-cash report with a foreign `holderId` and no `from` answers 404 in .NET and, as documented, 400 in Python | `ReportUseCases.cs` `BuildPettyCash`: the right (403), then `holderId` (`KeyNotFoundException`), then `Period(...)` | read the fleet branch too: there the investment right precedes the period and no holder exists, so only the petty-cash order is wrong; a client sends both wrong only by accident, so no released screen hits it | survives, minor | doc corrected (section 7: swap the two clauses for petty-cash reports) |
| V-D11-1 | falsification | inventory section 5 and `docs/09` 4.2: `CentralExpenseTests` (15) | the class has 17 `[Fact]` methods; a build session that ports "15 scenarios" and stops counting misses two | `sed -n 40,812p tests/api/CentralExpenseTests.cs \| grep -c "\[Fact\]"` = 17; the inventory's own "what they pin" cell lists all 17 | the cell enumerates every method, so the crosswalk is complete and only the number is wrong | survives, minor | doc corrected (section 7: 15 -> 17 in both places) |
| V-D11-2 | pre-mortem | `docs/10` 3.2 row 36 keeps a migrated saving's `End` ("`DEC-33` refuses new ones only"); `docs/05` 11.3 refuses any end on a saving's save (`recurring_savings_end`) | three months after cutover an owner opens a migrated saving that had an end date and saves a renamed version; the released web sends `end` as today (`docs/06` 2.13.7), the routine refuses, and the saving cannot be revised until its end is cleared, which the saving pop-up has no control for (question 74) | the two documents disagree on their face; `docs/06` 2.13.7 says the web sends `end` as today | looked for a rule that a revise keeps the stored end: 11.3 says only "a saving with an end date -> `recurring_savings_end`" | survives, minor | doc corrected (section 7: refuse an end that is new or different from the stored one; or the migration clears a saving's end and says so in row 36); for the user (section 10) |
| V-D5-1 | red team (persona 8, the gamer) | `docs/05` 11.6: a shared petty-cash purchase is one entry per vehicle, "each part is approved, rejected and reopened on its own" | a holder records a 100,000 purchase over 50 vehicles; each 2,000 part sits under an approver's limit (`This entry is above your approval limit.`), so the limit, which is per entry, never sees the purchase | `docs/05` 11.6; `PettyCashUseCases.cs:338` (the limit is per entry in .NET too) | parity: in .NET a holder can already record fifty separate entries by hand; the group only makes it one form; the approver sees `group {size, total}` on each part (`docs/05` 11.6, `docs/06` 2.13.4) | survives, minor (business rule not decided; parity, so no fix) | open question 82 with the default "the limit applies per part; the approver sees the purchase total on each part", reserved under the board's Numbers before writing; for the user (section 10) |
| V-D11-3 | falsification | the design report: "47 planned message codes" (`docs/audit/2026-10-12-design-08b-d0.md:86`) | 2.13.6 holds 43 rows | `awk '/2.13.6/,/2.13.7/' \| grep -c` = 43 | none possible | survives, note | doc corrected (the report's line 86; the build report counts what it adds) |
| V-D6-1 | dialectic | `docs/05` 11.1: `setup.posting_window` = "`setup.report_window` under the name the postings use" | the two formulas are identical (`report_window.sql:19-34`: `greatest(from, joined_on)` to `least(through, today)` cut to `left_on - 1`, away days not excluded), so the design adds a second function for one piece of knowledge (`docs/00` section 1) | `report_window.sql`; FP-2 | looked for a difference: none in the text of 11.1 | survives, note | doc corrected (section 7: call `report_window`, or state the difference) |
| V-D10-1 | Socratic | `docs/05` 11.5: the day save "re-raises a 400-class refusal with `vehicle_registration` added to its `DETAIL`" | `tests/db/test_routine_headers.py:144-147` forbids `RAISE` in any body but `tenancy.refuse`, and `Raises:` lists only literal codes; a build that writes `RAISE EXCEPTION USING ...` fails that test | the test file | the design is implementable without `RAISE`: catch, `GET STACKED DIAGNOSTICS`, then `tenancy.refuse(SQLERRM, SQLSTATE, detail \|\| ...)` with the caught code; the header then lists the pass-through codes `via revenue.capture_entry` | survives, note | doc corrected (section 7: say "through `tenancy.refuse` with the caught code and SQLSTATE") |
| V-D11-4 | falsification | `docs/13` is current | question 81 (a retired vehicle keeps its fleet number, D3's, decided at 20:46) sits in the table headed "Raised by the design of prompt 08b"; the board's Numbers line still says "next free is 71" | `docs/13-open-questions.md:134-146`; board line 209 | another session's edit at 20:49, outside this scope | survives, note | for the docs pass: move question 81 under a heading of its own; the board's Numbers line to 82 |

## 4. Per domain

Domains the prompt names for the design session: D1, D3, D4, D5, D6, D7, D9, plus D10 and D11.

### D1 Tenancy and authorization (no finding; the three hardest attacks are below)

| Probe | Verdict | Evidence |
|---|---|---|
| Every tenant-scoped routine calls `tenancy.enter_organization` first | unproven | `docs/05` 11 says so for every `api.*` row; no routine exists |
| Every tenant table has RLS and `tenant_isolation` | unproven | `docs/04` 14.2 to 14.4 say RLS on the five new tenant tables; the code table has none, as section 2's |
| Scoped viewers' totals, counts, exports, options, history | unproven | `docs/12` 2.8 rows 2, 3, 7 and their named tests (not written) |
| Every `{id}` route proves the id is the caller's | unproven | 11.2 (`XC404` on a row not visible), 11.3 (item visible by the kind's view right), 11.4 (`holder_id` 404) |
| Anti-escalation in SQL | n/a | no grant changes in scope |
| The permission catalogue equals `packages/shared` and `MODS` | holds (read) | the sixteen rights 2.13 names exist in `0009_access.sql` with the labels the sentences use |

Hardest attacks: (1) a scoped viewer reading the purchase total of hidden vehicles through `group.total` on a
ledger row: .NET shows the same (CE-21), so it is parity, recorded as conceded; (2) `reports` change-log rows
hidden from scoped viewers: the residual risk is in `docs/12` 7; (3) a `holderId` of another organization on a
petty-cash report: 404 by 11.4, never a figure.

### D3 Data integrity and concurrency (no finding)

| Probe | Verdict | Evidence |
|---|---|---|
| Every `version` bumped and compared, 409 with `current`, two connections | unproven | 11.2 (`expense_version_conflict` with `current`), the named two-connection test |
| Lock order, implicit FK locks | unproven; argued | 11.1's rule (vehicle row before the vehicle's advisory lock, ascending ids); an insert into `saving_runs` takes `FOR KEY SHARE` on the vehicle, item and version rows, which conflicts with nothing a revise holds (`FOR NO KEY UPDATE` on the old version's close, `FOR SHARE` on the item); `decide_saving_runs` takes no row lock after the advisory lock |
| Replays rely on a unique constraint; two identical first writes make one row | unproven | 11.2 (the purchase advisory lock before the lookup, the unique on `(organization_id, group_id, vehicle_id)` as the backstop); 14.3 (`ON CONFLICT DO NOTHING` on the run's key) |
| Append-only by grant | unproven | 14.3 (`saving_runs` `INSERT` only), `test_grants.py` named |
| Money `numeric(14,2)`, one rounding, no overflow | holds (read) for the types; unproven for the sums | 14.2 (`round` half away from zero once, in the generated `total`; the `check_line` "total too large" guard before an insert) |
| One call one transaction; exports idempotent | unproven | 11.4's last paragraph |

Hardest attacks: (1) two day saves in opposite sent orders: rows run in ascending vehicle id, each record lock
is `NOWAIT` (10.5's step), the advisory lock comes after the vehicle row, so the second save answers
`revenue_concurrent_save` instead of waiting, no cycle exists; (2) a run decided twice by a capture and a
`save_recurring` racing: the per-vehicle advisory lock serialises them and the second insert hits
`ON CONFLICT DO NOTHING`; (3) a saved run counted twice in the balance when dated on the opening date:
`DEC-35` says "dated after the opening date".

### D4 Contract parity

| Probe | Verdict | Evidence |
|---|---|---|
| Routes: .NET table, `docs/06`, routers, OpenAPI | holds (read) for .NET versus `docs/06`; n/a for routers and OpenAPI | 83 of 83 operation ids; 16 of 16 routes with method, path, tag |
| Bodies: names, order, nullability, numbers | holds (read) | the DTO records of section 2, C3 |
| Errors: titles, details, empty bodies | holds (read) for the scope's sentences; fails for one check order | 38 sentences; V-D4-1 |
| Clients | holds (read) | C5 |
| Drift register current | holds (read) | C1, C14 |

### D5 Domain rules and time (no finding beyond V-D5-1, which is a business rule)

| Probe | Verdict | Evidence |
|---|---|---|
| Business dates from `tenancy.business_date` and `p_now` | unproven | every routine of 11 takes `p_now`; `scheduled_runs` and `decide_saving_runs` take `p_today` |
| Week start, month ends, 29 February, day 28, time zones | unproven; argued | due days come from `setup.recurring_due_days` (06's, tested) with a pause filter added; `DEC-33` starts a new saving on the business date, so a monthly saving set up on the 28th first runs next month, as the notes want |
| Reasons and snapshots byte for byte | holds (read) for CE-15 and CE-16's text; the pause reason follows DN-B17-3, not .NET | `docs/05` 11.2, `docs/15:213` |
| Normalisation parity | n/a | no new normalised input |

### D6 Database craft (one note)

| Probe | Verdict | Evidence |
|---|---|---|
| `db verify` exit 0 per check | n/a | no migration exists; the build's |
| `SECURITY DEFINER` with `search_path`, `EXECUTE` revoked, no stale overload | unproven; the design names six signatures `0013` must drop | the build plan; 11.1 drops the two `vehicle_postings` |
| No dynamic SQL from input | unproven | 11.2 (ILIKE with `%`, `_`, `\` escaped), 11.4 (`reports.cell_text` matched in SQL) |
| Migrations forward-only with a reviewed `.down.sql` | unproven | 14.7 |
| An index per query | holds (read) for the design | 14.2 (three indexes plus the unique and the PK, one per query of 11.2), 14.3 |
| Features newer than the oldest supported PostgreSQL | holds (read) | generated columns (12), `hashtextextended` (11), gist exclusion with `btree_gist` (9.6), `ON CONFLICT` (9.5); local 16.15, CI `postgres:18` |
| The test template's fingerprint | n/a | no `db/` change |

### D7 Performance and scale (no finding; the open item is the design report's V-D7-1)

| Probe | Verdict | Evidence |
|---|---|---|
| Statement budgets per endpoint | unproven | 11.7: 2 per route |
| `EXPLAIN` at 10x the seed for the heavy reads | not checked | `docs/perf/` holds `revenue.md` only; 11.7 lists the files the build owes |
| No query per row inside a loop | unproven; argued | `scheduled_runs` is set-based over `unnest`; the ledger is one statement; the day save loops rows by design (one capture each, bounded at 500) |
| Exports bounded in rows, bytes and time | unproven | `DEC-45`: 10 000 rows, the role timeout, a worker thread |

Hardest attacks: (1) a year of gaps over a large fleet in one `gaps` export: the 10 000-row cap refuses it with
its sentence before any byte; (2) the ledger's figures over 367 days with the scheduled runs generated for every
visible vehicle: bounded by the period and the fleet, measured only by the owed `EXPLAIN`; (3) the summary's
`costs_due` to the month's end for every item: one `scheduled_runs` call over the month, set-based.

### D9 Hosting and supply chain (no finding)

| Probe | Verdict | Evidence |
|---|---|---|
| The deployment target can run the libraries | holds (read) for the measurable part | reportlab 5.0.0 ships no compiled module; its `pillow` wheel is manylinux; ADR-16 names the fallback |
| Lock files with hashes, `pip-audit`, pinned actions | n/a | the build's |
| The TLS rule | n/a | untouched |

Hardest attacks: (1) a Pillow wheel the host cannot install: the ADR's revisit clause keeps the hand-written PDF
writer behind the same port; (2) a library withdrawn: the adapter is the only importer; (3) a font read from the
system: the ADR forbids it (package data only).

### D10 Tests as evidence

| Probe | Verdict | Evidence |
|---|---|---|
| No fake of the capability under test | unproven | `docs/09` 4.2 puts every rule in `tests/db` and the parity in `test_fakes_match_routines.py` |
| `skip`, `xfail`, `sleep`, broad `except` in the scope's tests | n/a | no test exists |
| A test named after a rule asserts its distinguishing output | unproven | the names of `docs/12` 2.8 and `docs/09` 4.2 say what they assert; V-D10-1 is the one wording that could trip a build |
| Every `Raises:` code has a test | unproven | 11's "Raises, in order" cells; the build's rule |
| The full suite ran on a fresh template | holds (measured) | D4's shared run: 3 failed, 5733 passed, 1:55:20 (section 8); this run's three modules: 432 passed |

### D11 Documents and prompts

| Probe | Verdict | Evidence |
|---|---|---|
| Every doc clause the scope touches matches the code | fails for the counts, holds otherwise | V-D11-1, V-D11-3; the helper names, rights, constraint forms and client lines of C5 to C8 |
| Section references in the prompt resolve | holds (read) | `docs/01` sections 3, 4, 7, 8, 9; `docs/09` section 5; `docs/16`; `docs/06` 1.6 and 2.12; `docs/05` 10.5; `docs/15` B18 |
| `docs/13` and the README status are current | holds, with V-D11-4 | questions 74 to 81; the README status row names the report and the next step |
| Claims in memory notes and earlier reports re-measured | holds | section 9 |

## 5. Per mode

### Assumptions inventory

| Assumption | Where | Enforced by |
|---|---|---|
| A helper reaches the actor and organization without parameters | 11.5's `revenue.capture_entry` signature | `tenancy.current_actor()`, `current_organization()` (`0003_tenancy.sql:7-11`) |
| `btree_gist` is installed for the pause exclusion | 14.3 | `0005_setup.sql:6` (`WITH SCHEMA ops`) |
| Savings may run daily to yearly without a schema change | 11.3 | `setup.recurrence_frequencies` rows 1 to 4; `recurring_due_days` handles all four; the schedule check at `docs/04:536-539` allows daily |
| A new helper may call a later-sorting file | 11 (folder order) | nothing: a `LANGUAGE sql` body is checked at creation, so such a helper must be plpgsql (the build plan's rule) |
| A scheduled run is unique per (item, day, vehicle) without a table | `DEC-32` | by construction: one version in charge per day, one share per version and vehicle |
| The web never sends an end for a saving | 2.13.7 | only for a saving saved with "No end date" ticked; a migrated end breaks it (V-D11-2) |

### Falsification table

| Claim | Falsifier looked for | Result | Grade |
|---|---|---|---|
| Every .NET route of the scope is in `docs/06` with its id | an id of `apps/api/Api/*.cs` absent from the file | 0 of 83 absent | read |
| Every sentence of 2.13.6 is .NET's or marked | a .NET sentence of the scope not in 2.13.6, or a 2.13.6 sentence not in .NET and unmarked | 38 matched; the four 403s and the four "(new)"/"(p)" rows are marked | read |
| The 43 codes collide with nothing | a code already in `messages.py` or section 3 | 0 collisions | read |
| Every existing function section 11 names exists | a name without a file | 23 of 23 exist; 61 new | read |
| `CentralExpenseTests` has 15 methods | a different `[Fact]` count | 17 | read; V-D11-1 |
| `api.report_get`'s order is .NET's | a check out of order in `ReportUseCases.cs` | the petty-cash holder precedes the period | read; V-D4-1 |
| XlsxWriter fixes zip times | wall-clock `ZipInfo` dates | fixed at 1980-01-01 | read |
| The ADR's tables came from measured wheels | a claim the installed wheels contradict | none among the measurable ones; 5.0.1 named, 5.0.0 installed | read |
| The full suite is green on the tree the documents sit on | failures outside D1's known three | none | measured |

### Pre-mortem narratives (likelihood x impact; with the inversion)

1. **A migrated saving cannot be revised** (V-D11-2). Trigger: a saving with an end date migrated under row 36;
   the owner renames it in month two; the web sends `end`; `recurring_savings_end`. Noticed at the first edit.
   Inversion: what guarantees failure is "row 36 keeps the end" plus "11.3 refuses any end"; both stand today.
   Mitigation: section 7's wording.
2. **The build writes `RAISE EXCEPTION USING` in the day save** (V-D10-1) and spends an hour on the header
   test. Inversion: the condition exists (11.5's word "re-raises"). Mitigation: section 7's wording.
3. **A 10 000-row PDF built on a 4-core host beside the web** (ADR-16, `DEC-45`): seconds of a worker thread per
   export, the event loop free; the cap and the role timeout bound it; noticed by the owed `EXPLAIN` and the
   build's timing test. Inversion: failure would need no cap or an unbounded period; neither exists on paper.

### Red-team vectors

| Persona | Vector | Defence or gap |
|---|---|---|
| Clerk in tenant A | reads hidden vehicles' money through a report's headline or `totals` | every figure from `setup.fleet_postings` over `setup.visible_vehicles()` (11.4); the named scope tests |
| Clerk in tenant A | a foreign `holderId` on a petty-cash report or export | 404 (11.4); V-D4-1 only moves the order |
| The gamer | a note starting with `=` in an export | `write_string`, the three `strings_to_*` off, `quote_prefix` (ADR-16, `docs/12` 2.8) |
| The gamer | splits a purchase to sit under the approval limit | the gap of V-D5-1 (parity; for the user) |
| The calendar | a monthly saving set up on the 31st | `recurring_due_days`' day 28 and last-day rules; `DEC-33` starts it on the business date |
| Hurried DBA | runs `0013.down.sql` over data | the `DO` block refuses while `centralexpenses` or `reports` rows exist (14.7) |

### Dialectic

| Decision | Strongest counter | Verdict | Confidence |
|---|---|---|---|
| `DEC-31` runs decided by writes under an advisory lock | deciding on read needs no lock and no caller list; a forgotten caller leaves runs held for ever | kept: a read must not write, and the caller list is closed (capture, day save, `save_recurring`, vehicle update, restore); the "held for ever" case is the recorded residual | high |
| `DEC-32` computed cost runs | a stored posting row per run would make the ledger a plain table scan and the audit simpler | kept: .NET stores none, a computed run is never stale, only decided runs need permanence | high |
| `DEC-40` `reports.view` opens savings figures | gate the Savings report by `savings.view` | kept as the prototype's `MODS`; the residual risk is in `docs/12` 7, owner product | medium |
| `DEC-42` rows in ascending vehicle id | the client's first bad row is not the first error it sees | kept: the shape step runs first in sent order, and the web marks whichever row the 400 names | high |
| `DEC-45` one transaction per export, capped | a report export in .NET has no cap; a long gaps report may need more than 10 000 rows | kept: an uncapped export is the one unbounded read of the API; "choose a shorter period or search" is the sentence | high |
| ADR-16 ReportLab over a hand-written PDF | zero dependencies, no Pillow | kept: the CID font embedding is the part a reviewer cannot check by eye; the fallback stays behind the port | medium |
| V-D6-1 `posting_window` as a name | a name that says what the postings use reads better in 11.1 | changed: one function (`report_window`) unless the build finds a difference | high |

## 6. Conceded challenges

| Challenge | Guard that defeated it |
|---|---|
| The pause and resume reasons are not .NET's (`Paused {name} from {date}`) | DN-B17-3 (`docs/15:213`) prescribes `Saving, [name]` / `Scheduled expense, [name]` for every scheduled-item entry; `DEC-43` records it |
| The four 403 sentences are not .NET's | the inventory's section 7 and 2.13.6 say the 59-right labels replace .NET's; each label exists in `0009_access.sql` |
| E02's permissions differ from .NET's `reports.export` | `DEC-40`: one export right per module, recorded in drift row 4 |
| `revenue.capture_entry` has no actor or organization parameter | `tenancy.current_actor()` and `current_organization()`, the convention of 14 routine files |
| The report exports cap rows where .NET does not | `DEC-45`, recorded with its reason |
| The error named for a day save is not the first bad row in sent order | the shape step runs first in sent order (`DEC-42`); the web marks the named vehicle; the design report's dialectic recorded it |
| XlsxWriter files are not byte-stable | `workbook.py:813-828` fixes the zip times; `set_properties` fixes the created date |
| `recurring_savings_frequency` stays in `messages.py` and `test_message_codes` will fail | 2.13.6 retires it; the build removes the entry with the routine's refusal in one change |
| Two `uq_entries_group_vehicle` names collide | index names are per schema; `expenses` and `pettycash` are different schemas |
| The ledger's `total` overflows `numeric(14,2)` for an absurd line | `pettycash.check_line` refuses "The total is too large." before any insert; a migrated row that overflows is reported, not loaded |
| A run dated on the opening date is counted twice in the balance | `DEC-35`: saved runs "dated after the opening date" |
| Two day saves over the same vehicles deadlock | ascending vehicle id, `NOWAIT` on the record, the advisory lock after the row |
| A scoped viewer learns a purchase total through `group.total` | parity: CE-21's `group` on every row in .NET |
| The inventory's appendix misses two uncommitted files it cites | the cited lines of `PettyCashRepository.cs` lie outside its uncommitted hunks and no `PettyCashUseCases.cs` line is cited |

## 7. Fixes

None: report mode. The words to apply, for the build session's first step (or a docs pass):

1. `docs/05` 11.4, `api.report_get`, "Raises, in order": `reports.check_query`; unknown group or report ->
   `XC404`; the report's own right (`XC403 ...`); for a petty-cash report a `holder_id` not among the person's
   floats -> `XC404`; then the period (dated reports). (V-D4-1)
2. `docs/inventory/inventory-expenses-reports.md` section 5 and `docs/09` 4.2: `CentralExpenseTests` 15 -> 17.
   (V-D11-1)
3. `docs/05` 11.3, `setup.save_recurring`: "a saving with an end date that is new or differs from the stored one
   -> `recurring_savings_end` (a migrated end stands until cleared)"; or `docs/10` 3.2 row 36: "`End` set to
   null for savings (the notes have no end date); the list of cleared ends is reported". The owner decides which
   (section 10). (V-D11-2)
4. `docs/13`: question 82 (reserve on the board first): "The approval limit of a petty-cash approver is per
   entry; a shared purchase is one entry per vehicle, so each part is measured alone. Should the limit see the
   purchase total?" Default: per part, as .NET measures entries; the approver sees `group.total` on each part.
   (V-D5-1)
5. `docs/audit/2026-10-12-design-08b-d0.md:86`: 47 -> 43. (V-D11-3)
6. `docs/05` 11.1: drop `setup.posting_window` and name `setup.report_window` in `scheduled_runs`,
   `fleet_postings` and 11.2, or state the difference. (V-D6-1)
7. `docs/05` 11.5: "inside a block that catches a 400-class refusal and raises it again through `tenancy.refuse`
   with the caught code and SQLSTATE and `vehicle_registration` added to its `DETAIL`" (the header lists those
   codes `via revenue.capture_entry`). (V-D10-1)
8. `docs/13`: question 81 under its own heading; the board's Numbers line: next free 82. (V-D11-4; not this
   scope's author)

## 8. Commands and outputs (trimmed)

- `git status --short apps/api-python` -> `?? apps/api-python/` (the whole tree untracked, as every day);
  `git status --short apps/api tests/api` -> 22 modified, 5 untracked; `git log --oneline 9276c51..HEAD -- apps/api tests/api` -> nothing.
- Files of the scope by modification time: inventory 18:42, `docs/04` 18:45, `docs/02` 18:53, `docs/10` 18:55,
  `docs/15` 18:57, `docs/11` 18:59, the prompt 19:00, `docs/09` 19:04, `docs/05` 19:29, `docs/06` 19:30,
  `docs/12` 19:33, the design report 19:33; `docs/prompts/README.md` 20:42 and `docs/13` 20:49 by other sessions
  (the coordinator's and verify-07b-d3's rows). Under `src/`, `db/`: nothing after 17:30; under `tests/`:
  `test_revenue_routines.py` 20:39 (D4), `test_setup_vehicle_routines.py` 20:47 (verify-07b-d3).
- Versions: `.venv` Python 3.13.2; `select version()` -> PostgreSQL 16.15 (Visual C++ build 1944, 64-bit); the
  cluster holds `postgres` and `xcode` only; CI `postgres:18` (`.github/workflows/xcode-api.yml:63`, `:107`).
- Free memory at the test run: 0.68 GB (one `-n 0` job allowed; no other job on the board).
- `pytest tests/unit/test_messages.py tests/unit/test_endpoint_catalogue.py tests/unit/test_routine_catalogue.py -q -p no:cacheprovider -n 0`
  (21:06 to 21:07): `432 passed in 11.83s`.
- D4's shared full run (queue row 7, `full.log` dated 19:31 in revenue-d5's scratchpad):
  `3 failed, 5733 passed, 4 warnings in 6920.82s (1:55:20)`; the three: `tests/db/test_gateway.py::test_identity_routines_map_every_outcome_with_one_statement_each`,
  `::test_verify_device_maps_through_the_gateway`, `::test_ops_routines_map_the_operator_routines` (D1's, on the board since 20:38).
- Route sweep: 83 operation ids from `grep -ho 'WithName("...")\|ProducesExport("...")' apps/api/Api/*.cs`, each
  found in `docs/06-http-contract.md`.
- Sentence sweep: `grep -no '"[A-Z][^"]*[.?]"'` over the seven .NET files of the scope plus the quoted-label
  lines read by hand (`CentralExpenseUseCases.cs:137`, `:174`, `RevenueContracts.cs:141-142`,
  `RevenueEndpoints.cs:29`, `RecurringItem.cs:51-82`, `CentralExpenseContracts.cs:57`).
- Name sweep (scratchpad `names.py`): 84 `schema.name` tokens in `docs/05` 11, 23 existing with their files, 61 new.
- Library check (the global interpreter, where the D0 session measured): reportlab 5.0.0, 0 `.pyd`/`.so`,
  `rl_config.invariant` present, requires `charset-normalizer`, `pillow`; XlsxWriter 3.2.9, `ZipInfo(..., (1980, 1, 1, 0, 0, 0))`
  at `workbook.py:814`, `strings_to_formulas` and `quote_prefix` present. `pypdf` not installed anywhere.
- Not run, with the reason: `ruff`, `mypy`, `xcode-api db routines|verify` (no code or `db/` file in scope;
  `db verify` on `xcode` was last run read-only by verify-07b-d3 at 17:11); a new full run (no code change since
  the 19:31 run; the documents cannot change its outcome); `pip download` of the ADR's wheels (no network).

## 9. Regressions and misses against earlier audits

Read after the pass above: `docs/audit/2026-10-12-design-08b-d0.md` section 8, and the 20:40 entry of
verify-07b-d3.

- The design report's V-D11-1 (the two report permission codes): fixed, verified at `docs/05` 11.4.
- Its V-D4-3 (P03's fleet number): recorded in `docs/06` 2.13.4 for the build; the P03 row at `docs/06:433` is
  unchanged until then, as intended.
- Its V-D7-1 (`EXPLAIN` evidence): still open; `docs/perf/` holds `revenue.md` only.
- Its V-D1-1 (`reports.view` and savings figures): the residual risk is in `docs/12` 7.
- What that pass missed and this one found: V-D4-1 (the petty-cash check order), V-D11-1 (the test count),
  V-D11-2 (the migrated end), V-D5-1 (the approval limit per part), the three notes V-D6-1, V-D10-1, V-D11-3.
- No regression: nothing that pass recorded as fixed is broken.
- verify-07b-d3's V-D11-1 (stale rights rows in `docs/05` section 4) is outside this scope and was not re-checked.

## 10. For the user

1. **The approval limit on a shared petty-cash purchase** (V-D5-1, business): the limit is per entry in .NET and
   stays per part in the design. Recommendation: keep it per part (parity, and the approver sees the purchase
   total on each part), and record it as question 82 with that default, so the build does not have to decide.
2. **A migrated saving's end date** (V-D11-2, irreversible at migration): keep the end and let a revise carry it
   unchanged (the owner's intent survives; the routine refuses only a new or different end), or clear it at
   migration and report the list. Recommendation: the first, so no migrated saving posts past what the owner
   set and every one of them can be revised.
3. **Independence**: this verify was run by the design's author. If you want the fresh-eyes run the method asks
   for, a new session with the same parameters takes about an hour; nothing above needs it before the build.
4. **The coordinator role**: revenue-d5 [b49167] holds it from 21:05 (its message to me at 21:08); this session
   did not take it and leaves line 7 of the board as it is.
