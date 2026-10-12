# HTTP contract

What the Python API must put on the wire so that the existing web proxy, the mobile app and
the shared package keep working unchanged. Source: `docs/inventory/inventory-http-contract.md`
(the extract from the .NET code and the clients; its section numbers are cited as
`inv 2.3`). This document is normative; the inventory holds the per-endpoint message lists
and client behaviours that are too long to repeat. When the two disagree, the .NET code and
its tests decide, the inventory is corrected, and this document follows.

## 1. Global conventions

### 1.1 Paths, callers, versions

- No prefix, no version segment: routes start at `/auth`, `/setup`, `/health`, `/openapi`.
- Two callers: the mobile app directly, and the Next.js server (never a browser) through
  its proxy, which forwards `Authorization: Bearer`, adds `X-Request-ID`, optionally
  `X-Forwarded-For`, and sends `Content-Type: application/json` only with a non-empty body
  (`inv 4.2`). Both time out after 15 s; a slow answer is "offline" to them.
- Routing is case-insensitive in .NET and trailing slashes are ignored. FastAPI is
  case-sensitive; the clients send lower-case paths without trailing slashes, so this is an
  accepted deviation (section 1.12). `{id}` segments under `/setup/**` are UUIDs: a
  non-UUID is 404 with an empty body, not 400 (route constraint parity).

### 1.2 JSON

