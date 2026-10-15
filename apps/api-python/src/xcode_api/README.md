# xcode_api package

Module responsibilities and the dependency rule are in `docs/01-architecture.md`.
Short version (dependencies point inwards: http -> application <- db/security/infra; all
depend on domain; domain depends on nothing):

```
main.py            create_app(settings, container=None): HTTP composition root
container.py       Container and build_container(settings, pool, ...): wiring
settings.py        XCODE_* settings
domain/            entities, values, enums, outcomes, refusal errors, pure policies (stdlib only)
application/       use cases per area, ports, repository protocols (stdlib + domain only)
http/              inbound adapter: middleware, errors, dependencies, schemas/, routers/
db/                outbound adapter: pool, session helper, SQLSTATE translation, routines/ gateways, migrate runner
security/          outbound adapter: tokens, PIN hashing, codes, refresh tokens
infra/             outbound adapter: clock, mail, logging, rate limiting
cli/               xcode-api command line (composition root)
```
