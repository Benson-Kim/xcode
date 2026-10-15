# xcode_api.http

Inbound adapter (the "UI" ring): routers are the screens, Pydantic models the state holders.
Imports `application`, `domain`, `settings` and FastAPI/Pydantic only; adapters arrive
through the container on `app.state`.

See `docs/01-architecture.md` sections 3, 5 and 6, `docs/06-http-contract.md`.