| Rule | Detail |
|---|---|
| Property names | camelCase on output; the first letter of the .NET record property lower-cased. The old misspelling `useGroupping` is still accepted on the localization section save (the current name `useGrouping` wins when both are sent) and still served beside `useGrouping` in the appearance `formats`; the settings read serves `useGrouping` only (`inv` drift log entry 10; `docs/13-open-questions.md` question 22) |
| Input matching | exact camelCase (accepted deviation from .NET's case-insensitive matching; both clients send camelCase). Unknown properties are ignored |
| Missing versus `null` | a missing property takes the field default (`""` for `AuthRequest` strings, `null`, `0`, `false`); an explicit `null` for a required string is a 400 |
| Nulls | always written, never omitted. The only exception is problem details, whose optional members (`detail`, `instance`) are omitted when null |
| Enumerations | integers for `kind` (1 Cost, 2 Savings), `frequency` (1 Daily legacy, 2 Weekly, 3 Monthly, 4 Yearly), `bucket` (1, 2, 3). Strings for auth `status`, revenue cell `status`, revenue `reason` (`Garage`, `Arrest`, `No Crew`, `Other`), `scopeMode`, `themeMode`, `datePattern`, `weekNumbering`, periods, petty-cash `kind` (`cash`, `expense`, `credit`) and `status` (`waiting`, `approved`, `sentBack`, `null` for cash) |
| Numbers | money and other decimals are JSON numbers (`21000`, `1500.00`, `0.5`), never strings; `pydantic` must serialise `Decimal` as a number. `long` versions and `double` font scale are numbers. Numeric strings in input are accepted. An input amount must fit a .NET `decimal` (finite, at most 2^96 - 1 in size): beyond it the body is refused naming the field, as the .NET binder refused it; digits past 28 decimal places are rounded away as .NET read them, so `1e-999999` is 0 (`http/schemas/common.py` `_to_decimal`). An input integer must fit the type its routine parameter holds (`int` fields -2^31 to 2^31 - 1, `long` versions -2^63 to 2^63 - 1): beyond it the body is refused naming the field, as the .NET binder refused it; psycopg would otherwise send the value as `bigint` or `numeric` and the routine call would fail (bounded `Int32`/`Int64` types in each schema module) |
| Dates | `yyyy-MM-dd` in bodies, responses, route segments and query strings |
| Text lengths | counted in code points (`char_length`, `docs/04-schema.md` section 1), where .NET counts UTF-16 units: a text with characters outside the Basic Multilingual Plane (emoji) may hold up to twice as many of them as .NET accepts, and no limit is stricter than .NET's. An accepted deviation, as for auth (`docs/07-auth.md` section 10 row 4) |
| Instants | ISO-8601 UTC with offset `+00:00`, for example `2026-10-07T05:25:29.123456+00:00` (six fractional digits; .NET wrote up to seven; clients parse with `new Date`) |
| UUIDs | lower-case hyphenated |
| Phone numbers | normalised `+254XXXXXXXXX` in storage and output; inputs accept `+254...`, `254...`, `07...`, `7...` with a subscriber part `[17][0-9]{8}` |
| Content type | responses `application/json; charset=utf-8`, problems `application/problem+json`, health text `text/plain` for live and ready |

### 1.3 Authentication and the per-request session check

- `Authorization: Bearer <access JWT>` only. No cookies, no API keys, no query tokens.
- Access token (`docs/07-auth.md` section "Parameters"): HS256, `typ: JWT`, `iss` and
  `aud` from settings (defaults `xcode-api`, `xcode-clients`), `nbf` = issue time, `exp` =
  issue time plus the organization's `accessTokenMinutes`, no `iat`, no `jti`, zero clock
  skew. Claims: `sub`, `device`, `version` (security version as a string), `org`, `role`,
  `first_name`, `last_name`, `permission` (a JSON array when two or more, a bare string when
  exactly one). Only `exp` is ever decoded by a client.
- After signature and lifetime, every authenticated request calls
  `api.auth_resolve_session(p_user_id, p_device_id, p_security_version, p_now)`; it fails
  (401, empty body) unless the user is active, the version matches, and the device is
  trusted and unexpired. Bumping the security version, removing the user, or revoking or
  expiring the device therefore kills outstanding tokens at once.
- Authorization is then done by the routine the endpoint calls: membership, permission and
  data scope are checked in the database for every call, never from claims. The one
  exception is `GET /auth/session`, which echoes the token's claims.

### 1.4 Headers

| Header | Rule |
|---|---|
| `X-Request-ID` | inbound value accepted when 1 to 128 printable ASCII characters, else a new UUID; echoed on every response including 401, 404, 413, 429 and 500; copied into every problem body as `requestId`; bound to the log context |
| `X-Forwarded-For` | honoured only when the immediate peer is in `XCODE_TRUSTED_PROXIES` (default loopback), rightmost untrusted address; only this header is processed; used for the rate-limit partition and the sign-in trail |
| `WWW-Authenticate: Bearer` | on every 401 (.NET sent it only when its bearer handler challenged; the `/auth` envelope 401s carry it too, an accepted addition no client reads) |
| `Allow` | on 405 |
| `Retry-After` | on 429 (seconds to the window end) and on 503 from a transient failure (`1`). Additions to the .NET contract; no client reads them |
| `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` | on every response; no `Server` header (`docs/12-security.md`) |
| Device or client identity headers | none; the device id travels in the body (`deviceId`) and in the `device` claim |
| `Content-Encoding`, `Vary: Accept-Encoding` | gzip for `/setup/**` answers above 1 KiB when the client accepts it (the .NET API also offered Brotli; gzip is what the phone sends); never on `/auth/**` (byte-for-byte rule) or health |

### 1.5 Middleware order

1. forwarded headers (trusted proxies only); 2. request id; 3. exception handlers; 4. CORS;
5. body cap; 6. security headers; 7. routers. The auth rate limit is the first dependency
of every `/auth` route, so it also runs before authentication of `GET /auth/session` and the
revoke route: in .NET `UseRateLimiter` came before `UseAuthentication` and
`UseAuthorization` (`Program.cs:169-171`), so a request without a valid token is charged and,
past the limit, answered 429 rather than 401. `X-Request-ID` is present on 429 and 401.

### 1.6 Error model: three vocabularies

**(A) `/auth/**`: the `AuthResponse` envelope**, always all seven properties in this order:
`status, accessToken, refreshToken, retryAfterSeconds, developmentCode, maskedEmail, minimumPinLength`.

| `status` | HTTP | Extras | Produced by |
|---|---|---|---|
| `authenticated` | 200 | `accessToken`, `refreshToken` | A01, A02, A03, A06, A09, A10 |
| `verification_required` | 202 | `maskedEmail`; `developmentCode` in development mode | A01, A02 |
| `check_email` | 202 | `developmentCode` in development mode | A04, A07 |
| `code_verified` | 200 | | A05, A08 |
| `paused` | 423 | `retryAfterSeconds` (integer > 0) | A01, A02 |
| `authentication_failed` | 401 | | A01, A02, A03, A05, A06, A08, A09, A10 |
| `invalid_pin` | 400 | `minimumPinLength` (4..8) | A06, A09 |
| `invalid_request` | 400 | | pre-validation of A01 to A12 |
| `signed_out` | 200 | | A11 |
| `device_revoked` | 200 | | A12 |
| `service_unavailable` | 503 | | A01, A02 (new-device mail failed) |

Empty bodies on `/auth/**`: 401 from the bearer check (session and revoke routes), 403 from
revoking another device, 429, and the framework 404 and 405.

**(B) `/setup/**`: RFC 7807 `application/problem+json`**
`{ "type": <URL>, "title": ..., "status": <int>, "detail": ... (omitted when null), "requestId": ... }`
plus the extension members below. Clients read `detail`, `title`, `status`, `current`
and never `type`. `type` is `about:blank` (accepted deviation from the
RFC 9110 section URLs .NET emitted).

| Condition | Status | `title` | `detail` |
|---|---|---|---|
| not a member, missing permission, outside own scope for a grant, tenant guard | 403 | `Not permitted in this organization or data scope.` | the specific sentence when the catalogue (section 3) has one, else omitted |
| record outside the caller's scope or missing | 404 | `Record not found in your scope.` | omitted |
| validation or business-rule refusal | 400 | `Invalid setup change` | the sentence from section 3 (what the UI shows) |
| stale `version` on people and settings | 409 | `Settings changed. Reload before saving.` | omitted |
| unique or foreign-key violation | 409 | `A conflicting record exists. Reload before saving.` | omitted |
| revenue: a different record exists for the day | 409 | `This day already has a different record.` | `This day was changed after you opened it. Check the current record and save again.` plus `current` (a `RevenueCellDto`) |
| revenue: the record moved during the save | 409 | `This day was changed by another save.` | `Reload the current record and try again.` |
| petty cash: stale or missing `version` on change, approve, send back, remove | 409 | `This entry has changed.` | `This entry was changed after you opened it. Check it and save again.` plus `current` (a `PettyCashEntryDto`) |
| petty cash: create with an `id` another person already saved | 409 | `This entry has changed.` | `This entry was already saved by someone else. Reload and try again.`; `current` is `null` |
| petty cash: the entry moved during the save | 409 | `This entry was changed by another save.` | `Reload and try again.` |
| petty cash: cash taken back would leave the float below zero | 400 | `Invalid setup change` | `This takes the float below zero, which needs the permission "Send money that takes a float below zero".` plus `balanceAfter` (number) |
| malformed JSON or wrong field types | 400 | `Invalid setup change` | the first validation message; plus `errors` (field path to messages). .NET answered an empty 400; clients read `detail` or `title`, so the body is compatible |
| missing or wrong `Content-Type` on a body route | 415 | empty body | |

Organization settings section save only (`O02`): plain JSON, no `title`:
`400 {"detail":"Enter an organization name and a lowercase slug using letters, numbers, and hyphens."}`
and `409 {"detail":"This organization slug is already in use."}`.

**(C) Anything unhandled: 500** `application/problem+json`
`{ "type": "about:blank", "title": "An error occurred while processing your request.", "status": 500, "traceId": ..., "requestId": ... }`
with no exception detail. `TransientFailure` (pool exhausted, serialization failure after
retries, connection lost, PIN hashing at capacity on the `/auth` routes that derive a PIN)
is **503** with the same shape, `title` `The service is not available right now.`
and `Retry-After: 1`. Clients treat every status of 500 or more as "try later"; the web
proxy rewrites them to 503 `service_unavailable`.

Status by family (`inv 1.8`): 400, 401, 403, 404, 409, 423 (auth only), 429 (auth only), 500,
503 (auth mail failure; readiness).

### 1.7 Requests and binding

- Body routes require `Content-Type: application/json` and a non-empty JSON body: wrong or
  missing content type is 415 (empty body), empty or invalid JSON is 400 (section 1.6 B or
  the auth envelope). Routes without a body parameter ignore any body sent.
- The only optional body is `PersonLifecycleRequest` on activate and deactivate (no body and
  no content type bind as empty, and the use case then answers 409 "reload").
- Query and route values: `int`, `long`, `bool` (`true`/`false`), UUID, date; an unparsable
  value is 400. Defaults: `page=1`, `pageSize=25`, dashboard `period=week`, history
  `includeTotal=true`.
- Paging (`Page<T>`): `page` 1..100000 and `pageSize` 1..100, else 400
  `Page must be 1–100000 and page size 1–100.` (EN DASH U+2013). Response
  `{ items, pageNumber, pageSize, total }`.
- Typed reasons: optional on most writes; after trimming 1..500 characters, else 400
  `A reason of 1–500 characters is required.`; appended to the automatic sentence as
  `. Reason: <typed>.` (no second full stop after `.`, `!` or `?`).
- On the `/setup` routes, a query value or a JSON body string (keys included) holding U+0000
  or an unpaired surrogate is 400 `Invalid setup change` with the detail
  `Text cannot contain U+0000 or an unpaired surrogate.` and `errors` naming `query.<name>`
  or `body`, checked by `SetupRoute` before authentication like the 415 (accepted
  deviation: SQL Server stored such text; PostgreSQL text cannot, and the request
  otherwise ended as a 500).
- Body cap: 1 MiB, answered 413 problem (the logo data URL alone is up to about 350 KB; the
  web proxy caps at 1 MiB).

### 1.8 Rate limiting

- One policy, `auth`: fixed window of 60 s, `XCODE_RATE_LIMIT_AUTH_PER_MINUTE` permits (default 30;
  10000 in testing), partition = client address after forwarded-header processing or
  `unknown`. Applied to all 13 `/auth` routes including `GET /auth/session` and the revoke
  route; nothing else is limited.
- Refusal: 429, empty body, `Retry-After`, `X-Request-ID`. (The web proxy turns an empty 429
  into 503 for the browser; giving 429 a body is an open question, not a change made here.)
- Account pausing (423 `paused`) is separate (`docs/07-auth.md`).

### 1.9 CORS

Allow-list of exact origins from `XCODE_CORS_ORIGINS` (empty means none), any method,
any header, no credentials, no exposed headers. No current client is a browser origin.

### 1.10 Health

| Route | Behaviour |
|---|---|
| `GET /health/live` | 200 `Healthy` (`text/plain`), no database call |
| `GET /health/ready` | 200 `Healthy` when `SELECT 1` succeeds within 10 s as `xcode_app` and the contract version matches; else 503 `Unhealthy` |
| `GET /health` | 200 `{"status":"ok"}` (legacy JSON), no database call |

None is authenticated, rate limited or checked against `XCODE_ALLOWED_HOSTS` (probes call by
address); all carry `X-Request-ID`.

### 1.11 OpenAPI

`GET /openapi/v1.json` only when `XCODE_OPENAPI_ENABLED` (on in development and
testing, off in production). The document must satisfy the .NET `OpenApiTests`: `paths`
contains `/auth/sign-in` and `/setup/people`; `POST /auth/sign-in` documents 202 and 423
with `application/json` content referencing `#/components/schemas/AuthResponse` and has no
`security`; `POST /setup/people/{id}/deactivate` documents 409 with
`application/problem+json` referencing `#/components/schemas/ProblemDetails` and
`security: [{"Bearer": []}]`; `components.securitySchemes.Bearer` is `type: http`,
`scheme: bearer`, `bearerFormat: JWT`. Every secured operation documents 401. Tags:
`Setup`, `Organization` (settings, logo, appearance, preferences), `Revenue`, `Petty cash`
(section 2.11); the .NET API also tags `Central expenses` and `Reports` (drift register rows
1 and 2); auth routes untagged. Operation ids are the `operationId` column of section 2.

### 1.12 Accepted deviations from the .NET wire

| Deviation | Why it is safe |
|---|---|
| Input property names matched case-sensitively | both clients send exact camelCase |
| Instants with six fractional digits | parsed with `new Date`; .NET trimmed trailing zeros anyway |
| Problem `type` is `about:blank` | no client reads `type` |
| `requestId` on every problem body, `Retry-After` on 429 and 503, security headers | additive; no client parses them; `AuthTests` byte comparisons exclude per-request headers by name |
| Malformed JSON answered with a problem body instead of an empty 400 | clients fall back to `title` |
| 413 at 1 MiB | the web proxy already refuses larger bodies; .NET had no cap |
| Case-sensitive paths, no trailing-slash tolerance | clients use canonical lower-case paths |

Everything else, including every message string in section 3, is reproduced exactly.

## 2. Endpoint catalogue

Columns: `operationId` (OpenAPI; auth and health routes have none); `Permission` uses the
legend of `inv 2.0` (member, perm, any of, scope); `Routine` is the `api.*` routine the use
case tells (`docs/05-routines.md`); `Budget` is the maximum number of SQL statements per
request, counted by the gateway: anonymous auth routes 1 (sign-in and unlock 2, because
the PIN hash is verified in the process between a lookup and the decision routine),
authenticated routes 2 (session resolution plus the routine), health 0 or 1. The detail columns of the inventory (bodies,
check order, messages) are the contract for each row.

### 2.1 Authentication (`inv 2.2`, `inv 3.1`)

| ID | Route | Auth | Success | Routine | Budget |
|---|---|---|---|---|---|
| A01 | `POST /auth/sign-in` | anonymous | 200 `authenticated`; 202 `verification_required` | `api.auth_account_lookup`, then `api.auth_sign_in` | 2 |
| A02 | `POST /auth/unlock` | anonymous | same handler as A01 | `api.auth_account_lookup`, then `api.auth_sign_in` | 2 |
| A03 | `POST /auth/verify-device` | anonymous | 200 `authenticated` | `api.auth_verify_device` | 1 |
| A04 | `POST /auth/setup-pin/request` | anonymous | 202 `check_email` | `api.auth_request_code` (purpose `first_setup`) | 1 |
| A05 | `POST /auth/setup-pin/verify` | anonymous | 200 `code_verified` | `api.auth_verify_code` | 1 |
| A06 | `POST /auth/setup-pin/complete` | anonymous | 200 `authenticated` | `api.auth_complete_pin` | 1 |
| A07 | `POST /auth/pin-reset/request` | anonymous | 202 `check_email` | `api.auth_request_code` (purpose `pin_reset`) | 1 |
| A08 | `POST /auth/pin-reset/verify` | anonymous | 200 `code_verified` | `api.auth_verify_code` | 1 |
| A09 | `POST /auth/pin-reset/complete` | anonymous | 200 `authenticated` | `api.auth_account_lookup` (the hash the new PIN must differ from), then `api.auth_complete_pin` | 2 |
| A10 | `POST /auth/refresh` | anonymous (token in body) | 200 `authenticated` (rotated pair) | `api.auth_refresh` | 1 |
| A11 | `POST /auth/sign-out` | anonymous (token in body) | 200 `signed_out` always | `api.auth_sign_out` | 1 |
| A12 | `POST /auth/devices/{id}/revoke` | bearer; `id` must equal the `device` claim else 403 empty | 200 `device_revoked` | `api.auth_revoke_device` | 2 |
| A13 | `GET /auth/session` | bearer | 200 `{userId, firstName, lastName, role, permissions}` from the claims | none beyond session resolution | 1 |

Pre-validation (400 `invalid_request`, before any lookup): `deviceId` 1..128; `phoneNumber`
at most 14; `email` at most 320 and a valid address when non-empty; `pin` at most 8; `code`
at most 32; `refreshToken` at most 256; a `null` for any of the six is a refusal; so are a
U+0000 or an unpaired surrogate in any field (PostgreSQL text cannot hold them), a body that
is not a JSON object of strings, and a body without a JSON content type (accepted
deviations: .NET answered those with an empty 400, which the web proxy turned into 503).
The auth router does not use the generic validation handler: its request models carry the
six string fields defaulting to `""` and the checks above are explicit, so the envelope is
always produced. The rate limit runs before pre-validation, and before authentication on
A12 and A13.

Byte-for-byte rule (`AuthTests`): the 401 `authentication_failed` answers for an unknown
number, a number that does not normalise, an inactive account, a paused account seen from an
untrusted device, an untrusted device past the cap and a wrong PIN from an untrusted device
are identical except for `Date`, `Content-Length` and `X-Request-ID`; the 202 `check_email`
answers of A04 and A07 are identical whether or not mail was sent. Any new per-request
header must be added to the exclusion list of that test.

### 2.2 Access and people (`inv 2.3`, `inv 3.2`, `inv 3.3`)

| ID | Route | Permission | Success | operationId | Routine | Budget |
|---|---|---|---|---|---|---|
| S01 | `GET /setup/access/catalog` | member | `PermissionGroup[]` in catalog order | `GetAccessCatalog` | `api.access_catalog_list` | 2 |
| S02 | `GET /setup/access/roles` | `people.view` | `AccessRole[]` by name | `ListAccessRoles` | `api.access_role_list` (read-only; roles are pre-seeded) | 2 |
| S03 | `GET /setup/access/scope-options` | `people.manage` | `ScopeOptions` | `GetAccessScopeOptions` | `api.access_scope_options` | 2 |
| S04 | `GET /setup/access/me` | member | `MyScope` | `GetMyAccessScope` | `api.access_my_scope` | 2 |
| S05 | `GET /setup/people?page&pageSize&role&status` | `people.view` | `Page<PersonDto>` | `ListPeople` | `api.people_list` | 2 |
| S06 | `GET /setup/people/{id}` | `people.view` | `PersonDto`; 404 | `GetPerson` | `api.people_get` | 2 |
| S07 | `POST /setup/people` | `people.manage` + rules | 200 `{id}` | `CreatePerson` | `api.people_create` | 2 |
| S08 | `PUT /setup/people/{id}` | `people.manage` + rules; `version` | 200 `{id}` | `UpdatePerson` | `api.people_update` | 2 |
| S09 | `POST /setup/people/{id}/activate` | `people.manage`; optional body | 200 `{id}` | `ActivatePerson` | `api.people_set_active` | 2 |
| S10 | `POST /setup/people/{id}/deactivate` | `people.manage`; optional body; typed reason required | 200 `{id}` | `DeactivatePerson` | `api.people_set_active` | 2 |
| S11 | `POST /setup/people/{id}/sign-out` | `people.manage` | 200 `{id}` | `SignOutPerson` | `api.people_sign_out` | 2 |

S05 filters (.NET `AccessUseCases.List`, `ListFilterTests`): `role` keeps people holding the
role of that name, letter case ignored as on SQL Server's default collation and as role
names are unique (an unknown name gives an empty page; empty or `all` means no filter);
`status` is `active` (active with a PIN), `waiting` (active, no PIN yet) or `none`
(inactive), empty or `all` means no filter, anything else (letter case counts) is a 400
`people_filter_status_invalid`, checked after the permission and the page bounds as in
.NET. `total` counts the filtered people. Built by `api.people_list` `p_role`/`p_status`.

The sixteen-step check order of S07/S08 and the exact 400/403/404/409 sentences are
`inv 2.3`; they are reproduced in section 3 as message codes.

### 2.3 Companies and vehicles (`inv 2.4`, `inv 2.5`, `inv 3.4`)

| ID | Route | Permission | Success | operationId | Routine | Budget |
|---|---|---|---|---|---|---|
| S12 | `GET /setup/companies?page&pageSize` | `companies.manage` | `Page<CompanyDto>` | `ListSetupCompanies` | `api.setup_company_list` | 2 |
| S13 | `POST /setup/companies` | `companies.manage` and all-companies scope | `{id}` | `CreateSetupCompany` | `api.setup_company_create` | 2 |
| S14 | `PUT /setup/companies/{id}` | `companies.manage` | `{id}` | `RenameSetupCompany` | `api.setup_company_rename` | 2 |
| S15 | `POST /setup/companies/{id}/archive` | `companies.manage` | `{id}` | `ArchiveSetupCompany` | `api.setup_company_archive` | 2 |
| S16 | `POST /setup/companies/{id}/restore` | `companies.manage` | `{id}` | `RestoreSetupCompany` | `api.setup_company_restore` | 2 |
| S17 | `GET /setup/vehicles?page&pageSize&companyId` | any of `vehicles.manage`, `invest.view` | `Page<VehicleDto>` (targets hidden from investment viewers) | `ListSetupVehicles` | `api.setup_vehicle_list` | 2 |
| S18 | `POST /setup/vehicles` | `vehicles.manage` | `{id}` | `CreateSetupVehicle` | `api.setup_vehicle_create` | 2 |
| S19 | `PUT /setup/vehicles/{id}` | `vehicles.manage` | `{id}` | `UpdateSetupVehicle` | `api.setup_vehicle_update` | 2 |
| S20 | `GET /setup/vehicles/company-options` | `vehicles.manage` | `CompanyOption[]` | `ListVehicleCompanyOptions` | `api.setup_company_options` | 2 |
| S21 | `POST /setup/vehicles/{id}/retire` | `vehicles.manage` | `{id}` | `RetireSetupVehicle` | `api.setup_vehicle_retire` | 2 |
| S22 | `POST /setup/vehicles/{id}/restore` | `vehicles.manage` | `{id}` | `RestoreSetupVehicle` | `api.setup_vehicle_restore` | 2 |
| S23 | `GET /setup/vehicles/{id}/report?period` or `?from&through` | `vehicles.manage` | `VehicleReport` | `GetSetupVehicleReport` | `api.setup_vehicle_report` | 2 |

S17 `companyId` (.NET `SetupRepository.Vehicles`, `ListFilterTests`) keeps that company's
vehicles among those the caller sees, and the total counts the filtered set; absent means no
filter. A company outside the caller's scope gives an empty page, not a 403 or 404.

### 2.4 Scheduled expenses and savings (`inv 2.6`, `inv 3.5`)

| ID | Route | Permission | Success | operationId | Routine | Budget |
|---|---|---|---|---|---|---|
| S24 | `GET /setup/recurring?page&pageSize&kind&companyId&status` | `commitments.view` | `Page<RecurringDto>` | `ListSetupRecurring` | `api.setup_recurring_list` | 2 |
| S25 | `GET /setup/recurring/vehicle-options` | `commitments.manage` | `VehicleOption[]` | `ListRecurringVehicleOptions` | `api.setup_vehicle_options` | 2 |
| S26 | `POST /setup/recurring` | `commitments.manage` | `{id}` | `CreateSetupRecurring` | `api.setup_recurring_create` | 2 |
| S27 | `PUT /setup/recurring/{id}` | `commitments.manage` | `{id}` | `ReviseSetupRecurring` | `api.setup_recurring_revise` | 2 |
| S28 | `POST /setup/recurring/{id}/stop` | `commitments.manage`; body `{confirmed, reason}` | `{id}` | `StopSetupRecurring` | `api.setup_recurring_stop` | 2 |
| S29 | `POST /setup/recurring/{id}/restore` | `commitments.manage` | `{id}` | `CancelSetupRecurringStop` | `api.setup_recurring_cancel_stop` | 2 |

S24 filters (.NET `RecurringFilter.Of` and `SetupRepository`, `ListFilterTests`), each empty
or `all` meaning no filter: `kind` is `cost` or `savings` on the current version, else a 400
`Kind must be cost or savings.`; `companyId` keeps items whose current version shares to a
vehicle of that company the caller sees; `status` is `running` or `stopped`, else a 400
`Status must be running or stopped.`. An item runs while it is not stopped as of today, its
current version has not ended, and it shares to a visible vehicle in the fleet today. Order:
running items first, then current name, then id; the total counts the filtered set. The
three sentences join section 3 as message codes with the routine.

### 2.5 Change log (`inv 2.7`, `inv 3.9`)

| ID | Route | Permission | Success | operationId | Routine | Budget |
|---|---|---|---|---|---|---|
| S30 | `GET /setup/history?page&pageSize&section&from&to&text&before&includeTotal` | `audit.view` | `HistoryPage` `{items, pageNumber, pageSize, total (null only when includeTotal=false), hasMore, nextBefore}` | `ListSetupHistory` | `api.history_list` | 2 |

The response is the uncommitted superset of the .NET shape; its visibility and redaction
rules (`inv 2.7`) are part of the contract. The count is computed by the routine; whether
to cache it per settings version is a later decision (`docs/01-architecture.md` section 4).

### 2.6 Expense catalog (`inv 2.8`)

| ID | Route | Permission | Success | operationId | Routine | Budget |
|---|---|---|---|---|---|---|
| S31 | `GET /setup/expense-categories?page&pageSize` | any of `expenses.view`, `expenses.setup`, `commitments.view` | `Page<ExpenseCategoryDto>` | `ListExpenseCategories` | `api.setup_expense_category_list` | 2 |
| S32 | `GET /setup/expense-items/options` | any of the three plus `commitments.manage` | `ExpenseItemOption[]` | `ListExpenseItemOptions` | `api.setup_expense_item_options` | 2 |
| S33 | `POST /setup/expense-categories` | `expenses.setup` | `{id}` | `CreateExpenseCategory` | `api.setup_expense_category_create` | 2 |
| S34 | `PUT /setup/expense-categories/{id}` | `expenses.setup` | `{id}` | `UpdateExpenseCategory` | `api.setup_expense_category_update` | 2 |
| S35 | `POST /setup/expense-categories/{id}/stop` | `expenses.setup` | `{id}` | `StopExpenseCategory` | `api.setup_expense_category_set_stopped` | 2 |
| S36 | `POST /setup/expense-categories/{id}/restore` | `expenses.setup` | `{id}` | `RestoreExpenseCategory` | `api.setup_expense_category_set_stopped` | 2 |
| S37 | `POST /setup/expense-categories/{id}/items` | `expenses.setup` | `{id}` (item) | `CreateExpenseItem` | `api.setup_expense_item_create` | 2 |
| S38 | `PUT /setup/expense-items/{id}` | `expenses.setup` | `{id}` | `RenameExpenseItem` | `api.setup_expense_item_rename` | 2 |
| S39 | `POST /setup/expense-items/{id}/stop` | `expenses.setup` | `{id}` | `StopExpenseItem` | `api.setup_expense_item_set_stopped` | 2 |
| S40 | `POST /setup/expense-items/{id}/restore` | `expenses.setup` | `{id}` | `RestoreExpenseItem` | `api.setup_expense_item_set_stopped` | 2 |

### 2.7 Investment (`inv 2.9`)

| ID | Route | Permission | Success | operationId | Routine | Budget |
|---|---|---|---|---|---|---|
| S41 | `GET /setup/vehicles/{id}/investment` | `invest.view` | `InvestmentDto` | `GetVehicleInvestment` | `api.setup_investment_get` | 2 |
| S42 | `POST /setup/vehicles/{id}/investment` | `invest.manage` | `{id}` (entry) | `AddVehicleInvestment` | `api.setup_investment_create` | 2 |
| S43 | `PUT /setup/investment/{id}` | `invest.manage` | `{id}` | `UpdateVehicleInvestment` | `api.setup_investment_update` | 2 |
| S44 | `DELETE /setup/investment/{id}` | `invest.manage` | `{id}` | `DeleteVehicleInvestment` | `api.setup_investment_delete` | 2 |

### 2.8 Revenue (`inv 2.10`, `inv 3.6`)

| ID | Route | Permission | Success | operationId | Routine | Budget |
|---|---|---|---|---|---|---|
| R01 | `GET /setup/revenue?weekStart&companyId&vehicleId&page&pageSize` | `revenue.view` | `RevenueWeekDto` with `pageNumber`, `pageSize`, `totalVehicles`, `truncated`, `dayTotals`, `firstGap` (`inv 2.10` and drift log entries 1 and 2: no `page`/`pageSize` means page 1 of up to 500 vehicles with `truncated`; a `vehicleId` request is never paged; totals, `dayTotals` and `firstGap` cover the whole filtered grid) | `GetRevenueWeek` | `api.revenue_week_get` | 2 |
| R02 | `GET /setup/revenue/dashboard?period&companyId` | any of `dash.capture`, `dash.revenue`, `dash.gaps`, `dash.edits` | `RevenueDashboardDto` (cards null without their permission) | `GetRevenueDashboard` | `api.revenue_dashboard_get` | 2 |
| R03 | `PUT /setup/revenue/{vehicleId}/{date}` | any of `revenue.capture`, `revenue.correct`, then per-case rules | 200 `{id, version}` | `SaveRevenue` | `api.revenue_capture` | 2 |

R03 is the capture and offline-replay endpoint. There is no idempotency key: the steps of
`inv 2.10` are the contract, in that order, including the identical-replay answer (step 4)
before date, activity, permission and version checks. The 409 with `current` never follows
a 403. Days are captured in any order: the .NET API refused a new record while an earlier
active day was missing (400 with `earliestMissing`, step 9) until commit 9276c51 removed
that refusal, so there is no such answer here; the week still reports each vehicle's
`earliestMissing`. The day capture (`GET /setup/revenue/day`, `PUT /setup/revenue/day/{date}`)
and the screen export (`GET /setup/revenue/export`) of the same group belong to
`docs/prompts/08b-expenses-reports.md` (drift register rows 3 and 4).

Since 07b D4 the rows R01 to R03 carry the changes of section 2.12, which hold where the two
differ. R01 adds `q` and the gap figures, and R02 is gated by `dash.net` and `dash.gaps`.
R03 adds `capturedAt`, the low-day rule and `revenue.correct` for every saved record. Each
row of the 08b day capture answers as R03 does for that vehicle and day, the back-dating
limit and the low-day threshold included (`docs/05-routines.md` section 10.2).

### 2.9 Organization, appearance, preferences (`inv 2.11`, `inv 3.7`)

| ID | Route | Permission | Success | operationId | Routine | Budget |
|---|---|---|---|---|---|---|
| O01 | `GET /setup/organization/settings` | `organization.manage` | `OrganizationSettingsResponse` | `GetOrganizationSettings` | `api.organization_settings_get` | 2 |
| O02 | `PUT /setup/organization/settings/{section}` | `organization.manage`; `section` in `organization`, `localization`, `branding`, `securityPolicy`, `businessDate`, else 404 | `{section}` | `UpdateOrganizationSettings` | `api.organization_settings_set` | 2 |
| O03 | `PUT /setup/organization/logo` | `organization.manage` | `{logo}` data URL | `UpdateOrganizationLogo` | `api.organization_logo_set` | 2 |
| O04 | `DELETE /setup/organization/logo?reason` | `organization.manage` | `{logo: null}` | `DeleteOrganizationLogo` | `api.organization_logo_delete` | 2 |
| O05 | `GET /setup/appearance` | member | `AppearanceResponse` (includes `lockoutThreshold`, `lockoutMinutes`) | `GetAppearance` | `api.organization_appearance_get` | 2 |
| O06 | `GET /setup/preferences` | member | `PreferencesResponse` | `GetUserPreferences` | `api.preferences_get` | 2 |
| O07 | `PUT /setup/preferences` | member | the saved `UserPreference` | `UpdateUserPreferences` | `api.preferences_set` | 2 |

Section saves merge the posted object onto the stored section (omitted fields keep their
values, `organizationId` ignored, the legacy key `useGroupping` accepted for `useGrouping`
with the current name winning), validate, and answer with no version bump and no log when
nothing changed; a logged save moves `settingsVersion` by exactly one (a localization save
included). The automatic reason sentences and the `SettingNames` words are `inv 3.9`. The
OpenAPI schema names of the four sections are `OrganizationDto`, `LocalizationDto`,
`BrandingDto`, `SecurityPolicyDto` and `UserPreferenceDto` for O07 (same JSON).

Since 07b D4, O01 also serves the section `revenue` (`RevenueSettingsDto`) and O02 accepts it,
as section 2.12 states.

### 2.10 Health and OpenAPI

| ID | Route | Budget |
|---|---|---|
| H01 | `GET /health/live` | 0 |
| H02 | `GET /health/ready` | 1 |
| H03 | `GET /health` | 0 |
| X01 | `GET /openapi/v1.json` (development and testing only) | 0 |

### 2.11 Petty cash (`docs/inventory/inventory-petty-cash.md` sections 4 and 6; `docs/15-design-v2-3.md` B19; tag `Petty cash`)

The .NET feature was re-read on 2026-10-12 (9276c51 plus the working tree); the design
notes' rules (B19, decisions DEC-21 to DEC-29) decide where they differ. Gates are "any of"
the listed permissions; the per-entry rules and check orders are `docs/05-routines.md` 4.9.

| ID | Route | Permission (any of) | Success | operationId | Routine | Budget |
|---|---|---|---|---|---|---|
| P01 | `GET /setup/pettycash/overview?date&period&holderId&from&to` | `pettycash.view` | `PettyCashOverviewDto` | `GetPettyCashOverview` | `api.pettycash_overview_get` | 2 |
| P02 | `GET /setup/pettycash/entries?from&to&holderId&kind&status&q&page&pageSize` | `pettycash.view` | `Page<PettyCashEntryDto>` (`pageSize` default 100) | `ListPettyCashEntries` | `api.pettycash_entry_list` | 2 |
| P03 | `GET /setup/pettycash/options?date` | `pettycash.spend`, `pettycash.spend_other`, `pettycash.edit_own`, `pettycash.edit`, `pettycash.issue`, `pettycash.credit` | `PettyCashOptionsDto` | `GetPettyCashOptions` | `api.pettycash_options_get` | 2 |
| P04 | `GET /setup/pettycash/dashboard` | `dash.pettycash` | `PettyCashDashboardDto` (cards null as DEC-25 says) | `GetPettyCashDashboard` | `api.pettycash_dashboard_get` | 2 |
| P05 | `POST /setup/pettycash/entries` | `pettycash.spend`, `pettycash.spend_other`, `pettycash.issue`, `pettycash.credit` | 200 `PettyCashSaved` (never 201; replay by the client-supplied `id`) | `CreatePettyCashEntry` | `api.pettycash_entry_create` | 2 |
| P06 | `PUT /setup/pettycash/entries/{id}` | `pettycash.edit_own`, `pettycash.edit` | `PettyCashSaved` | `UpdatePettyCashEntry` | `api.pettycash_entry_update` | 2 |
| P07 | `POST /setup/pettycash/entries/{id}/approve` | `pettycash.approve_item` | `PettyCashSaved` | `ApprovePettyCashEntry` | `api.pettycash_entry_approve` | 2 |
| P08 | `POST /setup/pettycash/entries/{id}/send-back` | `pettycash.send_back` | `PettyCashSaved` | `SendBackPettyCashEntry` | `api.pettycash_entry_send_back` | 2 |
| P09 | `POST /setup/pettycash/entries/{id}/remove` | `pettycash.delete_own`, `pettycash.delete`, `pettycash.delete_approved`, `pettycash.delete_cash` | `PettyCashSaved` | `RemovePettyCashEntry` | `api.pettycash_entry_remove` | 2 |
| P10 | `POST /setup/pettycash/approve-day` | `pettycash.approve_day` | `PettyCashDayApproved` `{approved, total, skipped}` | `ApprovePettyCashDay` | `api.pettycash_day_approve` | 2 |
| P11 | `POST /setup/pettycash/approve` | `pettycash.approve_item` | `PettyCashDayApproved` | `ApprovePettyCashEntries` | `api.pettycash_entries_approve` | 2 |
| P12 | `POST /setup/pettycash/entries/{id}/reject` | `pettycash.reject` | `PettyCashSaved` | `RejectPettyCashEntry` | `api.pettycash_entry_reject` | 2 |
| P13 | `POST /setup/pettycash/entries/{id}/reopen` | `pettycash.reopen` | `PettyCashSaved` | `ReopenPettyCashEntry` | `api.pettycash_entry_reopen` | 2 |

The screen export `GET /setup/pettycash/export` (.NET `ExportPettyCash`, drift register row
4) is prompt 08b's. Wire records, in wire order; fields marked + are new in Python and come
last (DEC-29); the rest are `inventory-petty-cash.md` section 4.4:

| Record | Fields |
|---|---|
| `SavePettyCashEntry` (P05, P06) | `kind`, `date`, `unitAmount`, `id`, `holderId`, `vehicleId`, `expenseItemId`, `units` (absent = 1), `payee`, `note`, `reimbursable` (false), `version` |
| `ReviewPettyCashEntry` (P07) | `version` |
| `SendBackPettyCashEntry` (P08) | `version`, `comment` |
| `RemovePettyCashEntry` (P09) | `version`, `reason` (optional for a waiting expense, DEC-28) |
| `DecidePettyCashEntry` (P12, P13) + | `version`, `reason` |
| `ApprovePettyCashDay` (P10) | `date`, `holderId`, `to` |
| `ApprovePettyCashEntries` (P11) | `entries`: `[{id, version}]` |
| `PettyCashSaved` | `id`, `version`, `status`, `balance` |
| `PettyCashDayApproved` | `approved`, `total`, `skipped` |
| `PettyCashOverviewDto` | `businessDate`, `date`, `period` (`day`, `week`, `range`), `from`, `to`, `permissions`, `holders`, `figures`, `floats` |
| `PettyCashPermissionsDto` | `holderId`, `canSpend`, `canViewAll`, `canIssue`, `canIssueNegative`, `canApproveItem`, `canApproveDay`, `approvalLimit`, + `canView`, `canSpendOther`, `canEditOwn`, `canEdit`, `canDeleteOwn`, `canDelete`, `canDeleteApproved`, `canSendBack`, `canReject`, `canReopen`, `canCredit`, `canDeleteCash`, `earliestDate` (the back-dating limit, null for none) |
| `PettyCashHolderDto` | `id`, `name`, `active` |
| `PettyCashFiguresDto` | `openingBalance`, `cashReceived`, `expenses`, `creditNotes`, `moneyOut`, `closingBalance`, `waiting`, `waitingCount` (rejected expenses count in none of them) |
| `PettyCashFloatDto` | `holderId`, `name`, `active`, `cashReceived`, `creditNotes`, `expenses`, `waiting`, `waitingCount`, `approved`, `sentBack`, `balance`, `lastCashOn`, + `rejected` |
| `PettyCashEntryDto` | `id`, `kind`, `holderId`, `holderName`, `date`, `vehicleId`, `registration`, `expenseItemId`, `expenseItemName`, `bucket`, `units`, `unitAmount`, `total`, `payee`, `note`, `reimbursable`, `status` (`waiting`, `sentBack`, `approved`, `rejected`, null), `sentBackNote`, `reviewedByName`, `reviewedAt`, `recordedByName`, `recordedAt`, `updatedAt`, `version`, `canEdit`, `canRemove`, `canReview`, `aboveLimit`, + `rejectReason`, `reopenReason`, `canSendBack`, `canReject`, `canReopen` |
| `PettyCashOptionsDto` | `vehicles` (`id`, `companyId`, `companyName`, `registration`, `active`), `items` (`id`, `name`, `categoryId`, `categoryName`, `bucket`), `holders` |
| `PettyCashDashboardDto` | `float` (`balance`, `waitingCount`, `waitingTotal`, `sentBackCount`, `approvedThisMonth`), `approvals` (`count`, `total`, `approvalLimit`, `aboveLimit`, `holders`: `holderId`, `name`, `count`, `total`, `oldest`) |

The `float` dashboard key and the `from` query name are served under those names (Python
aliases). `kind` and `status` filters are comma lists: trimmed, empty items dropped,
duplicates removed; absent or empty means every kind or status. Approved expenses appear in
the vehicle report (S23) as postings with `source` `pettycash`. A 409 carries `current` (the
entry document, or `null` for a foreign or vanished id); the float-guard 400 carries
`balanceAfter`; the back-dating refusal `record_too_old` carries `earliest`.

Totals: 83 always-on routes in sections 2.1 to 2.11 plus the conditional OpenAPI route (`inv 2`;
petty cash adds P11 to P13 to the 80 counted before), and the routes of section 2.12. This catalogue is not yet the whole
.NET contract: on 2026-10-11 the .NET API served 99 always-on routes. The ones without a row
here (central expenses, reports, day capture, the screen exports, scheduled-item pause,
resume, runs and summary) are rows 1 to 5 of the drift register in `docs/prompts/README.md`;
they get their rows when prompt 08b designs them. Until then the .NET code is the contract
for them.

### 2.12 The design notes v2.29 to v2.33 (prompt 07b)

The routes and body changes of `docs/15-design-v2-3.md`. **Every route in this section is
new in Python and absent from .NET** (measured 2026-10-11); the .NET developer works from
the same notes, and this contract leads when .NET builds one (question 55; the drift check
of each prompt records a difference). The rule ids are those of `docs/15`.

#### 2.12.1 Sign-in routes (`docs/07-auth.md` section 12)

Anonymous unless marked; every one is under the `auth` rate limit; N02 and N07 also under
`auth_pin`. They answer the **step envelope**: the seven properties of section 1.6 A, then
`purpose`, `triesLeft`, `pinProblem`, `deviceToken`, all eleven always present, in that
order, `null` when unused.

| ID | Route | Body | Success and refusals | Routine | Budget |
|---|---|---|---|---|---|
| N01 | `POST /auth/start` | `phoneNumber, deviceId, deviceToken?, deviceName?` | 200 `pin_required`; 423 `pin_locked`; 403 `blocked`; 202 `verification_required` (`purpose` `first_setup` or `pin_reset`, `maskedEmail`) | `api.auth_start` | 1 |
| N02 | `POST /auth/pin` | `phoneNumber, deviceId, deviceToken?, deviceName?, pin` | 200 `authenticated`; 202 `verification_required` (`purpose` `new_device` with `maskedEmail`, or `first_setup`/`pin_reset`); 401 `authentication_failed` with `triesLeft`; 423 `pin_locked`; 403 `blocked`; 503 `service_unavailable` (new-device mail failed) | `api.auth_account_lookup`, `api.auth_pin` | 2 |
| N03 | `POST /auth/code` | `phoneNumber, deviceId, deviceName?, purpose, code, trustDevice` | `new_device`: 200 `authenticated` (`deviceToken` when trusted); `first_setup`/`pin_reset`: 200 `code_verified`; 401 `authentication_failed` (`triesLeft`, or null when the code is expired or gone); 202 `code_resent` (the third wrong try) | `api.auth_check_code` | 1 |
| N04 | `POST /auth/code/resend` | `phoneNumber, deviceId, deviceName?, purpose` | 202 `verification_required` always (`maskedEmail` null) | `api.auth_resend_code` | 1 |
| N05 | `POST /auth/pin/forgot` | `phoneNumber, deviceId, deviceName?` | 202 `verification_required` (`purpose` `pin_reset`, `maskedEmail` null) always | `api.auth_request_code` | 1 |
| N06 | `POST /auth/pin/new` | `phoneNumber, deviceId, deviceName?, purpose, code, pin, trustDevice` | 200 `authenticated` (`deviceToken` when trusted); 400 `invalid_pin` (`pinProblem`, `minimumPinLength` 4); 401 `authentication_failed` | `api.auth_complete_pin` (after `api.auth_account_lookup` for `pin_reset`) | 1 (`first_setup`), 2 (`pin_reset`) |
| N07 | `POST /auth/pin/change` (bearer) | `currentPin, newPin` | 200 `pin_changed`; 400 `invalid_pin`; 401 `authentication_failed` with `triesLeft`; 423 `pin_locked`; 401 empty from the bearer check | session, `api.auth_account_lookup_user`, `api.auth_change_pin` | 3 |
| N08 | `GET /auth/trusted-devices` (bearer) | | 200 `TrustedDevice[]` (plain JSON, not the envelope) | session, `api.auth_device_list` | 2 |
| N09 | `POST /auth/trusted-devices/{id}/remove` (bearer; `{id}` a UUID, the row id) | | 200 `device_revoked`; 404 empty | session, `api.auth_device_remove` | 2 |

- New statuses: `pin_required` (200), `pin_locked` (423), `blocked` (403), `code_resent`
  (202), `pin_changed` (200). The thirteen routes of 2.1 never answer them.
- `TrustedDevice`: `{id, name, trustedAt, lastUsedAt, thisDevice}`.
- Pre-validation, as 2.1 for the shared fields, plus: `deviceToken` at most 64 characters of
  `[A-Za-z0-9_-]`; `deviceName` as `docs/07-auth.md` 12.1; `purpose` one of `first_setup`,
  `new_device`, `pin_reset` (`new_device` only on N03 and N04); `trustDevice` a JSON boolean
  (default `true`); `currentPin` and `newPin` at most 8 characters. Anything else is
  `invalid_request`.
- Uniform answers (tested byte for byte, the `Seen` exclusions of 2.1): N01 for an unknown
  number and for an account with a PIN, unlocked, seen from a device that is not trusted;
  N02 for an unknown number and for a wrong PIN on an untrusted device with the same
  `triesLeft`, and `pin_locked` for both; N04 and N05 for every number; N03 for an unknown
  number and a real one with the same count.

#### 2.12.2 People sign-in actions (problem details)

| ID | Route | Permission | Success | operationId | Routine | Budget |
|---|---|---|---|---|---|---|
| S45 | `POST /setup/people/{id}/pin-reset` | `people.sign_in` | 200 `{id}` | `RequirePersonPinReset` | `api.people_pin_reset` | 2 |
| S46 | `POST /setup/people/{id}/trusted-devices/{deviceId}/remove` (`{deviceId}` the row id) | `people.sign_in` | 200 `{id}` | `RemovePersonDevice` | `api.people_device_remove` | 2 |

S11 (`POST /setup/people/{id}/sign-out`) is "Remove all" under `people.sign_in`.

#### 2.12.3 Target sets and main categories

| ID | Route | Permission | Success | operationId | Routine | Budget |
|---|---|---|---|---|---|---|
| S47 | `GET /setup/vehicles/{id}/targets` | `vehicles.view` | `TargetSet[]` newest first | `ListVehicleTargets` | `api.setup_target_set_list` | 2 |
| S48 | `POST /setup/vehicles/{id}/targets` | `vehicles.target`; body `{startsOn, days}` (`days` seven numbers, Monday first) | `{id}` (the set) | `SaveVehicleTargets` | `api.setup_target_set_save` | 2 |
| S49 | `POST /setup/vehicle-targets/{id}/remove` | `vehicles.target` | `{id}` | `RemoveVehicleTargets` | `api.setup_target_set_remove` | 2 |
| S50 | `GET /setup/expense-main-categories?page&pageSize` | any of `catalog.view`, `expenses.view`, `scheduled.view` | `Page<MainCategory>` plus `categoriesWithoutMain` | `ListExpenseMainCategories` | `api.setup_expense_main_category_list` | 2 |
| S51 | `POST /setup/expense-main-categories` | `catalog.add`; body `{name}` | `{id}` | `CreateExpenseMainCategory` | `api.setup_expense_main_category_create` | 2 |
| S52 | `PUT /setup/expense-main-categories/{id}` | `catalog.edit`; body `{name}` | `{id}` | `RenameExpenseMainCategory` | `api.setup_expense_main_category_rename` | 2 |

`TargetSet`: `{id, startsOn, days, weekTotal, inForce, canRemove}`. `MainCategory`: `{id,
name, categoryCount, itemCount}`.

#### 2.12.4 Changed rows of sections 2.1 to 2.9

The permission column of every row below replaces the one above (the 59 keys of `docs/15`
section 3); body changes are additive unless marked **changed**, and every one keeps the
property order of today with the new properties at the end.

| Row | Permission now | Body and behaviour |
|---|---|---|
| A01 to A13 | anonymous / bearer as today | envelope unchanged; behaviour per `docs/07-auth.md` 12.13; A01 and A02 also under `auth_pin`; A09's budget becomes 2 (the lookup that returns the hash the new PIN is compared with) |
| O01 to O04 | `organization.manage` (Owner only, `docs/15` 3.3) | O01 adds the section `revenue` `{lowDayThreshold, gapAmberPercent}`; O02 accepts `section` `revenue` |
| O05 | member | adds `idleUnlockSeconds`; `lockoutThreshold` is 5 |
| S01 | member | 59 items in 12 groups; each item adds `section` (null outside petty cash) |
| S02 | `people.view` | |
| S03 | any of `people.add`, `people.edit` | vehicle options add `fleetNumber` |
| S05 | `people.view` | `status` filter: `active`, `not_signed_in`, `pin_reset_due`, `locked`, `blocked` (legacy `waiting`, `none` accepted); `PersonDto` adds `status`, `lastSignedInAt`, `backLimit` `{mode, count, from}`, `canChange`, `modules` `[{name, held, total}]`, `everything`; `active` and `hasPin` stay |
| S06 | `people.view` | adds `signIn` `{status, lock, lastSignedInAt, email, devices: [{id, name, trustedAt, lastUsedAt}]}` |
| S07 | `people.add` | body adds `backLimit` (absent = `days` 7); `permissions` must be catalogue keys (**changed**: today's retired keys are `people_permission_unknown`) |
| S08 | `people.edit` | body adds `backLimit` (absent = unchanged); catalogue keys only |
| S09, S10 | `people.block` | |
| S11 | `people.sign_in` | logged in section `signIn` as "Trusted device removed, {name}" (**changed** wording, DN-B8-1); `unchanged` when nothing is left to remove |
| S12 | `companies.view` | |
| S13 | `companies.add` | |
| S14 to S16 | `companies.edit` | |
| S17 | any of `vehicles.view`, `reports.investment` | `VehicleDto` adds `fleetNumber`, `initialInvestment`, `dayTargets`, `nextTarget` `{startsOn, dayTargets, weeklyTarget}` (the first set starting after today, or null); `dayTargets` are the seven figures of the set in force today, also while the vehicle is away or has left (null when no set has started, and for a caller without `vehicles.view`); `weeklyTarget` is the total of the set in force today (0 while away or after leaving, as before); `targets` keeps its shape, one entry per set by start with `revision` its ordinal |
| S18 | `vehicles.add` | body adds `fleetNumber` (**required**), `dayTargets` (seven numbers, **required**), `initialInvestment` (null or 0 = empty); `weeklyTarget` is ignored (`DEC-15`) |
| S19 | `vehicles.edit` | body adds `fleetNumber` (**required**), `initialInvestment`; `weeklyTarget` is ignored: targets change only through S48 (DN-B9-10, `DEC-15`) |
| S20 | any of `vehicles.add`, `vehicles.edit` | |
| S21, S22 | `vehicles.edit` | |
| S23 | `vehicles.view` | `target` is the sum of the day targets over the window |
| S24 | any of `scheduled.view`, `savings.view` | items of a kind the caller cannot view are left out |
| S25 | any of `scheduled.add`, `scheduled.edit`, `savings.add`, `savings.edit` | options add `fleetNumber` |
| S26 | `scheduled.add` (cost) or `savings.add` (savings) | |
| S27 to S29 | the edit right of the item's kind (and of the new kind on a kind change) | change-log reason `Scheduled expense, {name}` / `Saving, {name}` (**changed** wording, DN-B17-3) |
| S30 | `audit.view` | `section` accepts `signIn` |
| S31 | any of `catalog.view`, `expenses.view`, `scheduled.view` | `ExpenseCategoryDto` adds `mainCategoryId`, `mainCategoryName`; `bucket` may be null |
| S32 | any of `catalog.view`, `expenses.view`, `expenses.capture`, `scheduled.view`, `scheduled.add`, `scheduled.edit`, `pettycash.spend` | options add `mainCategoryName` |
| S33 | `catalog.add` | body `{name, mainCategoryId}`; `bucket` accepted and ignored (**changed**: no longer required) |
| S34 | `catalog.edit` | body `{name, mainCategoryId}` (absent = unchanged, null = no main category); `bucket` ignored |
| S35, S36, S39, S40 | `catalog.stop` | |
| S37 | `catalog.add` | |
| S38 | `catalog.edit` | |
| S41 | `reports.investment` | |
| S42 to S44 | `vehicles.edit` | |
| R01 | `revenue.view` | query `q` (registration or fleet number); `RevenueWeekDto` adds `lowDayThreshold`, `gapAmberPercent`, `gap`, `gapBand`, `belowThresholdDays`, `missingDays`; vehicle rows add `fleetNumber`, `gap`, `gapBand`, `belowThresholdDays`; a cell's `expected` is the day target; a cell may carry `amount` and `reason` |
| R02 | any of `dash.net`, `dash.gaps` | cards per `docs/05-routines.md` 10.5 |
| R03 | any of `revenue.capture`, `revenue.correct` | body adds `capturedAt` (an instant, optional); an amount below the threshold needs `reason`; an amount at or above it takes none; the `note` on Other is optional; `revenue.correct` for every saved record (**changed**: today's saved record too) |
| P01 to P13 | the gates of section 2.11 (prompt 08), keys 12 to 31 of `docs/15` section 3.1 | |

#### 2.12.5 Message codes these rows add (planned)

Section 3 lists only what is built (`tests/unit/test_messages.py` compares it with
`http/messages.py` both ways). The build session that adds a code moves its row from this
table into the right block of section 3 in the same change, and applies the changes and
retirements listed here at the same time (D2's five rows moved on 2026-10-12; D3's eight moved the same day, with `target_start_required` added and `expense_bucket_invalid` retired, as no route chooses a bucket any more). Sentences taken from the prototype are marked
(p); the others are decided here (question 64 holds their wording for the owner). Dates
follow the rule of section 3 (`yyyy-MM-dd`); `{CUR} {threshold}` uses `tenancy.fmt_money`
(`KES 4,000`).

| Code | Status | Sentence | Session |
|---|---|---|---|

D4's five rows moved to section 3 on 2026-10-12, with `{CUR}` written `{currency}` (a
`DETAIL` key, the organization's currency), and D4 retired `revenue_no_earnings_permission`
(reasons are part of capture and change) and `revenue_other_needs_note` (the note on Other
is optional) from both.

### 2.13 Expenses, reports, exports, day capture and scheduled runs (prompt 08b)

Source: `docs/inventory/inventory-expenses-reports.md` (routes `E*`, `G*`, `D*`, `X*`, `S53` to `S56`, rules `CE-*`,
`SR-*`, `RP-*`, `RD-*`, `FP-*`); routines `docs/05-routines.md` section 11; decisions `DEC-30` onward in
`docs/15-design-v2-3.md` section 2. Methods, paths, tags and operation ids are .NET's; the permissions are the 59 rights
(`docs/15` section 3.1), so they differ from .NET's where the notes changed them. Every route answers through the setup
error model (section 1.6), is 2 statements, and lists its 400, 403, 404 (and 409 where it writes) in the OpenAPI
document. Bodies keep .NET's property order; what Python adds is appended at the end of its object.

#### 2.13.1 Central expenses (router `http/routers/expenses.py`, tag `Central expenses`)

| ID | Route | Permission | Success | operationId | Routine |
|---|---|---|---|---|---|
| E01 | `GET /setup/expenses/ledger?from&to&source&q&page=1&pageSize=100` | `expenses.view` | `ExpenseLedger` | `GetExpenseLedger` | `api.expenses_ledger_get` |
| E02 | `GET /setup/expenses/export?from&to&source&q&format` | `expenses.export` and `expenses.view` | file (2.13.5) | `ExportExpenseLedger` | `api.expenses_export_get` |
| E03 | `GET /setup/expenses/options?date` | any of `expenses.capture`, `expenses.correct` | `ExpenseOptions` | `GetExpenseOptions` | `api.expenses_options_get` |
| E04 | `POST /setup/expenses/entries` | `expenses.capture` | 200 `{ids, total}` | `RecordExpense` | `api.expenses_entry_create` |
| E05 | `PUT /setup/expenses/entries/{id}` | any of `expenses.capture`, `expenses.correct`, then CE-12 | 200 `{id, version}` | `ChangeExpense` | `api.expenses_entry_update` |
| E06 | `POST /setup/expenses/entries/{id}/remove` | any of the two, then CE-12 | 200 `{id, version}` | `RemoveExpense` | `api.expenses_entry_remove` |

- `ExpenseLedger`: `businessDate, from, to, permissions {canRecord, canCorrect}, figures {total, central, pettyCash,
  scheduled}, items, pageNumber, pageSize, total, amount`. A row: `id, source, date, vehicleId, registration,
  expenseItemId, itemName, categoryName, bucket, units, unitAmount, total, note, recordedByName, holderName, scheduleId,
  group, version, canEdit, canRemove` and, new, `mainCategoryName, fleetNumber`. `bucket` is the category's, 2 when it
  has none (B16 keeps the column for released clients). `canEdit`/`canRemove` are false for a row dated before the
  viewer's earliest writable date (B12).
- `ExpenseOptions`: `vehicles [{id, companyId, companyName, registration, active, fleetNumber}], items [{id, name,
  categoryId, categoryName, bucket, mainCategoryName}]`.
- E04 body `{id?, date, expenseItemId, units, unitAmount, note?, allocations: [{vehicleId, amount}]}`; E05 body `{date,
  vehicleId, expenseItemId, units, unitAmount, note?, version}`; E06 body `{version, reason}`. Money and units parse
  exactly (the shared money parser; units up to three decimals), unknown properties are ignored as everywhere.
- 409: `expense_version_conflict` (title `This expense has changed.`, `current` the ledger row or null) and
  `expense_saved_by_other` (the same title, no `current`). There is no EF race to translate: the row lock serialises
  writers, so .NET's `This expense was changed by another save.` answer has no counterpart (a two-connection
  test proves the stale writer gets `expense_version_conflict`).
- `{id}` is a `uuid` convertor (404 empty body otherwise, as every `/setup` route).

#### 2.13.2 Reports (router `http/routers/reports.py`, tag `Reports`)

| ID | Route | Permission | Success | operationId | Routine |
|---|---|---|---|---|---|
| G01 | `GET /setup/reports` | `reports.view` | `ReportsAccess` | `GetReportsAccess` | `api.report_catalog_get` |
| G02 | `GET /setup/reports/fleet/{report}?from&to&companyId&q&page=1&pageSize=50` | `reports.view`; `investment` also `reports.investment` | `ReportTable` | `GetFleetReport` | `api.report_get` |
| G03 | `GET /setup/reports/pettycash/{report}?from&to&holderId&q&page=1&pageSize=50` | `reports.view` and `pettycash.reports` | `ReportTable` | `GetPettyCashReport` | `api.report_get` |
| G04 | `GET /setup/reports/{group}/{report}/export?from&to&holderId&companyId&q&format` | `reports.export` and the report's gate | file | `ExportReport` | `api.report_export_get` |

- `ReportsAccess`: `businessDate, firstDayOfWeek, fleet, pettyCash, holders [{id, name, active}], canExport`.
  `pettyCash` adds `rejected` after `sentBack`.
- `ReportTable`: `group, report, title, from, to, businessDate, headline {label, value, kind}, figures, columns [{key,
  label, kind, sum}], rows, pageNumber, pageSize, total, totals`. A cell is a string, a JSON number or null; dates
  `yyyy-MM-dd`. The columns of each report are `docs/05` 11.4 (Net by vehicle and Money out by main category,
  `DEC-38`; Savings with saved, skipped and held runs, B18; Investment with the initial investment, `DEC-39`); clients
  render columns by `kind`, so new keys need no client change.
- `{report}` is free text checked by the routine (404 for an unknown one, as .NET); `{group}` on G04 is `fleet` or
  `pettycash`, anything else 404.

#### 2.13.3 Day capture and the revenue export (router `http/routers/revenue.py`, tag `Revenue`)

| ID | Route | Permission | Success | operationId | Routine |
|---|---|---|---|---|---|
| D01 | `GET /setup/revenue/day?date&companyId` | `revenue.view` | `RevenueDay` | `GetRevenueDay` | `api.revenue_day_get` |
| D02 | `PUT /setup/revenue/day/{date}` | any of `revenue.capture`, `revenue.correct`; each row as R03 | 200 `{rows: [{vehicleId, id, version}]}` | `SaveRevenueDay` | `api.revenue_day_save` |
| X02 | `GET /setup/revenue/export?weekStart&companyId&format` | `revenue.export` and `revenue.view` | file | `ExportRevenueWeek` | `api.revenue_export_get` |

- `RevenueDay`: `date, businessDate, vehicles [{id, companyId, registration, day, lastWeek, fleetNumber}], truncated`;
  `day` is R01's cell (D4's fields), `lastWeek` `{amount, reason}` or null.
- D02 body `{rows: [{vehicleId, amount, reason, note, version}]}`; each row runs R03's steps of `docs/05` 10.5 (the
  threshold, the rights, the back-dating limit as of the request), never .NET's older step list. A 400 names the
  vehicle (`KDA 103A: {sentence}`); a 409 is `revenue_day_conflict` with `current` and `vehicleId`; a 403 keeps its
  sentence. `{date}` that is not a date is 404, as R03.
