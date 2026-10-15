# xcode-api (Python + PostgreSQL rewrite of `apps/api`)

Status: in conversion. `docs/` holds the complete specification and the agent prompts
(`docs/prompts/`, in order) for converting the .NET API to Python with business rules in
PostgreSQL routines. Prompts 00 to 08 and 07b are implemented (bootstrap, PostgreSQL
foundation, schema, identity and tenancy, auth, access and people, setup, revenue, the design
notes v2.29 to v2.33, petty cash); 08b (expenses and reports), 09 (operability) and 10 (data
migration) are being built. The status per prompt and the .NET drift register are in
`docs/prompts/README.md`; the operator's procedures are `deploy/runbook.md`. When the
conversion is accepted the folder is renamed to `apps/api` and the .NET project retired.

## Reading order

| Document | What it fixes |
|---|---|
| `docs/00-principles.md` | the ten principles as checkable rules, the zero-trust tenets, the PR checklist |
| `docs/01-architecture.md` | rings and the inward dependency rule, package map, request lifecycle, locality table, endpoint checklist |
| `docs/02-stack.md` | technology decisions (ADR-1 to ADR-15) |
| `docs/03-database.md` | schemas, roles, RLS, routine conventions, SQLSTATE protocol, migration runner, zero-trust checks |
| `docs/04-schema.md` | every table, column, constraint and index |
| `docs/05-routines.md` | every `api.*` routine: signature, rules, errors, tests |
| `docs/06-http-contract.md` | every endpoint exactly as the web and mobile clients use it today |
| `docs/07-auth.md` | sign-in, codes, devices, tokens, lockout, hashing parameters |
| `docs/08-operability.md` | settings, logging, health, CLI, deployment, runbook, safety switches |
| `docs/09-testing.md` | harness, layers of tests, crosswalk from the .NET suite |
| `docs/10-data-migration.md` | SQL Server to PostgreSQL copy and cutover |
| `docs/11-naming.md` | fixed names and domain vocabulary (`xcode`, never `Auth`) |
| `docs/12-security.md` | zero-trust control matrix with the test for each control |
| `docs/13-open-questions.md` | decisions the owners must make |
| `docs/inventory/` | extracts from the .NET code and clients that the documents above were built from |
| `docs/prompts/` | the copy-paste prompts for the implementing agents, in order |

## Layout

```
db/          roles, migrations, routines (one file per routine), seeds
src/         xcode_api package: domain, application, http, db, security, infra, cli
tests/       unit, db (routines, structure, runner), api (HTTP contract), support
deploy/      container and CI specification
docs/        everything above
```

## Local development

```
docker compose up -d postgres          # PostgreSQL 18 with roles from db/roles
cp .env.example .env
pip install -e . -r requirements-dev.txt
xcode-api db migrate                   # as xcode_owner (XCODE_MIGRATION_DATABASE_URL)
xcode-api seed-demo                    # development only, as xcode_operator (db/seeds/README.md)
xcode-api serve                        # as xcode_app (XCODE_DATABASE_URL), port 5000
pytest -n auto
```

## Non-negotiables (details in the documents)

- Rules live in PostgreSQL routines reviewed by DBAs; Python validates shape, routines decide.
- `xcode_app` can only execute `api.*` (not `api.ops_*`); the CLI's user and seed commands connect as `xcode_operator`, which can execute only `api.ops_*` and `api.meta_*`; routines run under row-level security as a non-owner role.
- Dependencies point inwards: `http -> application <- db/security/infra`, all on `domain`, which imports nothing.
- The HTTP contract the web and mobile clients use today is preserved byte for byte.
- Every control, rule and invariant has a named test; a test that fakes the capability under test is not evidence.
