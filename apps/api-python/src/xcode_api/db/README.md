# xcode_api.db

The PostgreSQL data layer: pool, per-call transaction helper, SQLSTATE translation,
composite-row adapters, the repository implementations (`routines/`) and the migration
runner. Implements the repository Protocols declared in `application/repositories.py`;
never imported by `http/` or `application/`.

See `docs/01-architecture.md` sections 3 and 4, `docs/03-database.md`.
