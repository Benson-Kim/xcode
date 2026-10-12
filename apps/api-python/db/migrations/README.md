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

The set is `docs/04-schema.md` section 11, in order; `0008_pettycash` arrives with the
petty-cash feature. Every file runs in the runner's transaction; from 0002 on each starts with
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
