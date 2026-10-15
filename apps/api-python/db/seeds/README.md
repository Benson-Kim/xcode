# Demo seed (development only)

The demo is the routine `api.ops_seed_demo` (`db/routines/60_ops/`), run as `xcode_operator`
by `xcode-api seed-demo` or, with `XCODE_DEMO_SEED=true`, at startup. Both refuse outside
`XCODE_ENV=development` before connecting, and the routine refuses again
(`seed_development_only`). A database holding any organization but the demo is never seeded
(`seed_exists`). It mirrors the .NET `DemoSeed` (`docs/inventory/inventory-persistence.md`
section 8.1) and adds a fleet history the .NET seed did not have.

| Login | Phone | Role | PIN | Scope |
|---|---|---|---|---|
| `antony.maina@shamayah.co.ke` | `+254733520614` | Owner | 4826 | all companies |
| `peter.otieno@zurigenesis.co.ke` | `+254722410355` | Office admin | 1379 | all companies |
| `brian.mwangi@metrotrans.co.ke` | `+254700111222` | Fleet manager | none (sets one with an email code) | all companies |
| `wanjiru.kamau@zurigenesis.co.ke` | `+254712345678` | Revenue clerk | 2580 | Zuri Genesis only |

The CLI hashes the PINs as the API does (`XCODE_AUTH_PIN_ITERATIONS`). The routine stores a
hash only on an account the run creates, so a PIN changed during development survives a
reseed. Every run makes the four logins active again.

What else is created, through the same `api.*` routines the clients call (so the change log,
versions and dates read as real use):
- the organization `Demo Fleet` (`demo-fleet`) with default localization, branding and policy;
- the expense catalogue when the organization has none: three main categories, the .NET
  three categories and 13 items;
- when the organization has no vehicle, six weeks of history written day by day from 42 days
  back: two companies (Zuri Genesis, Metro Trans), six vehicles with fleet numbers and dated
  target sets (one joined two weeks ago, one away and back), scheduled items of every
  frequency a new item can have (weekly, monthly, last day of the month, yearly; daily is
  retired) and two savings, investments, revenue with missing days, no-earnings and low-day
  reasons and corrections (records at version 2), and petty cash in every entry state.

A second run answers `created: false` and adds nothing. One run takes a few seconds, more
than `xcode_operator`'s 5 s statement timeout, so the gateway raises it for this one call.
`tests/support/scenario.py` `seed_10x` multiplies the seeded fleet for `EXPLAIN` runs.