- These routes must be declared before R03's `/{vehicleId}/{date}` (FastAPI matches in order; `day` and `export` are
  not uuids, so the convertor already keeps them apart, and the order makes it explicit).

#### 2.13.4 Petty-cash export and the scheduled-item routes

| ID | Route | Permission | Success | operationId | Routine |
|---|---|---|---|---|---|
| X03 | `GET /setup/pettycash/export?from&to&holderId&view&status&q&format` (tag `Petty cash`) | `pettycash.export` and the petty-cash read gate | file | `ExportPettyCash` | `api.pettycash_export_get` |
| S53 | `GET /setup/recurring/summary` (tag `Setup`) | any of `scheduled.view`, `savings.view` | `RecurringSummary` | `GetSetupRecurringSummary` | `api.setup_recurring_summary` |
| S54 | `GET /setup/recurring/{id}/runs` | any of `scheduled.view`, `savings.view` (the item's kind) | `RecurringRuns` | `GetSetupRecurringRuns` | `api.setup_recurring_runs` |
| S55 | `POST /setup/recurring/{id}/pause` | `scheduled.pause` or `savings.pause` by kind | `{id}` | `PauseSetupRecurring` | `api.setup_recurring_pause` |
| S56 | `POST /setup/recurring/{id}/resume` | as S55 | `{id}` | `ResumeSetupRecurring` | `api.setup_recurring_resume` |

- `RecurringSummary`: `from, to, costsDue, saved, savingsBalance` and, new, `runningCosts, pausedCosts, runningSavings,
  pausedSavings`; a figure of a kind the caller cannot view is null.
- `RecurringRuns`: `id, name, kind, start, total, runCount, runs [{date, amount, shares [{vehicleId, registration,
  amount, state, revenue}]}]` (`state` and `revenue` new).
- S24's `RecurringDto` adds, after D3's fields, `pausedFrom, lastRun, lastRunVehicles, balance` (.NET's order) and then
  `lastRunStates {saved, skipped, held}, condition {min, days}, opening {date, total}, nextRun`.
- S26 and S27 bodies add `condition` (`{min, days}` or null) and `opening` (`{date, amounts: [{vehicleId, amount}]}`
  or null; absent on S27 keeps it). For a saving `start` is ignored and `end` must be null (B18, `DEC-33`).
- S23 lists central postings with `source` `central` (FP-6); its figures come from `setup.fleet_postings`.
- `summary` is declared before `/{id}` routes; `{id}` is a `uuid` convertor.
- P05 (petty-cash create) body adds `allocations` (`[{vehicleId, amount}]`, 2 to 50, an expense only); P02 rows add
  `group {id, size, total, units, unitAmount}` (`docs/05` 11.6).
- P03's vehicles add `fleetNumber` after `active`, as S03 and S25 do (DN-B10-3; the gap was found by the verify of 07b D3 on
  2026-10-12 and is taken by the 08b build).

#### 2.13.5 Files

- Content types: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` and `application/pdf`.
- `Content-Disposition: attachment; filename="{name}"; filename*=UTF-8''{percent-encoded name}` (ASP.NET Core's form
  for `Results.File` with a name), `{name}` = `{title}[ {period}].{xlsx|pdf}` with characters outside printable ASCII,
  `"` and `\` replaced by `_` in the quoted form; one helper in `http/` builds it.
- The body is the whole file; no streaming (the row cap bounds it, `docs/12-security.md` 2.8). `Cache-Control:
  no-store` and `X-Content-Type-Options: nosniff` come from the middleware as on every answer; gzip does not apply
  (the files are not JSON).
- What the file holds: RP-16 and RP-17's layout, built by the library of `docs/02-stack.md` ADR-16 from
  `reports.document`; every text cell a string cell, formula injection neutralised (`docs/12` 2.8).

#### 2.13.6 Message codes these rows add (planned)

Moved into section 3 by the build session with the routine that raises each (as 2.12.5 explains). (p) marks a sentence
from the v2.3 prototype; the others are .NET's, except the four marked (new), decided here.

| Code | Status | Sentence |
|---|---|---|
| `expense_vehicles_invalid` | 400 | `Choose 1-50 distinct vehicles.` |
| `expense_allocation_amount` | 400 | `Each vehicle's amount must be other than zero, with at most two decimals.` |
| `expense_allocation_sign` | 400 | `Each vehicle's amount must have the same sign as the total.` |
| `expense_allocation_sum` | 400 | `The vehicle amounts must add up to the total.` |
| `expense_date_future` | 400 | `An expense cannot be recorded for a future date.` |
| `expense_date_too_old` | 400 | `Choose a date in the last ten years.` |
| `expense_vehicle_not_yours` | 400 | `Choose one of your vehicles.` |
| `expense_vehicle_inactive` | 400 | `{registration} was not in the fleet on that day.` |
| `expense_item_not_in_use` | 400 | `Choose an item that is in use.` |
| `expense_version_required` | 400 | `Send the version of the expense you opened.` |
| `expense_purchase_has_vehicle` | 400 | `This purchase already has a row for {registration}.` |
| `expense_change_other` | 403 | `Changing someone else's expense needs the permission "Edit an expense".` |
| `expense_change_earlier_day` | 403 | `Changing an expense from an earlier day needs the permission "Edit an expense".` |
| `expense_change_date` | 403 | `Changing the date of an expense needs the permission "Edit an expense".` |
| `expense_version_conflict` | 409 | title `This expense has changed.`, `This expense was changed after you opened it. Check it and save again.`, `current` |
| `expense_saved_by_other` | 409 | title `This expense has changed.`, `This expense was already saved by someone else. Reload and try again.` |
| `expense_period_required` | 400 | `Choose the first and the last date.` |
| `expense_period_order` | 400 | `The first date cannot be after the last date.` |
| `expense_period_length` | 400 | `Choose a period of at most 367 days.` |
| `expense_source_invalid` | 400 | `Choose central, petty cash or scheduled.` |
| `expense_search_length` | 400 | `Search for 200 characters or fewer.` |
| `report_period_both` | 400 | `Choose the first and last day.` |
| `report_period_order` | 400 | `The first date cannot be after the last date.` |
| `report_period_length` | 400 | `Choose at most 367 days.` |
| `report_period_future` | 400 | `Choose a period that starts on or before today.` |
| `report_search_length` | 400 | `Search for 200 characters or fewer.` |
| `report_investment_permission` | 403 | `The investment report needs the permission "See the investment report".` |
| `report_pettycash_permission` | 403 | `Petty cash reports need the permission "View petty cash reports".` |
| `export_format_invalid` | 400 | `Choose Excel (xlsx) or PDF.` |
| `export_too_many_rows` | 400 | `There are {count} rows to export, more than 10,000. Choose a shorter period or search.` (`count` with thousands separators) |
| `pettycash_export_view_invalid` | 400 | `Choose the expenses or the cash received.` |
| `revenue_day_date_range` | 400 | `Choose a day from the last ten years up to today.` |
| `revenue_day_rows_required` | 400 | `Enter the revenue or a no-earnings reason for at least one vehicle.` |
| `revenue_day_rows_limit` | 400 | `Save at most 500 vehicles at once.` |
| `revenue_day_vehicle_repeated` | 400 | `Each vehicle can be in the day only once.` |
| `revenue_day_conflict` | 409 | title `This day already has a different record.`, `{registration} was changed after you opened the day. Check its current record and save again.`, `current`, `vehicleId` |
| `recurring_condition_on_cost` | 400 | `Only a saving has a revenue rule.` (new) |
| `recurring_condition_min` | 400 | `Enter the revenue target.` (p) |
| `recurring_condition_days` | 400 | `Measure the revenue over 1, 7 or 30 days.` (new) |
| `recurring_opening_on_cost` | 400 | `Only a saving has an opening balance.` (new) |
| `recurring_opening_future` | 400 | `The opening balance date is after today.` (p) |
| `recurring_opening_vehicle` | 400 | `An opening balance is for a vehicle of the saving.` (new) |
| `recurring_savings_end` | 400 | `A saving has no end date.` (new) |

Retired with the saving model: `recurring_savings_frequency` (savings run daily, weekly, monthly or yearly). Pause and
resume reuse `recurring_already_stopped`. The rule of the day save's 400s (`{registration}: ` before the sentence when
`DETAIL` carries `vehicle_registration`) is one function in `http/errors.py` with its own unit test.

