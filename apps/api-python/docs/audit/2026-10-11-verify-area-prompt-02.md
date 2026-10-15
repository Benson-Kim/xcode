# Verify: prompt 02 (schema), 2026-10-11

`SCOPE: area:prompt 02` · `MODE: fix` · `DEPTH: standard` · method `docs/14-verification.md`.
Run by a session that did not write the code. Edits only under `apps/api-python/`. The
session stopped at the context budget the verify prompt sets (about 100k tokens), so the
probes it did not reach are marked `not checked` (section 4), and section 11 says where to
resume.

## 1. Verdict

**pass with findings**: no blocker survives, and the full suite ran to completion (4181 passed, 0 failed, 0 skipped, 0 errors, 47 min 3 s; section 8).

- Claims (section 2): 32. holds 20, fails 2, unproven 8, n/a 0, not checked 2.
- Surviving findings (section 3): blocker 0, major 2, minor 4, note 3.
- Fixed in this run: 1 major (V-D9-1), with a test that failed first. The other major
  (V-D4-1) needs a migration, and the next migration number is shared with prompts 07 and
  07b, so it is recorded as an open question with a default and an owner. Of the minors,
  2 have a corrected document (one of them also a guard test) and 2 are handed to the
  prompt 01 verify session, which is editing `db/verify.py` now.
- Probes (section 4): 32. holds 14, fails 8 (each fixed, corrected, or with an owner), unproven 1, n/a 5, not checked 4.

## 2. Thesis and claims

Thesis (steelmanned): prompt 02 delivers D1 to D7. Migrations 0002 to 0007 build every
`identity`, `tenancy`, `setup` and `revenue` table of `docs/04-schema.md` with its keys,
checks, indexes, RLS and grants; append-only tables refuse `UPDATE` and `DELETE` by
privilege; the code tables and the 40-key catalogue equal the .NET `PermissionCatalog`;
the triggers raise the `XC422` protocol; the domain vocabulary imports only the standard
library; `db verify` proves the schema on a live database and each check bites; the column
rules equal the .NET validation at `HEAD` 493bf82.

Grades follow `docs/14-verification.md` section 5. "A (run)" = a test against real
PostgreSQL passed in this run and its assertion was read. "B (run)" = it passed, but this
run did not re-read the assertion, so a security or integrity claim stays `unproven`.

