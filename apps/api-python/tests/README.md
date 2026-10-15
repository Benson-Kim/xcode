# Tests

Strategy and the crosswalk from the .NET test classes are in `docs/09-testing.md`.

| Folder | Scope | Database |
|---|---|---|
| `unit/` | pure Python: settings validation, token issuer, PIN hasher, code format, layer rule, use cases with the fakes in `support/fakes.py`, rate limiter contract (both adapters), problem-details encoding | none (rate limiter postgres adapter test lives in `db/`) |
| `db/` | routines called directly through psycopg as `xcode_app`; structure tests as `xcode_owner`; migration runner | real PostgreSQL, one database per test from a template |
| `api/` | HTTP contract through httpx ASGI transport against the real app with the real database | same |
| `support/` | fixtures shared by all: database template, scenario builder, manual clock, mail spy, statement counter | |

No SQLite, no mocked gateway in `db/` or `api/`. A test that fakes the capability under test
is not evidence.

Schema tests in `db/` (`docs/04-schema.md` section 11):

| File | Proves |
|---|---|
| `test_structure.py`, `test_schema_structure.py` | every `db verify` check passes on the migrated schema, and each one names the object a negative test breaks (dropped index, disabled RLS, extra grant, missing trigger, loose foreign key) |
| `test_enum_parity.py` | code tables, `CHECK (... IN ...)` lists and the permission catalogue equal the `domain/` enums and `support/permission_catalogue.json` |
| `test_tenancy_isolation.py` | as `xcode_api_executor`, each tenant table hides another organization's rows and refuses rows naming it (`42501`) |
| `test_constraints.py` | each CHECK, unique constraint, exclusion, foreign key and trigger refuses a violating row by SQLSTATE and name; completeness tests fail on a constraint without a case |
| `test_grants.py` | append-only tables refuse `UPDATE`/`DELETE`; no write beyond the declared ones; `xcode_app`/`xcode_operator` read nothing; `xcode_readonly` reads code tables and the catalogue only |

The template database is built once and kept frozen (`xcode_template`); after changing a
migration, drop it (`UPDATE pg_database SET datallowconn = true WHERE datname =
'xcode_template'; DROP DATABASE xcode_template;`) so the next run rebuilds it.
