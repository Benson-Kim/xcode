# xcode_api.domain

The innermost ring: entities, value objects, enumerations, outcomes, the refusal error
vocabulary and the few pure policies the API tier applies itself. Standard library only;
`tests/unit/test_layers.py` fails on any other import.

Rules that need data (uniqueness, versions, caps, lockout, tenant scope, due dates) live in
PostgreSQL routines, not here. See `docs/01-architecture.md` section 3.

Modules: `values.py` (value objects, `CodedEnum`, `WriteResult`), `identity.py`, `tenancy.py`,
`setup.py`, `revenue.py` (records and enumerations mirroring the schema). Every enumeration
that the database stores has its parity test in `tests/db/test_enum_parity.py`.
