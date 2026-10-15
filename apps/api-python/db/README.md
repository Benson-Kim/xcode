# db/ : everything that runs inside PostgreSQL

Reviewed by DBAs. Nothing here is generated; every file is hand-written SQL.

| Folder | Contents | Applied by |
|---|---|---|
| `roles/` | role creation and grants (idempotent) | DBA, local compose init, test harness |
| `migrations/` | versioned schema and data changes, `NNNN_name.sql` + `NNNN_name.down.sql` | `xcode-api db migrate` |
| `routines/` | one routine or type per file, `CREATE OR REPLACE`, applied in lexical order on every deploy | `xcode-api db routines` (also run by `db migrate`) |
| `seeds/` | development demo data | `xcode-api seed-demo` (development only) |

Rules: `docs/03-database.md`. Catalogue of routines: `docs/05-routines.md`. Table spec:
`docs/04-schema.md`.
