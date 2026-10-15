# xcode_api.application

Use cases and ports. Pure: imports `domain` and the standard library only.

- `ports.py`: `Clock`, `TokenIssuer`, `PinHasher`, `CodeHasher`, `Mailer`, `RateLimiter`.
- `repositories.py`: `IdentityRepository`, `TenancyRepository`, `SetupRepository`,
  `RevenueRepository`, `OpsRepository` (Protocols, one method per routine).
- `errors.py`: `TransientFailure`, `IntegrityBug`.
- `auth/`, `access/`, `organization/`, `setup/`, `revenue/`, `pettycash/`, `ops/`: one module per use case
  (`<verb>_<noun>.py`: `<Verb><Noun>Command` + `<Verb><Noun>.execute`).

See `docs/01-architecture.md` sections 2 and 3.