| # | Claim (prompt 02 unless noted) | Code | Verdict | Grade |
|---|---|---|---|---|
| 1 | D1: one file per table group, `SET LOCAL lock_timeout`, no `api.*` routine | `db/migrations/0002`-`0007` (read in full) | holds | A (read + `test_migrate` run) |
| 2 | D1: columns, types, defaults and checks as `docs/04` sections 3 to 6.1 | same | holds, apart from claim 18 | A (read against `docs/04`) |
| 3 | D1: composite FKs start with `organization_id` | migrations; `check_tenant_foreign_keys` | holds | A (`test_verify_reports_a_foreign_key_that_skips_the_organization`) |
| 4 | D1: RLS and exactly `tenant_isolation` for the executor on every tenant table | migrations; `check_tenant_tables_have_rls` | holds | A (probe run: 0 failing checks; bite tests for disabled RLS, a second policy, the wrong role and the wrong expression) |
| 5 | D1: grants per the "Writes" column; append-only tables INSERT only | migrations; `check_declared_privileges` | holds on the migrated database | A (probe run) |
| 6 | D1/README: role files are idempotent and re-runnable | `db/roles/030_grants.sql` | **fails** (V-D9-1), fixed | A (`test_role_files.py`, failed first) |
| 7 | D1: `btree_gist` in `ops`, `public` empty | `0005_setup.sql:6` | holds | A (`test_btree_gist_lives_outside_public`) |
| 8 | D2: code-table rows exactly as `docs/04` section 2 | `0005:32-45`, `0006` | holds | B (run) |
| 9 | D2: 40 keys, 30 dependencies, 79 role defaults, equal to .NET | `0004:38-156`, `DO` guard | holds | A (compared line by line with `AccessContracts.cs:26-118` and `Access.cs:52-88`) |
| 10 | D3: `touch_updated_at` on every table with `updated_at` | migrations; `check_updated_at_triggers` | holds | A (`test_verify_reports_a_missing_touch_trigger`) |
| 11 | D3: triggers raise `XC422` with the code in `MESSAGE` | `0005:280-327`, `0006` | holds | B (run) |
| 12 | D3: the share-sum constraint trigger is deferred and checked at commit | `0005:298-337` | **unproven** as written: it cannot run at commit under `xcode_app` (V-D3-1); doc corrected | C |
| 13 | D3: contrast truncation equals .NET | `0003:22-46` vs `Organization.cs:58-67` | holds (equal to `ratio < 4.5`) | A (code compared; contrast table test passed) |
| 14 | D3: session functions return `NULL` when unset | `0003:8-19` | unproven (tenancy; assertion not re-read) | B (run) |
| 15 | D4: enums equal the code tables and the `CHECK` lists | `test_enum_parity.py` | holds | B (run) |
| 16 | D4: `domain/` imports only the standard library | `test_layers.py` | holds | A (run) |
| 17 | D5: every `db verify` check bites on a broken database | `tests/db/test_schema_structure.py`, `test_structure.py` (40 bite tests) | **unproven** for column grants to the executor and readonly (V-D6-1) | A for the rest |
| 18 | `docs/04` 4.4: brand domain and URL rules carry the .NET rule | `0003:162-185`; `check_branding.sql:46-50` | **fails** (V-D4-1) | A (.NET probe and SQL probe) |
| 19 | `docs/04` 5.1: case folding differs from .NET "for a few letters" | `0005:52` | **unproven**: every non-ASCII letter differs (V-D5-1); doc corrected | A (SQL probe) |
| 20 | `0007` checklist: a DBA may add a readonly RLS policy and still pass `db verify` | `0007:5-12`; `verify.py:418-420` | **unproven**: the check refuses any second policy (V-D6-2) | A (code read) |
| 21 | D6: isolation for every tenant table (B invisible, no id invisible, foreign insert `42501`) | `test_tenancy_isolation.py` | unproven | B (run) |
| 22 | D6: one failing case per `CHECK`, `UNIQUE`, `EXCLUDE`, FK and trigger | `test_constraints.py` | unproven | B (run) |
| 23 | D6: append-only `UPDATE`/`DELETE` fail with `42501`; app and operator read nothing | `test_grants.py`, `test_app_has_no_table_privileges_anywhere` | unproven (security; assertions not re-read) | B (run) |
| 24 | D7: deviations written into `docs/04` | `docs/04` | holds apart from claims 12 and 19 (corrected now) | A |
| 25 | Invariant: `db migrate` fresh then re-run applies nothing | `test_migrate.py` | holds | B (run) |
| 26 | Invariant: `db verify` exit 0 | CLI on the `xcode` database | holds | A (`exit=0`, 21 checks ok) |
| 27 | Invariant: no TODO, FIXME or plan identifiers | sweep | holds | A (sweep) |
| 28 | Invariant: lint and types green | `ruff`, `mypy` | holds | A (run) |
| 29 | Away periods: non-overlap equals .NET | `0005:120-124` vs `FleetVehicle.cs:84-111` | holds | A (code compared) |
| 30 | Invariant: all tests green | full run | holds | A (4181 passed, 0 failed, 0 skipped, 0 errors) |

`not checked`: the `docs/04` index list against `pg_indexes` beyond what `check_declared_indexes`
asserts, and the `domain/` dataclass fields against `docs/05` section 1.3 (both D11; context
budget).