#### 2.13.7 Client facts

- The web downloads files through its proxy and names them itself (`{label} {period}.{format}`), reading only the
  content type; on a refusal it shows `detail` (`apps/web/components/reports/exportReport.ts:28-49`). The
  `Content-Disposition` name is for other callers.
- The ledger and reports are paged on the server; the web pages until `items.length >= total` on the ledger and asks for
  one page of a report at a time with `q`.
- The web saves a day through D02 and reads the 409's `vehicleId` to mark the row (`apps/web/components/revenue/useFleetDay.ts`).
- The released web sends a scheduled item's `start`, `end` and shares as today; for a saving `start` is ignored and an
  `end` that is new or differs from the stored one is refused (`recurring_savings_end`), which today's web never sends for a saving with "No end date"
  ticked (question 74 records the other changes the saving pop-up needs).
- Mobile v2.11 calls none of these routes (`grep` over `apps/mobile/src`); its revenue queue keeps R03 and its bodies.

## 3. Message catalogue

Routines refuse with SQLSTATE `XC4xx` and `MESSAGE` = a stable code; parameters travel in
`DETAIL` as a JSON object. `http/messages.py` maps each code to the exact sentence below
(the single place for these strings; the pure functions that format them are tested with
the examples in the inventory). `tests/db/test_message_codes.py` proves that every code
raised in `db/routines/**/*.sql` has an entry here, and `tests/unit/test_messages.py`
proves every entry formats. Codes are `<area>_<summary>`; statuses follow section 1.6.

