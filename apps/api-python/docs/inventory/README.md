# Inventories

Extracts from the .NET API, its tests and the web and mobile clients, produced by read-only
Sonnet readers so that implementers never have to read the C# code. They are inputs to
`docs/04` to `docs/07`; where an inventory and the .NET code disagree, the code and its
tests win and the inventory is corrected in the same change.

| File | Covers | Feeds |
|---|---|---|
| `inventory-http-contract.md` | every endpoint, DTO, enum, header, error shape; what web, mobile and `@xcode/shared` depend on; naming audit | `docs/06-http-contract.md`, prompts 04 to 09 |
| `inventory-persistence.md` | every table, column, index, constraint, query filter, concurrency token, raw SQL, seed, provisioning | `docs/04-schema.md`, `docs/10-data-migration.md`, prompts 02, 10 |
| `inventory-domain.md` | every business rule, invariant, computation, use-case flow, permission matrix | `docs/05-routines.md`, prompts 03, 05, 06, 07 |
| `inventory-auth.md` | sign-in, codes, devices, tokens, lockout, hashing parameters, forwarded headers, startup checks | `docs/07-auth.md`, prompts 03, 04 |
| `inventory-tests.md` | every .NET test class and the behaviours it pins | `docs/09-testing.md` section 4 crosswalk, prompt 11 |
| `inventory-petty-cash.md` | the uncommitted petty-cash feature: entities and rules `PC-*`, table, endpoints `P01` to `P10`, DTOs, tests, client dependencies | `docs/04-schema.md` 6.2, `docs/05-routines.md` 4.9, `docs/06-http-contract.md` 2.11, prompt 08 |
| `inventory-expenses-reports.md` | the .NET changes of 9 and 10 October: central expenses `CE-*`, scheduled runs and pauses `SR-*`, reports and exports `RP-*`, day capture `RD-*`, list filters `LF-*`, fleet postings `FP-*`; routes `E01` to `E06`, `G01` to `G04`, `D01`, `D02`, `X02` to `X04`, `S53` to `S56`; tests and client reads | `docs/04-schema.md` 14, `docs/05-routines.md` 11, `docs/06-http-contract.md` 2.13, prompt 08b |
| `inventory-remediation.md` | digest of `.claude/remediation/` findings and reviews that shaped the design | `docs/13-open-questions.md`, prompt 11 |
