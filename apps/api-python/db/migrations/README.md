# Versioned migrations

- `NNNN_<name>.sql` forward, `NNNN_<name>.down.sql` reverse. `NNNN` is zero-padded and
  strictly increasing.
- First line: `-- <purpose in one sentence>`.
- One concern per file (one table family, one backfill). Backfills end with a `DO` block
  that raises if the expected row count does not hold.
- Never edit a file after it is applied anywhere; add a new one. The runner refuses
  checksum drift.
- Tenant tables get `ENABLE ROW LEVEL SECURITY` and the `tenant_isolation` policy in the
  same migration that creates them.
- Routine bodies do not belong here; a signature change is `DROP FUNCTION IF EXISTS` here
  and the new definition in `../routines/`.

The set is `docs/04-schema.md` section 11, in order (0008 to 0011 are detailed in its section
13, 0013 in section 14). Every file runs in the runner's transaction; from 0002 on each starts with
`SET LOCAL lock_timeout = '10s'`; its `.down.sql` reverses it for `db down`.

| Version | File | Purpose |
|---|---|---|
| 0001 | `0001_ops.sql` | `ops.operator_actions` (append-only operator/runner audit) and the `ops.rate_limit_windows` UNLOGGED fixed-window counter table |
| 0002 | `0002_identity.sql` | `identity` users, verification codes, trusted devices, refresh tokens, the append-only sign-in attempts; `ops.touch_updated_at()` |
| 0003 | `0003_tenancy.sql` | organizations, memberships, localization, branding, logo, security policy, user preferences, the append-only change log and audit events; `tenancy.current_organization/actor/request()`, `tenancy.check_contrast()`; RLS |
| 0004 | `0004_access_catalog.sql` | the permission catalogue with its 40 keys, dependencies and role defaults; roles, person roles, permission overrides, data scopes; RLS |
| 0005 | `0005_setup.sql` | `btree_gist` (in `ops`); code tables; companies, vehicles, targets, away periods, investments, expense catalogue, recurring items, versions and allocations; the scope foreign keys; registration and allocation-sum triggers; RLS |
| 0006 | `0006_revenue.sql` | `revenue.no_earnings_reasons`, `revenue.records`, the business-date trigger; RLS |
| 0007 | `0007_readonly.sql` | no grant: the DBA checklist for any future `xcode_readonly` access, as comments |
| 0008 | `0008_sign_in.sql` | sign-in of the design notes v2.33: forced reset, last sign-in, the wrong-PIN lock as a counter, hashed device tokens with name and use dates, the sign-in history words, the `signIn` change-log section, a 15-minute idle unlock |
| 0009 | `0009_access.sql` | access of the design notes v2.32 and v2.33: the 59-right catalogue with derived legacy keys and the hidden Owner key, the grant translation of every membership, the back-dating limit, brand host and URL rules |
| 0010 | `0010_setup.sql` | setup of the design notes v2.29 to v2.32: dated target sets (the weekly targets split into them), fleet number and optional initial investment, main categories above expense categories |
| 0011 | `0011_revenue.sql` | revenue of the design notes v2.29 to v2.31: a low day keeps its amount with a reason, an optional note on Other, the low-day threshold and gap amber-band settings; the weekly targets leave |
| 0012 | `0012_pettycash.sql` | petty cash: kind and status code tables, the entries table, the `pettycash` change-log section; RLS |
| 0013 | `0013_expenses.sql` | central expenses, scheduled-item pauses, the saving model (rule, openings, decided runs), petty-cash shared purchases, the `centralexpenses` and `reports` change-log sections; RLS |
| 0014 | `0014_orphan_routines.sql` | drops the old `api.auth_sign_in` (8 arguments) and `api.people_list` (6 arguments) that 0008 and 0009 left behind, and the four-argument `setup.scheduled_runs` and `setup.fleet_postings` (they gain a kinds filter) |