Cross-cutting:

| Code | Status | Sentence |
|---|---|---|
| `not_member`, `permission_missing` (no detail) | 403 | title only |
| `not_found` | 404 | title only |
| `version_conflict` | 409 | `Settings changed. Reload before saving.` |
| `unique_conflict` | 409 | `A conflicting record exists. Reload before saving.` |
| `page_out_of_range` | 400 | `Page must be 1–100000 and page size 1–100.` |
| `reason_length` | 400 | `A reason of 1–500 characters is required.` |
| `money_invalid` | 400 | `Amount must be positive with at most two decimal places.` |

Raised to the service or the CLI only, never rendered as a sentence:

| Code | Where | Effect |
|---|---|---|
| `session_invalid` (`XC401`) | `api.auth_resolve_session`, every bearer route | 401 with an empty body and `WWW-Authenticate: Bearer` |
| `rate_limit_invalid` | `api.rate_limit_hit` with bounds the service itself chose | a configuration bug: 500 |
| `organization_not_single` (`XC409`) | `api.ops_provision_user` and `api.ops_seed_demo` when the database holds more than one organization | the CLI prints `refused: organization_not_single`, exit 1 |
| `seed_development_only` (`XC403`) | `api.ops_seed_demo` outside `development` (the CLI refuses before connecting) | CLI `seed-demo` prints `refused: seed_development_only`, exit 1 |
| `seed_exists` (`XC409`) | `api.ops_seed_demo` when the one organization is not the demo | CLI `seed-demo` prints `refused: seed_exists`, exit 1 |