## 3. Findings

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| V-D9-1 | red team (hurried DBA) | `db/roles/README.md`: the role files are "idempotent, re-runnable"; `docs/04` 9: append-only tables hold INSERT only | A DBA re-applies `010` to `030` on a migrated database (a new role, a changed timeout). Expected: no table grant changes. Actual: `030_grants.sql:48-56` ran `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES` in six schemas, which gave the executor 58 extra grants: `UPDATE`/`DELETE` on `tenancy.change_log`, `tenancy.audit_events`, `identity.sign_in_attempts`, `ops.operator_actions`, the append-only setup tables, and the permission catalogue | probe E1 (section 8); `test_role_files.py` failed with "Left contains 58 more items, first extra item: ('identity.refresh_tokens', 'xcode_api_executor', 'DELETE')" | `db verify` does notice (two checks, 42 failures), so this is not silent where verify runs; but the README invites the re-run, and nothing in the runbook makes verify follow it | survives, **major** (an invariant broken by a documented operation) | **fixed**: the existing-object grants are removed (default privileges still cover new tables, and every migration sets its own grants); README corrected; `tests/db/test_role_files.py` |
| V-D4-1 | falsification | `docs/04` 4.4: the domain is `^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.…)+$` and URLs `~ '^https://'`; the inventory (`inventory-domain.md:224`) says the rule is `Uri.CheckHostName == Dns` and an absolute https URI | `PUT /setup/organization/settings` with domain `Example.com` (a phone keyboard capitalises the first letter), `localhost`, `example.com.`, `a_b.example.com` or `bücher.de`, or a URL `HTTPS://x.example`. .NET accepts all of them; Python answers 400 `Invalid domain.` or `Brand URLs must use HTTPS.` from `tenancy.check_branding`, and the `CHECK`s at `0003_tenancy.sql:162-185` refuse them on any path | .NET probe (section 8): all `Dns`/`True`; SQL probe E4: all refused | looked for a documented decision to narrow the rule: none in `docs/04`, `docs/13` or the prompts | survives, **major** (a rule wrong on a reachable path) | **open question 58** in `docs/13`: default = accept what .NET accepts (case-insensitive scheme; host labels with upper case, underscores and non-ASCII letters, a single label, a trailing dot; keep the 253 cap), stored as typed. It needs a forward-only migration that replaces `ck_brandings_domain` and the five URL checks, plus `check_branding.sql`. Owner: the first migration of prompt 07b, because 07 and 07b share the next number |
| V-D6-1 | falsification | `docs/14` D6: each `db verify` check fails on a database built to break it; `0007` checklist item 6: verify "checks the hash, digest, identity and audit rules" | `GRANT UPDATE (reason, after) ON tenancy.change_log TO xcode_api_executor`, `GRANT UPDATE (weekly_amount) ON setup.vehicle_targets TO xcode_api_executor` and `GRANT SELECT (before, after) ON tenancy.audit_events TO xcode_readonly`: all 21 checks still pass | probe E2 (section 8); `check_declared_privileges` reads `pg_class.relacl` only (`verify.py:551-595`); `check_audit_tables_append_only` reads `role_table_grants` (`verify.py:771-792`) | the app and operator check is column-aware (`verify.py:222-286`, bite test `test_verify_reports_a_column_grant_to_the_app_role`); readonly's audit grant returns no rows without a policy, but V-D6-2 shows the checklist asks for one | survives, **minor** (a detector gap; no such grant exists today) | **handed over**: in both checks, read `pg_attribute.attacl` (or `has_column_privilege`), and add one bite test each. `db/verify.py` was changed at 15:56 by the prompt 01 verify session, so I left it alone. Residual risk until then: owner = whoever edits `verify.py` next |
| V-D6-2 | Socratic | `0007_readonly.sql:9-10` item 4: a DBA who grants readonly columns adds "a reviewed RLS policy naming xcode_readonly"; item 6: and passes `db verify` | Following item 4 adds a second policy; `_tenant_policy_failures` (`verify.py:418-420`) requires exactly `["tenant_isolation"]`, so item 6 then fails | code read | none: the two rules contradict | survives, **minor** (documentation that would block the DBA path) | **handed over** with V-D6-1: allow extra policies whose roles are exactly `{xcode_readonly}` and whose command is `SELECT`, or drop item 4 and say readonly reads no tenant rows. Recommendation: allow them, because the checklist's column grants are useless without a policy |
| V-D5-1 | falsification | `docs/04` 5.1 and `docs/13` q17: `upper()` and .NET `ToUpperInvariant` differ "for a few non-ASCII letters (ß, dotted i)" | `upper('école' COLLATE "C")` keeps `é` (0xE9), while .NET and Python give `É` (0xC9). So `école` and `École` are two companies or categories here, and .NET refused the second as a duplicate | SQL probe (section 8); .NET probe `upper ÉCOLE c9` | the `C` collation was chosen on purpose, so that every server behaves the same (q17's default); that part holds | survives, **minor** (the premise of an owner decision is wrong) | **doc corrected** in `docs/04` 5.1 and `docs/13` question 17. For the user: section 10 |
| V-D3-1 | pre-mortem | `docs/04` 5.8: the share-sum trigger is `DEFERRABLE INITIALLY DEFERRED`, checked at commit | A future routine (08b's saving rework) inserts versions or allocations and returns. At commit the deferred trigger runs as `xcode_app`, which has no `USAGE` on `setup`, so the commit fails with `42501` and the request gets a 5xx | `docs/05` row `setup.save_recurring` records the workaround; `save_recurring.sql:283` | the one writer today fires the check with `SET CONSTRAINTS … IMMEDIATE`, so no current path fails | survives, **minor** (a latent trap; the schema document promised a commit-time check) | **doc corrected** (`docs/04` 5.8 now states the rule and that deleting a share is unchecked); guard test `tests/unit/test_deferred_constraints.py` fails for any routine that writes shares without the statement (shown to bite, section 8) |
| V-D6-3 | Socratic | `docs/03` 6: `updated_at` comes from `p_now`; the trigger is a backstop | `ops.touch_updated_at` (`0002:7-16`) replaces `updated_at` with `now()` whenever the new value equals the old one, so a routine that sets `p_now` equal to the stored value (a frozen `ManualClock`) gets wall-clock time | code read | in production `p_now` moves, so the two values never match | survives, **note** | recorded |
| V-D6-4 | Socratic | the schema behaves the same on every server | `ck_users_email` (`email = lower(email)`) and `uq_roles_name` (`lower(name)`) use the database default collation: `C` on the local cluster (ASCII-only `lower`), `en_US.utf8` in the CI image | `datcollate = C` measured on `xcode` | Python stores emails lower-cased and role names are four ASCII seeds, so no current input behaves differently | survives, **note** | recorded; question 17's fix (section 10) covers it |
| V-D3-2 | Socratic | "positive money, two decimals" by `numeric(14,2)` | `numeric(14,2)` rounds `10.555` to `10.56` instead of refusing it | type semantics | `Money` refuses more than two decimals before any routine runs (`domain/values.py`) | survives, **note** | recorded |

## 4. Per domain

Probe tally (32): D1 RLS and policy holds; owner functions past RLS holds; catalogue = .NET holds; catalogue = shared and `MODS` n/a; scoped viewers, `{id}` routes, anti-escalation n/a. D3 append-only by grant fails (fixed); composite FKs holds; money type holds; constraint trigger at commit fails (doc and guard); versions, locks, replays n/a. D4 column rules holds; brand domain and URLs fails (q58); case folding fails (doc, q17); drift holds. D5 no clock in decisions holds. D6 verify exit 0 holds; checks bite fails (V-D6-1, handed over); no dynamic SQL holds; definer search_path holds; version features unproven; template fingerprint holds; indexes and timeouts not checked. D10 sweep holds; five invariants fails (two closed, one open); three test files' assertions not checked; full suite holds. D11 `docs/04` matches code fails (corrected); `docs/13` and status current fails (corrected q17, added q58; the prompts README status row for 02 still says "validated" without a report, now this file). D2 n/a, D7 not checked, D8 n/a, D9 beyond the roles file not checked.

**D1 Tenancy and authorization.** RLS plus exactly `tenant_isolation` on every tenant table:
holds (A, claim 4). Functions owned by `xcode_owner` that read past RLS: in scope only trigger
functions and `check_contrast`, none `SECURITY DEFINER` (sweep), so none reads past RLS:
holds. Catalogue equals .NET: holds (claim 9); against `packages/shared` and the design's
`MODS`: n/a here (B13 of 07b). Scoped viewers, `{id}` routes, anti-escalation: n/a (routines,
prompts 03 to 06).

**D3 Data integrity.** Append-only by grant: holds on the migrated database, fails under a
roles re-run (V-D9-1, fixed). Composite FKs: holds. Money `numeric(14,2)`: holds (V-D3-2
note). Constraint trigger at commit: V-D3-1. Version bumps, lock order, replays: n/a
(routines).

**D4 Contract parity.** Column rules against .NET: registration (`FleetVehicle.cs:10`),
away periods, schedule shape (`RecurringSchedule.cs:26-35`), contrast, lengths (company 160,
category and item 100, investment description 160, note 80, reason 500): hold. Brand
domain and URLs: fail (V-D4-1). Case folding: V-D5-1. Drift: since 2026-10-08 the .NET
schema gained only `CentralExpenses` (9276c51) and the uncommitted `RecurringPause`, both in
the drift register (rows 1, 5); no table prompt 02 built changed: holds.

**D5 Domain rules and time.** No `now()`, `current_date`, `clock_timestamp()` or `random()` in a
decision path of 0002 to 0007: holds (the trigger backstop and column defaults only, V-D6-3).
Normalisation parity: V-D5-1.

**D6 Database craft.** `db verify` exit 0: holds. Checks bite: holds for the 40 bite tests,
fails for column grants (V-D6-1). No dynamic SQL in the migrations: holds (sweep: only
`EXECUTE FUNCTION` trigger syntax; the one `EXECUTE format` lives in `db/roles/030`, with
`%I` on a fixed array). `SECURITY DEFINER` without `search_path`: none in the migrations.
Version-specific features: none newer than PostgreSQL 13 seen in 0002 to 0007 (generated
columns 12, `btree_gist`, `EXCLUDE`, identity columns): holds by reading, not checked against
a 13 server. Template fingerprint equals the files tested: holds (comment
`7a8b76ad…f9c5` = `template_fingerprint()`, measured after the fix). Indexes per query and
role timeouts: not checked.

**D10 Tests as evidence.** Skip, xfail, sleep and bare-except sweep over the six scope test
files: clean (the one `skip` hit is a test name). Five invariants with a wrong
implementation: (1) disabling RLS on one table: caught (`test_verify_reports_disabled_rls`);
(2) a migration that forgot `REVOKE ALL`: caught (`test_verify_reports_an_extra_write_privilege`);
(3) a roles re-run: was not caught by any test, now `test_role_files.py`; (4) a column
`UPDATE` grant on the change log: not caught (V-D6-1); (5) a routine writing shares without
`SET CONSTRAINTS`: was not caught, now `test_deferred_constraints.py`. Assertions of
`test_tenancy_isolation.py`, `test_constraints.py` and `test_grants.py`: not checked
(context budget; claims 21 to 23 stay `unproven`).

**D11 Documents.** `docs/04` corrected in 5.1 and 5.8; `db/roles/README.md` corrected.
`docs/13` question 17 corrected and question 58 added (at 17:20, after the file had been
quiet for 45 minutes). The `0008_pettycash.sql` name in `docs/04` 6.2 and 11, prompt 08 and
`db/migrations/README.md` will collide with whatever migration 07 or 07b adds first: for
07b's design session.

D2, D7, D8, D9 (except the roles file): n/a for a schema prompt, or not checked.

## 5. Per mode

**Assumptions (Socratic).**

| Assumption | Stated | Enforced by |
|---|---|---|
| Role files can be re-run | `db/roles/README.md` | nothing until this run; now `test_role_files.py` |
| The deferred share check runs at commit | `docs/04` 5.8, `0005:298` | nothing; the writer must fire it (now a guard test) |
| `C`-collation folding differs from .NET only for a few letters | `docs/04` 5.1, q17 | false (V-D5-1) |
| Column-level grants cannot appear | implicit in `check_declared_privileges` | nothing for the executor and readonly (V-D6-1) |
| A readonly policy can coexist with verify | `0007` item 4 | contradicted by `verify.py:418` (V-D6-2) |

**Falsification:** claims table, section 2.

**Pre-mortem.**
1. (likely x medium) In February 2027 a DBA adds a role on the cPanel database by re-running
   the role files, as the README allows. The executor now holds `DELETE` on the change log
   and the operator trail; a routine bug that deletes history goes unnoticed until an owner
   misses an entry. Early sign: `db verify` red. Mitigated: V-D9-1 fixed.
2. (likely x low) Prompt 08b adds a saving routine that inserts versions and allocations
   without `SET CONSTRAINTS`; every save answers 500 in production, although its tests,
   which commit as the owner, pass. Mitigated: the guard test.
3. (possible x low) An owner types `Priori.co.ke` in brand settings on the new API and
   gets "Invalid domain.". Early sign: a support call. Open: V-D4-1.

Inversion: what would guarantee failure? Grants that drift without `db verify` noticing.
That condition exists for column grants (V-D6-1).

**Red team.** Hurried DBA: roles re-run (V-D9-1, fixed); column grant on an audit table
(V-D6-1, open); a readonly policy per the checklist (V-D6-2). Clerk in tenant A: a foreign
`organization_id` in a composite FK, refused by FK plus RLS `WITH CHECK` (conceded, A);
reading another tenant with no organization set returns nothing because
`current_organization()` is `NULL` (B). Gamer: an export cell starting with `=`: n/a here.

**Dialectic.**

| Decision | Strongest counter | Verdict | Confidence |
|---|---|---|---|
| `upper(name COLLATE "C")` for name uniqueness (q17) | It is server-independent but parity-breaking for all non-ASCII letters; PostgreSQL 17's builtin `C.UTF-8` provider does simple case mapping, which is what `ToUpperInvariant` does, and is still server-independent | keep for now; revisit when the host's PostgreSQL version is known (q39) | medium |
| A deferred constraint trigger for shares | An immediate trigger fires per row and would refuse the first allocation insert, so deferral is needed, but it must be fired by the writer | keep, with the documented rule and guard | high |
| Migrations own table grants; role files own defaults | One place (030) could grant everything: simpler, but it cannot express append-only | keep; V-D9-1 makes it true | high |

## 6. Conceded

- `tenancy.role_defaults` holds the raw .NET lists, not the dependency-expanded ones (Fleet
  manager lacks `commitments.view`): `tenancy.role_permissions` expands through
  `tenancy.expand_permissions`, as `PermissionCatalog.DefaultsFor` does.
- `daterange(left_on, returned_on)` with `[)` bounds lets a vehicle leave on the day it
  returned: .NET allows exactly that (`FleetVehicle.cs:89`), and adds a stretch only when
  `returnedOn > left` (`:108`), matching `returned_on > left_on`.
- Contrast is truncated, .NET compares unrounded: `trunc(r, 2) >= 4.5` holds exactly when `r >= 4.5`.
- The registration check equals .NET's `^K[A-Z]{2}[0-9]{3}[A-Z]$` with the canonical space.
- The schedule check equals `RecurringSchedule`'s constructor rule.
- Identity columns need no sequence grant for INSERT: the append-only inserts pass in `test_grants.py`.

## 7. Fixes

| Finding | Files | Test that failed before and passes now |
|---|---|---|
| V-D9-1 | `db/roles/030_grants.sql`, `db/roles/README.md` | `tests/db/test_role_files.py::test_reapplying_the_grants_file_leaves_every_table_grant_unchanged` (before: 58 extra grants; after: 1 passed) |
| V-D3-1 (guard) | `docs/04-schema.md` 5.8 | `tests/unit/test_deferred_constraints.py` (passes today; shown to fail when the `SET CONSTRAINTS` statement is removed) |
| V-D5-1 | `docs/04-schema.md` 5.1, `docs/13-open-questions.md` question 17 | document only |
| V-D4-1 | `docs/13-open-questions.md` question 58 | open question; no code change |

## 8. Commands and outputs

Versions: PostgreSQL 16.15 (local cluster, port 5433, `datcollate`/`datctype` `C`, UTF8);
Python 3.13.2; CI image `postgres:18` in `.github/workflows/xcode-api.yml` (untracked, never
run). Own template `XCODE_TEST_TEMPLATE=xcode_template_v02`, because sessions verifying 00
and 01 and the prompt 07 build shared the cluster.

```
baseline (before any change), 11 modules, -n 3:  421 passed in 858.55s
test_role_files.py before the fix:  1 failed  "Left contains 58 more items"
test_role_files.py after the fix:   1 passed
probe E1 (030 re-run): change_log, audit_events, sign_in_attempts, vehicle_targets,
  recurring_versions, permissions -> DELETE,INSERT,SELECT,UPDATE;
  failing checks {'table privileges match the declared writes': 34,
                  'audit tables are append-only for the executor': 8}
probe E2 (column grants): failing checks {}
probe E3: upper(U&'\00E9cole' COLLATE "C") first char e9; Python/.NET c9
probe E4: 'Example.com', 'localhost', 'intranet', 'example.com.' -> CHECK accepts=False
.NET 10 probe: Example.com Dns, EXAMPLE.COM Dns, localhost Dns, example.com. Dns,
  a_b.example.com Dns, bücher.de Dns, -a.example.com Unknown;
  HTTPS://x.example True; "école".ToUpperInvariant() ÉCOLE c9
xcode-api db status: applied 0001-0007, pending none, checksum drift none,
  routine drift ['50_revenue/round_half_even.sql', '50_revenue/vehicle_week.sql'] (prompt 07, in flight)
xcode-api db verify (xcode database): 21 checks ok, exit=0
ruff check/format (new files): clean; mypy: no issues in 153 source files
template comment = fingerprint: 7a8b76ad06c34a97c5218622dcc142aa0468e6eba57360960a90206918b3f9c5
full run (start 16:32:16, end 17:19:35), -n 3, own template rebuilt from the fixed files:
  4181 passed, 6 warnings in 2823.37s (0:47:03); 0 failed, 0 skipped, 0 errors
  warnings: PyJWT InsecureKeyLengthWarning from tests that mint HS384/HS512 tokens with a
  36-byte key (not this scope)
```

`xcode-api db routines` was not run against the `xcode` database: the prompt 07 session is
reworking the revenue routines there, and this run changed no routine.

## 9. Regressions and misses against earlier reports

`docs/audit/` holds no earlier report for prompt 02. The memory note says "02, 03 validated
2026-10-09" with no report. That validation did not record V-D9-1, V-D4-1, V-D6-1, V-D6-2 or
V-D5-1, and its schema document still said "a few letters". No earlier fix found broken
again.

## 10. For the user

- **Case-insensitive names beyond ASCII (q17).** Today `école` and `École` can both exist as
  companies, categories or items. Recommendation: accept it until the host's PostgreSQL
  version is known (q39). On PostgreSQL 17 or later, switch the generated columns to the
  builtin `C.UTF-8` collation, which folds like .NET and is the same on every server. Kenyan
  PSV and expense names are almost all ASCII, so the exposure is small, and a later change
  needs only a forward migration that re-derives the column.

## 11. Where to resume

Not checked, in order of value: the assertions of `test_tenancy_isolation.py`,
`test_constraints.py` and `test_grants.py` (claims 21 to 23); the `domain/` records against
`docs/05` section 1.3; the `docs/04` index list against the queries the routines run (D6, D7).
To hand over: V-D6-1 and V-D6-2 to whoever next edits `db/verify.py`; V-D4-1 and the
`0008` numbering to 07b's design session.