The CLI user commands print `refused: <code>` for every refusal, including the `people_*`
codes `api.ops_provision_user` shares with the people routines.

People and access (`inv 2.3`):

| Code | Status | Sentence |
|---|---|---|
| `people_names_required` | 400 | `First and last name are required.` |
| `people_email_invalid` | 400 | `A valid email is required.` |
| `people_phone_invalid` | 400 | `A valid mobile number is required.` |
| `people_scope_mode` | 400 | `Choose a data scope.` |
| `people_scope_empty` | 400 | `Choose at least one item in the data scope.` |
| `people_scope_duplicate` | 400 | `Data scope items must be distinct.` |
| `people_filter_status_invalid` | 400 | `Status must be active, not_signed_in, pin_reset_due, locked or blocked.` (the legacy `waiting` and `none` are still accepted, not named) |
| `people_permissions_invalid` | 400 | `Permissions and approval limit are invalid.` |
| `people_role_unknown` | 400 | `Unknown role.` |
| `people_version_required` | 400 | `Reload this person before saving.` |
| `people_all_companies_needs_all` | 403 | `Only someone who can see every company can give access to every company.` |
| `people_companies_unknown` | 400 | `Choose companies in your organization.` |
| `people_vehicles_unknown` | 400 | `Choose vehicles in your organization.` |
| `people_companies_outside_scope` | 403 | `You can only give access to companies in your own data scope.` |
| `people_vehicles_outside_scope` | 403 | `You can only give access to vehicles in your own data scope.` |
| `people_hidden_scope_kind` | 403 | `This person's data scope includes companies or vehicles outside your own, so you cannot change which kind of scope they have. Their companies and vehicles outside your view are kept as they are.` |
| `people_self_edit` | 400 | `You cannot change your own access here.` |
| `people_owner_grant` | 403 | `Only an Owner can give the Owner role.` |
| `people_owner_edit` | 403 | `Only an Owner can change, remove or sign out an Owner.` |
| `people_permission_unknown` | 400 | `Unknown permission.` |
| `people_role_not_held` | 403 | `You can only grant roles whose permissions you hold.` |
| `people_access_manage_needed` | 403 | `Changing single permissions or an approval limit needs "Edit a person and their access".` (the right that replaced `access.manage`; question 64 holds the wording) |
| `people_permission_not_held` | 403 | `You can only grant permissions you hold.` |
| `people_sign_in_scope` | 403 | `Only an Owner, or someone who can see this person's full data scope, can change their email or mobile number.` |
| `people_sign_in_holdings` | 403 | `Only an Owner, or someone who holds everything this person holds, can change their email or mobile number.` |
| `people_contact_taken` | 400 | `That mobile number or email already belongs to someone.` |
| `people_self_deactivate` | 400 | `You cannot deactivate your own access.` (activate uses the same text) |
| `people_self_sign_out` | 400 | `Use sign out for your own session.` |
| `people_self_sign_in` | 400 | `Use the profile menu for your own PIN and devices.` |
| `people_back_limit_invalid` | 400 | `Choose how far back this person can change records: none, 0 to 3650 days or 0 to 120 months.` |
| `people_back_limit_date_future` | 400 | `The date before which this person cannot change records cannot be after today.` |
| `people_back_limit_not_held` | 403 | `You cannot let someone change records further back than you can.` (a non-Owner's own limit bounds the limits they give) |
| `record_too_old` | 400 | `You can only add or change records dated {earliest} or later.` (`earliest` as `yyyy-MM-dd`; raised by the writes of `docs/05-routines.md` 10.2) |

Companies and vehicles (`inv 2.4`, `inv 2.5`; parameters in braces):

| Code | Status | Sentence |
|---|---|---|
| `company_name_length` | 400 | `Name must contain 1-160 characters.` |
| `company_name_taken` | 400 | `Another company already has this name.` |
| `company_archived_rename` | 400 | `Archived companies cannot be renamed. Restore it first.` |
| `company_has_vehicles` | 400 | `Retire every vehicle in this company before archiving it.` |
| `company_already_archived` | 400 | `The company is already archived.` |
| `vehicle_registration_format` | 400 | `Use the registration format KDA 482M.` |
| `vehicle_joined_future` | 400 | `A vehicle cannot join after the business date.` |
| `vehicle_company_inactive` | 400 | `Choose an active PSV company.` |
| `vehicle_retired_edit` | 400 | `Retired vehicles must be restored before they can be edited.` |
| `vehicle_registration_change` | 400 | `Registration cannot change after a vehicle is added.` |
| `vehicle_registration_taken` | 400 | `This registration already exists.` |
| `vehicle_fleet_required` | 400 | `Enter the fleet number.` (the prototype's) |
| `vehicle_fleet_length` | 400 | `A fleet number has at most 20 characters.` |
| `vehicle_fleet_taken` | 400 | `Fleet number {fleet} is already used in this PSV company.` (the prototype names the other vehicle; this does not, so a scoped person learns no registration they cannot see) |
| `target_start_required` | 400 | `Enter the start date.` |
| `target_days_required` | 400 | `Enter the target for every day.` (the prototype's) |
| `target_start_past` | 400 | `A target cannot start before today.` (the prototype's) |
| `target_set_unchanged` | 400 | `This is the target already set for {date}.` (the prototype's) |
| `target_set_started` | 400 | `A target that has started cannot be changed or removed. Add a new one from today.` |
| `vehicle_join_after_revenue` | 400 | `{registration} has revenue recorded on {date}. A vehicle cannot join the fleet after a day it has a record for.` |
| `vehicle_leave_before_revenue` | 400 | `{registration} has revenue recorded on {date}. A vehicle cannot leave the fleet on or before a day it has a record for.` |
| `vehicle_leave_date_range` | 400 | `A vehicle's leave date must be from its join date through the business date.` |
| `vehicle_leave_before_return` | 400 | `A vehicle's leave date must be on or after the day it last returned to the fleet.` |
| `vehicle_already_retired` | 400 | `The vehicle is already retired.` |
| `vehicle_company_archived_restore` | 400 | `Restore the vehicle's archived company first.` |
| `vehicle_return_date_range` | 400 | `A vehicle's return date must be from the day it left through the business date.` |
| `report_period_invalid` | 400 | `Period must be week or month.` |
| `report_range_required` | 400 | `Choose a period, or a from and through date.` |
| `report_range_invalid` | 400 | `Report range must be at most 367 days and cannot include the future.` |

Scheduled items (`inv 2.6`):

| Code | Status | Sentence |
|---|---|---|
| `recurring_savings_item` | 400 | `Savings must not have an expense item.` |
| `recurring_item_not_in_use` | 400 | `Choose an expense item that is in use.` |
| `recurring_schedule_shape` | 400 | `Choose a weekday (0–6), a month day (1–28 / last), or for yearly a month (1–12) and a day.` |
| `recurring_name_length` | 400 | `Name must contain 1-160 characters.` |
| `recurring_kind_invalid` | 400 | `Costs need an expense item; savings must not have one.` |
| `recurring_note_length` | 400 | `A note can have at most 200 characters.` |
| `recurring_filter_kind_invalid` | 400 | `Kind must be cost or savings.` |
| `recurring_filter_status_invalid` | 400 | `Status must be running or stopped.` |
| `recurring_end_before_start` | 400 | `End date must be on or after start date.` |
| `recurring_allocations_count` | 400 | `Choose 1-500 distinct vehicles.` |
| `recurring_allocation_sum` | 400 | `Vehicle shares must equal the total exactly.` |
| `recurring_daily_retired` | 400 | `Daily schedules are no longer offered. Choose weekly, monthly or yearly.` |
| `recurring_savings_frequency` | 400 | `Savings are set aside weekly or monthly.` |
| `recurring_cost_needs_item` | 400 | `Choose the expense item this cost is for.` |
| `recurring_start_required` | 400 | `Start date is required.` |
| `recurring_start_too_early` | 400 | `A schedule can start no earlier than the first of the current month.` |
| `recurring_share_inactive` | 400 | `New recurring shares must use active vehicles and companies.` |
| `recurring_stopped_edit` | 400 | `Stopped items cannot be edited.` |
| `recurring_running_start_change` | 400 | `An already running item's start date cannot change.` |
| `recurring_stop_confirm` | 400 | `Confirm stopping this item. Past postings are retained; no posting occurs from today.` |
| `recurring_stop_later_pending` | 400 | `This item is already due to stop on a later date. Cancel that stop first.` |
| `recurring_already_stopped` | 400 | `The item is already stopped.` |
| `recurring_stop_in_effect` | 400 | `This item has already stopped. Add a new scheduled item instead.` |

Change log, expense catalog, investment (`inv 2.7` to `inv 2.9`):

| Code | Status | Sentence |
|---|---|---|
| `history_dates_order` | 400 | `The first date cannot be after the last date.` |
| `history_text_length` | 400 | `Search for 200 characters or fewer.` |
| `history_before_invalid` | 400 | `Before must be a change log version.` |
| `expense_name_length` | 400 | `Name must contain 1-100 characters.` |
| `expense_category_taken` | 400 | `That category already exists.` |
| `expense_main_taken` | 400 | `That main category already exists.` |
| `expense_already_stopped` | 400 | `It is already turned off. Turn it on first to cancel that.` |
| `expense_item_taken` | 400 | `That item already exists in this category.` |
| `investment_date_invalid` | 400 | `An investment date is required and cannot be after the business date.` |
| `investment_description_length` | 400 | `Say what it was, in 1-160 characters.` |

Revenue (`inv 2.10`):

| Code | Status | Sentence |
|---|---|---|
| `revenue_reason_invalid` | 400 | `Choose a valid no-earnings reason.` |
| `revenue_amount_with_reason` | 400 | `A reason is kept only for revenue below {currency} {threshold}.` (`DETAIL` `currency`: the organization's currency; `threshold`: the low-day threshold as `tenancy.fmt_money` writes it, `4,000`) |
| `revenue_entry_required` | 400 | `Enter revenue or choose a no-earnings reason.` |
| `revenue_low_needs_reason` | 400 | `Choose the reason. Revenue is below {currency} {threshold}.` (`DETAIL` as `revenue_amount_with_reason`) |
| `revenue_note_length` | 400 | `The no-earnings note must be at most 80 characters.` |
| `revenue_note_without_other` | 400 | `Only Other may have a no-earnings note.` |
| `revenue_future_date` | 400 | `Revenue cannot be recorded for a future date.` |
| `revenue_vehicle_away` | 400 | `The vehicle was away from the fleet on this day, so it is not a day revenue is recorded for.` |
| `revenue_vehicle_inactive` | 400 | `Revenue can only be recorded while the vehicle is active.` |
| `revenue_capture_permission` | 403 | `Recording a day that has no record yet needs the permission "Capture revenue".` |
| `revenue_correct_permission` | 403 | `Changing revenue already saved needs the permission "Change revenue already saved".` |
| `revenue_version_conflict` | 409 | title `This day already has a different record.`, detail `This day was changed after you opened it. Check the current record and save again.`, `current` from `DETAIL` |
| `revenue_concurrent_save` | 409 | title `This day was changed by another save.`, detail `Reload the current record and try again.` |
| `revenue_week_range` | 400 | `Choose a week from the last ten years through the current week.` |
| `revenue_search_length` | 400 | `Search for 40 characters or fewer.` |
| `revenue_settings_invalid` | 400 | `The low-day threshold must be 0 or more and the amber band 0 to 100 per cent.` |
| `dashboard_period_invalid` | 400 | `Period must be today, week or month.` |

Organization, logo, preferences (`inv 2.11`):

| Code | Status | Sentence |
|---|---|---|
| `organization_name_slug` | 400 plain `{detail}` | `Enter an organization name and a lowercase slug using letters, numbers, and hyphens.` |
| `organization_slug_taken` | 409 plain `{detail}` | `This organization slug is already in use.` |
| `settings_not_object` | 400 | `Send the section's settings as an object.` |
| `settings_wrong_type` | 400 | `A setting has the wrong type of value.` |
| `settings_business_date_future_zone` | 400 | `The held business date would be in the future in that time zone. Change the business date first.` |
| `business_date_invalid` | 400 | `Business date must be a valid calendar date or null.` |
| `business_date_future` | 400 | `The business date cannot be in the future.` |
| `locale_invalid` | 400 | `Use BCP 47 locale.` |
| `time_zone_invalid` | 400 | `'{value}' is an unknown or invalid time zone identifier. (Parameter 'value')` |
| `format_settings_invalid` | 400 | `Invalid format settings` |
| `brand_names_required` | 400 | `Brand names and logo alt text are required.` |
| `brand_colour_format` | 400 | `Use a six-digit hex colour` |
| `brand_contrast` | 400 | `Brand colors must meet WCAG AA (4.5:1) against the fixed surfaces` |
| `brand_url_https` | 400 | `Brand URLs must use HTTPS.` |
| `brand_domain_invalid` | 400 | `Invalid domain.` |
| `brand_support_email_invalid` | 400 | `Invalid support email.` |
| `security_policy_pin_sign_in` | 400 | `PIN sign-in cannot be disabled.` |
| `security_policy_invalid` | 400 | `Invalid security policy.` |
| `logo_too_large` | 400 | `The logo must be at most 256 KB.` |
| `logo_type` | 400 | `Upload a PNG, JPEG or WebP image.` |
| `logo_unreadable` | 400 | `The image could not be read.` |
| `logo_signature` | 400 | `The file is not the image type it claims to be.` |
| `preferences_accessibility` | 400 | `Invalid accessibility preferences` |
| `preferences_locale_not_allowed` | 400 | `Your organization does not allow a personal locale.` |
| `preferences_time_zone_not_allowed` | 400 | `Your organization does not allow a personal time zone.` |
| `preferences_hour12_not_allowed` | 400 | `Your organization does not allow a personal clock format.` |
| `preferences_theme_not_allowed` | 400 | `Your organization does not allow a personal theme.` |

Petty cash (`inventory-petty-cash.md` sections 2.3, 2.4, 4.3; `docs/15-design-v2-3.md` B19):

| Code | Status | Sentence |
|---|---|---|
| `pettycash_kind_invalid` | 400 | `Choose an expense, a credit note or cash.` (line check 1 and the `kind` filter) |
| `pettycash_line_date_required` | 400 | `Enter the date.` |
| `pettycash_line_amount_zero` | 400 | `Enter an amount other than zero.` |
| `pettycash_line_amount_decimals` | 400 | `Enter the amount with at most two decimals.` |
| `pettycash_line_units` | 400 | `Units must be above zero, with at most three decimals.` |
| `pettycash_line_units_only_expense` | 400 | `Only an expense has units.` |
| `pettycash_line_total_zero` | 400 | `The total rounds to zero. Check the units and the amount.` |
| `pettycash_line_total_large` | 400 | `The total is too large.` |
| `pettycash_line_note_length` | 400 | `The note must be at most 80 characters.` |
| `pettycash_line_vehicle_required` | 400 | `Choose the vehicle.` |
| `pettycash_line_item_required` | 400 | `Choose what it was for.` |
| `pettycash_line_expense_payee` | 400 | `Only a credit note has a payee.` |
| `pettycash_line_credit_vehicle` | 400 | `A credit note is not recorded against a vehicle.` |
| `pettycash_line_payee_length` | 400 | `The payee must be at most 80 characters.` |
| `pettycash_line_cash_shape` | 400 | `Cash given has only an amount, a date and a note.` |
| `pettycash_spend_permission` | 403 | `Recording spending needs the permission "Add an expense".` |
| `pettycash_own_float_only` | 400 | `Spending is recorded on your own float.` |
| `pettycash_credit_permission` | 403 | `Recording a credit note needs the permission "Record a credit note".` |
| `pettycash_cash_permission` | 403 | `Giving cash to a float needs the permission "Issue cash".` |
| `pettycash_holder_required` | 400 | `Choose who the cash goes to.` |
| `pettycash_holder_not_holder` | 400 | `Choose someone who keeps a petty cash float.` |
| `pettycash_future_date` | 400 | `Petty cash cannot be recorded for a future date.` |
| `pettycash_too_old` | 400 | `Choose a date in the last ten years.` |
| `pettycash_range_both` | 400 | `Choose the first and last day.` |
| `pettycash_range_length` | 400 | `Choose at most 367 days.` |
| `pettycash_range_start` | 400 | `Choose a period that starts on or before today.` |
| `pettycash_vehicle_scope` | 400 | `Choose one of your vehicles.` |
| `pettycash_vehicle_inactive` | 400 | `The vehicle was not in the fleet on that day.` |
| `pettycash_item_inactive` | 400 | `Choose an item that is in use.` |
| `pettycash_below_zero` | 400 | `This takes the float below zero, which needs the permission "Issue cash to a float below zero".` plus `balanceAfter` |
| `pettycash_change_cash` | 400 | `Cash given and credit notes cannot be changed. Delete the entry and record it again.` |
| `pettycash_change_decided` | 400 | `Reopen this entry before changing it.` |
| `pettycash_change_own_permission` | 403 | `Changing your own expenses needs the permission "Edit own expense".` |
| `pettycash_change_other_permission` | 403 | `Changing someone else's expense needs the permission "Edit any expense".` |
| `pettycash_delete_cash_permission` | 403 | `Deleting cash given or a credit note needs the permission "Delete a cash entry".` |
| `pettycash_delete_rejected` | 400 | `Reopen a rejected expense before deleting it.` |
| `pettycash_delete_approved_permission` | 403 | `Deleting an approved expense needs the permission "Delete after approval".` |
| `pettycash_delete_own_permission` | 403 | `Deleting your own expenses needs the permission "Delete own expense".` |
| `pettycash_delete_other_permission` | 403 | `Deleting someone else's expense needs the permission "Delete any expense".` |
| `pettycash_cash_not_reviewed` | 400 | `Cash given is not approved.` |
| `pettycash_credit_not_reviewed` | 400 | `A credit note is not approved.` |
| `pettycash_own_float_review` | 403 | `You cannot approve, send back or reject entries on your own float.` |
| `pettycash_own_entry_review` | 403 | `You cannot approve, send back or reject an entry you recorded.` |
| `pettycash_above_limit` | 403 | `This entry is above your approval limit.` |
| `pettycash_not_waiting` | 400 | `Only an entry waiting for approval can be approved, sent back or rejected.` |
| `pettycash_sent_back` | 400 | `This entry was sent back. It can be approved once it is saved again.` |
| `pettycash_already_sent_back` | 400 | `This entry was already sent back.` |
| `pettycash_not_decided` | 400 | `Only an approved or rejected entry can be reopened.` |
| `pettycash_kind_change` | 400 | `An entry cannot change between expense, credit note and cash. Remove it and record it again.` |
| `pettycash_holder_change` | 400 | `An entry cannot move to another float. Remove it and record it again.` |
| `pettycash_comment_required` | 400 | `Say what should be fixed.` |
| `pettycash_comment_length` | 400 | `The comment must be at most 200 characters.` |
| `pettycash_reject_reason_required` | 400 | `Say why the entry is rejected.` |
| `pettycash_reopen_reason_required` | 400 | `Say why the entry is reopened.` |
| `pettycash_decision_reason_length` | 400 | `The reason must be at most 200 characters.` |
| `pettycash_approve_none` | 400 | `Choose the entries to approve.` |
| `pettycash_approve_many` | 400 | `Approve at most 100 entries at a time.` |
| `pettycash_period_invalid` | 400 | `Choose a day or a week.` |
| `pettycash_status_invalid` | 400 | `Status must be waiting, approved, sentBack or rejected.` |
| `pettycash_entry_changed` | 409 | title `This entry has changed.`, detail `This entry was changed after you opened it. Check it and save again.`, `current` from `DETAIL` |
| `pettycash_already_saved` | 409 | title `This entry has changed.`, detail `This entry was already saved by someone else. Reload and try again.`, `current` `null` |
| `pettycash_concurrent_save` | 409 | title `This entry was changed by another save.`, detail `Reload and try again.` |

Petty cash reuses `page_out_of_range`, `history_dates_order`, `history_text_length` and
`reason_length` (same sentences).

Dates in sentences are `yyyy-MM-dd` except the change-log reasons, which use `d MMM yyyy`
(`docs/05-routines.md` section 6).

## 4. Client facts that constrain changes

- The web proxy requires every `/auth/**` answer below 500 to be JSON with a string `status`,
  otherwise it answers 503 to the browser; tokens never reach the browser; `unlock` is not
  reachable from the web (`inv 4.2`).
- The web data layer shows `detail`, then `title`, then a fixed 403 sentence; it retries
  reads only on 503, 0 and network failure; it pages until `items.length >= total`
  (`inv 4.3`).
- The mobile queue depends on: 200 `{id, version}` (also for an identical replay, at any
  time); 409 with `current` or a re-read of the day; `detail`/`title` on 400, 403, 404
  and other 4xx; 5xx and timeouts as retryable (`inv 3.6`, `inv 4.4`). Since .NET commit
  9276c51 it no longer reads `earliestMissing` from a 400: a stored `blocked` entry reads
  as pending. Its secure-store JSON keys the queue by the
  API `userId`, so user ids must survive the data migration.
- Mobile reads `lockoutThreshold` and `lockoutMinutes` from `GET /setup/appearance` and only
  accepts them inside 3..10 and 1..60.
- `Phase1ContractTests` (`tests/api`) pin every property name, kind and nullability the
  clients read; the Python contract tests reproduce them (`docs/09-testing.md` section 4).

- The design notes v2.29 to v2.33 (section 2.12) are built ahead of every client: the web
  adopts them when it moves to the Python API (question 55), mobile stays at v2.11
  (question 54). What a v2.11 phone and today's web get once 07b is built is
  `docs/15-design-v2-3.md` section 4.
- The number-first flow on a client: N01; then `pin_required` -> the PIN step (the number
  only, never a name, on a device without a token); `verification_required` -> the code step
  (title from `purpose`: `Confirm this device`, `First sign in`, `Reset PIN`; the masked
  email when `maskedEmail` is not null, which it is after "Forgot PIN" and "Send a new code",
  so that an unknown number cannot be told apart there); after `code_verified` the new-PIN
  step (N06) with "Trust this device" ticked; `blocked` -> `This number is blocked. Speak to
  the office.` A trusted device keeps the person's number, name and `deviceToken` in its
  secure store, starts at the PIN step and sends the token with N01 and N02; it forgets
  the token when a right PIN is answered with `verification_required` and `purpose`
  `new_device` (the server no longer trusts the device).
- Wording the client shows for the step envelope (the prototype's): `pin_locked` ->
  `Too many wrong PINs. Reset your PIN to sign in.` with "Reset PIN" (N05);
  `authentication_failed` with `triesLeft` n on N02 -> `Wrong PIN. {n} tries left.` (`try`
  for 1), on N03 -> `Wrong code. {n} tries left.`, on N07 -> `The current PIN is not
  right.`; `code_resent` -> `Wrong code. A new code has been sent.`; `invalid_pin` with
  `pinProblem` `length` -> `The PIN is 4 digits.`, `weak` -> `Choose a PIN that is harder
  to guess.`, `unchanged` -> `Choose a PIN different from the old one.` (N07: `... the
  current one.`). Checked in the client before sending: `Enter your 10 digit mobile
  number.`, `Enter your 4 digit PIN.`, `Enter the 6 digit code.`, `The two PINs do not
  match.`.
- The PIN field submits on its fourth digit. A PIN of five to eight digits set before the
  notes still verifies (v2.11 phones keep sending it), but the new screens cannot take it:
  its holder uses "Forgot PIN" once (`docs/07-auth.md` 12.4).
- The client asks for the PIN again after `idleUnlockSeconds` (`GET /setup/appearance`)
  without activity and keeps unsent work.
- Vehicle drop-downs show `{registration} · {fleetNumber}`, or the registration alone while
  `fleetNumber` is null; the week grid colours the gap by `gapBand` and shows the reason
  buttons only while the amount is below `lowDayThreshold`; a cell whose `canEdit` is false
  is not a button (DN-B12, DN-B14-6).
- Clients gate screens on the 59 catalogue keys; the legacy keys of `docs/15` section 3.4
  exist only for v2.11 phones and disappear with them.

## 5. Checklist for a new or changed endpoint

1. Row in section 2 with id, permission, routine, budget, operation id.
2. Codes it can raise in section 3 with their sentences.
3. Schema in `http/schemas/<area>.py` with camelCase aliases and the exact property order.
4. Use case in `application/<area>/` told by the router; no logic in the router.
5. Tests: HTTP behaviour test with the statement budget asserted, routine tests for each
   code, and the OpenAPI assertions when the operation is secured.
