# HTTP contract inventory: the .NET API (apps/api) and what web, mobile and shared depend on

Purpose: capture the HTTP contract of `apps/api` (ASP.NET Core 10 minimal APIs, `Auth.Api` project) exactly, so the Python
rewrite can be built without reading the C# and the existing web (`apps/web`) and mobile (`apps/mobile`) clients keep
working unchanged.

Basis of this inventory
- Repository `C:\Users\user\Documents\Coding\PrioriTech\xcode-wt\revenue`, branch `fix/format`, HEAD `3253914`.
- Read-only inventory of the working tree as it was on 2026-10-07. Paths below are relative to the repository root.
- Facts that exist only in uncommitted files are marked **(uncommitted)**. At the time of reading, the uncommitted API
  edits were: `apps/api/Api/SetupEndpoints.cs` (history route), `apps/api/Application/Setup/SetupContracts.cs`
  (`HistoryPage`), `apps/api/Application/Setup/ISetupRepository.cs`, `apps/api/Application/ISetupExecution.cs`,
  `apps/api/Infrastructure/Setup/{SetupRepository,SetupExecution,SetupModel,HistoryCountCache}.cs`,
  `apps/api/Infrastructure/RevenueRepository.cs`, `apps/api/Domain/Setup/OrganizationSettingsVersion.cs` and a new
  migration `ChangeLogVehicle`. Of those, only `GET /setup/history` changes the wire contract (an additive superset);
  the rest changes who may see which change-log row. Uncommitted edits in `packages/shared/src/{dates,format,revenue,intlCache}.ts`
  are internal performance refactors and do not change any type or wire shape.
- "Framework default (unverified)" marks behaviour that comes from ASP.NET Core / System.Text.Json defaults and is not
  pinned by a test in this repository. It could not be run (no builds or tests were allowed), so treat those lines as
  the first things to verify against a live .NET instance if exact parity matters.
- `file:line` references use the numbering of the file as read, corrected on 2026-10-08 for `Program.cs`, `Domain/Organization.cs`, `Infrastructure/AuthDb.cs`, `Infrastructure/OrganizationRepository.cs`, `Application/OrganizationPort.cs` and wherever a statement's content changed in remediation phases 4 to 6. Other citations into files edited since (the use cases, `RevenueRepository.cs`, `SetupRepository.cs`) can be a few lines off; the last section `Drift log (phases 4 to 6)` lists every change and wins over any older statement above.

Section list
1. Global conventions
2. Endpoint table
3. Per-feature detail (DTOs, enums, call sequences)
4. Client expectations (shared, web, mobile)
5. Naming audit
6. Open questions and ambiguities

---

## 1. Global conventions

### 1.1 Hosts, base paths and who calls what

| Item | Value | Source |
|---|---|---|
| API route prefix | none. Routes start at `/auth`, `/setup`, `/health`, `/openapi`. No `/api`, no `/v1` | `apps/api/Program.cs:170-180`, `Api/*.cs` |
| API version header or path | none | whole of `apps/api` |
| API default dev address | `http://localhost:5000` (web proxy fallback), `http://10.0.2.2:5000` (Android emulator fallback), `http://localhost:5000` (iOS fallback) | `apps/web/app/api/body.ts:22`, `apps/mobile/src/lib/api.ts:19-22` |
| Web browser base path | same-origin Next.js route handlers `/api/auth/*` and `/api/setup/*`, which forward to the API `/auth/*` and `/setup/*`. The browser never calls the .NET API directly | `apps/web/lib/api.ts:5`, `apps/web/lib/data/request.ts:25`, `apps/web/app/api/auth/[...path]/route.ts:153-154`, `apps/web/app/api/setup/[...path]/route.ts:84-85` |
| Web upstream URL | env `API_URL`; required in production and must be `https:` (or `http://localhost` / `http://127.0.0.1`) | `apps/web/app/api/body.ts:4-23` |
| Mobile base URL | env `EXPO_PUBLIC_API_URL` (must be `https://` in release builds); auth calls go to `${apiUrl}/auth/<operation>`, other calls to `${apiUrl}/<path>` (for example `auth/session`, `setup/appearance`, `setup/revenue...`) | `apps/mobile/src/lib/api.ts:19-35,79,151` |
| Web proxy request timeout | 15 s (`AbortSignal.timeout(15_000)`) | auth `route.ts:45,174`; setup `route.ts:97` |
| Mobile request timeout | 15 s (`REQUEST_TIMEOUT_MS`); a timeout is treated as offline | `apps/mobile/src/lib/api.ts:59-77` |

Consequence for the rewrite: the API sees two kinds of callers. The mobile app calls it directly. The web calls it
server-to-server from the Next.js process, which adds `X-Request-ID`, optionally `X-Forwarded-For`, and always sends
`Authorization: Bearer` taken from an HttpOnly cookie. Neither calls it from a browser origin, so CORS is not exercised.

### 1.2 Environments that change the wire behaviour

| Condition | Effect | Source |
|---|---|---|
| `ASPNETCORE_ENVIRONMENT` = `Development` or `Testing` | `GET /openapi/v1.json` is served. In Production it is not mapped (404). A missing `Auth:SigningKey` is replaced by a random 48-byte key (tokens die on restart) | `Program.cs:23-24,179-180` |
| `AuthOptions.DevelopmentMode` = Development environment AND a "local" connection string (contains `localhost`, `(localdb)`, `127.0.0.1`, `:memory:`, `mode=memory` or `.db`, or is empty) | verification codes are returned in the response body as `developmentCode`, and the one-minute resend cooldown on codes is disabled; the dev email sender only logs | `Program.cs:29-39,73-74`, `Application/Authentication/AuthCodes.cs:17-41` |
| Production (any environment other than Development and Testing) | startup requires `Email:Host`, `Email:From` and `ConnectionStrings:Auth`; a missing or empty one stops the host while it is built with an `InvalidOperationException` whose message is `Email:Host is required.`, `Email:From is required.` or `ConnectionStrings:Auth is required.`. `Auth:SigningKey` of at least 32 UTF-8 bytes is always required (`Set Auth__SigningKey to at least 32 random bytes.`; only Development and Testing invent a random key), `Auth:TrustLifetimeDays` must be positive or null, `RateLimiting:AuthPermitLimit` positive, every `ForwardedHeaders:KnownProxies` entry an IP address. Starting the API never creates or migrates the schema outside a local Development database: a Production start against an empty database issues no `CREATE TABLE`, never touches `__EFMigrationsHistory` and fails at the unassigned-users check (`Program.cs:237`, reads `Users`). Schema changes run only with the explicit `--migrate` argument (`Program.cs:188-199`), once per release before any replica starts | `Program.cs:25-27,42-47,91-92,188-199,202-213`, `tests/api/ProductionStartupTests.cs:34-73`, `apps/api/Dockerfile:15-16` **(uncommitted)** |
| `RateLimiting:AuthPermitLimit` | default 30 per minute, 10000 when environment is `Testing`; must be > 0 | `Program.cs:91-92` |
| `Testing` environment | skips migrations, provisioning commands and startup checks | `Program.cs:181` |

### 1.3 JSON serialization (applies to every JSON body, request and response)

No global JSON options are configured anywhere in `apps/api` (searched for `ConfigureHttpJsonOptions`, `JsonNamingPolicy`: only
`Application/Settings/SettingsText.cs:11` has a private `JsonSerializerOptions(JsonSerializerDefaults.Web)`, used for the settings change-log text, not for responses).
The one converter is per type: `[JsonConverter(typeof(JsonStringEnumConverter<CellStatus>))]` on revenue `CellStatus` (`Application/RevenueContracts.cs:20`), see the enum bullet below.
So the ASP.NET Core minimal-API default applies, which is `System.Text.Json` with `JsonSerializerDefaults.Web`:

- Property names are **camelCase** on output (`userId`, `accessToken`, `pageNumber`): the first letter of the C# record
  property is lower-cased. Misspelling fixed in phase 6 **(uncommitted)**: the wire name is now **`useGrouping`** (localization, `EffectiveFormats`); the old spelling `useGroupping` is still ACCEPTED on `PUT /setup/organization/settings/localization` and still WRITTEN as a second, read-only field in `appearance.formats` for released clients, see 3.7, section 5 and the drift log.
- Input property names are matched **case-insensitively**. Unknown properties are **ignored** (a body from an older web
  that still sends a retired `category` field is accepted, `tests/api/Phase1ContractTests.cs:185-191`).
- A property missing from a request body takes the record parameter's default (`""` for the `AuthRequest` strings, `null`,
  `0`, `false`, `Guid.Empty`, and `default(DateOnly)` = `0001-01-01` for value types without a default). An explicit JSON
  `null` for a non-optional string becomes `null` and is then rejected by validation. This matters for `/auth/*`: omitted
  field = `""`, explicit `null` = 400 `invalid_request` (`Api/AuthEndpoints.cs:76-80`).
- Numbers may be sent as JSON strings and are still read (`NumberHandling.AllowReadingFromString` is part of the Web
  defaults; framework default, unverified).
- **Nulls are written, never omitted** (default ignore condition is "never"). `tests/api/Phase1ContractTests.cs:126-137`:
  every `AuthResponse` carries all seven properties. The exception is ProblemDetails, whose optional members (`detail`,
  `instance`) are omitted when null (framework default).
- **Enums are written and read as integers**, with exactly one exception: revenue `CellStatus` is a STRING enum on the wire (`none`, `future`, `missing`, `amount`, `reason`; per-type `JsonStringEnumConverter<CellStatus>` with `JsonStringEnumMemberName`, `Application/RevenueContracts.cs:19-28`; wire values pinned by `tests/api/PermissionKeysTests.cs:61-74`). Every other enum stays numeric. Values:
  - `RecurringKind`: `1` = Cost, `2` = Savings (`Domain/Setup/RecurringSchedule.cs:12-16`)
  - `RecurrenceFrequency`: `1` = Daily (legacy, refused for new saves), `2` = Weekly, `3` = Monthly, `4` = Yearly (`RecurringSchedule.cs:3-10`)
  - `ExpenseBucket`: `1` = RepairsAndMaintenance, `2` = RecurringCharges, `3` = LoanRepayments (`Domain/Setup/ExpenseCatalog.cs:5-10`)
  - Values that look like enums but are plain strings: auth `status`, revenue `reason`
    (`"Garage"`, `"Arrest"`, `"No Crew"`, `"Other"`), `scopeMode`, `themeMode`, `datePattern`, `weekNumbering`, period.
- **Money and other decimals are JSON numbers** (for example `21000`, `1500.00`, `0.5`). They must never be emitted as
  strings (a Pydantic v2 `Decimal` serialises as a string by default, which would break every client). Database precision is
  `decimal(14,2)` for revenue amounts, targets, recurring amounts, allocations, investment amounts and approval limits
  (`Infrastructure/OrganizationModel.cs:29`, `RevenueModel.cs:14`, `Setup/SetupModel.cs:28,44,66,73`). Money inputs must be
  > 0, have at most two decimals and be <= 999999999999.99 (`Domain/Setup/PsvCompany.cs:66-72`, `SetupValue.Money`).
- `long` values (`version`, `settingsVersion`, history `version`) are JSON numbers. `double` (`fontScale`) is a JSON number.

### 1.4 Scalar formats

| Type | Wire format | Notes and source |
|---|---|---|
| calendar date (`DateOnly`) | `"yyyy-MM-dd"` (for example `"2026-10-07"`) in bodies, responses, route segments and query strings | `Phase1.Date` helper `tests/api/Phase1ContractTests.cs:77`. The clients' `isDate` accepts exactly `^\d{4}-\d{2}-\d{2}$` with a valid month and day (`packages/shared/src/dates.ts:54,64-74`) |
| instant (`DateTimeOffset`) | ISO-8601 round-trip, always UTC: `"2026-10-07T05:25:29.1234567+00:00"` (up to 7 fractional digits, trailing zeros dropped, offset `+00:00`). Every stored instant is UTC (`Domain/Revenue.cs:82`, `Domain/Setup/OrganizationSettingsVersion.cs:33`, `Infrastructure/OrganizationModel.cs:110-112`) | Browsers and React Native parse it with `new Date(value)` (`packages/shared/src/dates.ts:278-283`), so a `Z` suffix would be equally acceptable. Fields: `HistoryEntry.occurredAt`, `InvestmentEntry.recordedAt` |
| Guid | lowercase hyphenated, for example `"3f2b8c1e-5d4a-4b6f-9a0c-1e2d3c4b5a69"`. The route constraint `{id:guid}` means a non-GUID segment does not match the route at all (404, not 400) | `Api/SetupEndpoints.cs`, `Api/RevenueEndpoints.cs:48` |
| phone number | stored and compared as `+254XXXXXXXXX`. `PhoneNumber.Normalize` accepts `+254712345678`, `254712345678`, `0712345678`, `712345678` (subscriber part must match `^[17][0-9]{8}$`) and returns `+254...`; anything else returns `""` (invalid). Clients send the national form `07XXXXXXXX` (`normalisePhone`) | `Domain/PhoneNumber.cs`, `packages/shared/src/format.ts:114-121` |
| email | trimmed and lower-cased on person save, validated with .NET `MailAddress.TryCreate`, max 320 chars | `Application/`AccessUseCases.cs:113,340` |
| `version` | `long`; starts at 1 on revenue records and memberships; bumps on every change | `Domain/Revenue.cs:76`, `Domain/Organization.cs:127` |

### 1.5 Authentication

Header: `Authorization: Bearer <access JWT>`. No cookie, no API key, no query-string token. (The web keeps the tokens in
HttpOnly cookies `access` and `refresh` and re-sends the access token as a Bearer header from its proxy.)

Access token (`Infrastructure/Security.cs:77-90`, `Program.cs:99-129`):
- HS256 with `Auth:SigningKey` (UTF-8 bytes, at least 32). `typ: JWT`.
- `iss` = `Auth:Issuer` (default `xcode-api`), `aud` = `Auth:Audience` (default `xcode-clients`), `nbf` = issue time, `exp` =
  issue time + the organization's `accessTokenMinutes` (default 10; allowed 1-15). No `iat`, no `jti`. Clock skew is zero.
- Claims, with `MapInboundClaims = false` so names stay raw: `sub` (user Guid), `device` (device id string), `version`
  (user `SecurityVersion` as a string), `org` (organization Guid), `role` (role name), `first_name`, `last_name`, and one
  `permission` claim per effective permission key (a JSON array when there are two or more, a bare string when exactly one).
- The only part of the token any client decodes is `exp` (the web proxy, `apps/web/app/api/auth/[...path]/route.ts:73-85`,
  to size the `access` cookie; it falls back to 600 s when it cannot decode). Clients get names, role and permissions from
  `GET /auth/session`, not from the token.

Per-request session check (`Program.cs:115-127`): after the signature and lifetime check, the server loads the user and the
trusted-device row and rejects (401) unless **all** hold: `sub` parses as a Guid; the user exists with `Status = Active`;
`SecurityVersion.ToString() == version claim`; a `TrustedDevice` exists for (`sub`, `device` claim) with `Revoked = false`
and (`TrustExpiresAt` is null or in the future). Consequence: bumping `User.SecurityVersion`, removing the user, or
revoking or expiring the device kills every outstanding access token **immediately** (tests `OperabilityTests.cs:133-175`).

Refresh token: opaque, 48 random bytes, standard Base64 (64 characters), stored as upper-case hex HMAC-SHA256 (keyed with the
signing key) of the raw value; lifetime = organization `refreshTokenDays` (default 30; 1-90); single use, rotated on every
refresh (`Application/Authentication/SessionTokens.cs:40-48`, `Application/Authentication/SessionService.cs:10-37`).

Authorization has two layers:
1. Framework: `RequireAuthorization()` with no policy name = "any authenticated principal". Applied to the groups `/setup`
   (people, access, companies, vehicles, recurring, expenses, investment, history, organization, appearance, preferences),
   `/setup/revenue`, plus `GET /auth/session` and `POST /auth/devices/{id}/revoke`.
2. Application: each use case then checks **in the database, not from the JWT claims**: the caller has an active
   membership (else 403), and holds the use case's permission key(s) (else 403), and the record is inside the caller's
   data scope (else 404 or 403, depending on the case). The permission key per endpoint is in section 2; the keys are
   listed in section 3.2. `GET /auth/session` is the one place that echoes the permissions **from the token**.

### 1.6 Custom request and response headers

| Header | Direction | Behaviour | Source |
|---|---|---|---|
| `X-Request-ID` | request (optional) and response (always) | Value = first `X-Request-ID` request header, else `Activity.Current.Id`, else `TraceIdentifier`. Echoed unchanged (no validation, no length limit) on **every** response, including 401/403/404/429/500. Also copied into every ProblemDetails body that goes through the problem-details service as `requestId`, and put in the log scope as `RequestId` | `Program.cs:151-162`, `OperabilityTests.cs:91-110` |
| `X-Forwarded-For` | request | Honoured only when the immediate peer is in `ForwardedHeaders:KnownProxies` (default `127.0.0.1`, `::1`; the IPv4-mapped `::ffff:127.0.0.1` also matches). Only `X-Forwarded-For` is processed (not `X-Forwarded-Proto`, `X-Forwarded-Host`, `Forwarded` or `X-Real-IP`). Used solely to pick the rate-limit partition | `Program.cs:78-90`, `tests/api/ForwardedClientTests.cs` |
| `Authorization` | request | Bearer JWT, see 1.5 | |
| `Content-Type: application/json` | request | required on every request that carries a body (see 1.9) | |
| `WWW-Authenticate: Bearer ...` | response on 401 | emitted by the JWT bearer middleware (framework default, unverified) | |
| `Allow` | response on 405 | framework default (unverified) | |
| `Retry-After` | response | not sent. The 429 has no `Retry-After` header and no body | `Program.cs:93-98` |
| `Cache-Control` | response | none set by the API on any response. (The web proxy adds `Cache-Control: no-store`.) | |
| `Accept-Encoding` / `Content-Encoding` / `Vary` | request / response / response | **`/setup/**` only**: when the caller accepts it the body is compressed with Brotli (`br`, level Optimal) or Gzip; the response then carries `Content-Encoding: br` (or `gzip`) and `Vary: Accept-Encoding`. `Accept-Encoding: br` gives `br`, `gzip` gives `gzip`, `gzip, deflate, br` gives `br` (Brotli preferred); no `Accept-Encoding` gives an identity body with no `Content-Encoding`. The decoded bytes equal the plain body. Compressed types are the framework default list (including `application/json`) plus `application/problem+json`; `EnableForHttps = true`. `/auth/**`, `/health*` and `/openapi` are NEVER compressed and carry no `Vary: Accept-Encoding` (token bodies would expose BREACH). React Native's fetch sends only gzip, which is why gzip stays. Test: a 100-row history page compresses to under a quarter of its plain size | `Program.cs:138-146,164-165`, `tests/api/CompressionTests.cs:53-110` **(uncommitted)** |
| device or client identity headers (`X-Device-Id`, `X-Client`, app-version headers, user-agent checks) | **none exist**. The device id travels in the JSON body field `deviceId` and in the JWT `device` claim | `Application/AuthContracts.cs:18-25`, `Infrastructure/Security.cs:81` |
| security headers (HSTS, `X-Content-Type-Options`, CSP) | none from the API (the web sets its own in `apps/web/next.config.ts:5-21` and `apps/web/proxy.ts`) | |

### 1.7 Middleware order (the order the Python app should reproduce)

`Program.cs:147-180`:
1. `UseForwardedHeaders()` (XFF only, trusted proxies only)
2. request-id middleware (`X-Request-ID` in and out, log scope)
3. `UseExceptionHandler()` (with the `AddProblemDetails` customisation: remove `exception`, add `requestId`)
3a. response compression, only for paths that start with `/setup` (`UseWhen`, `Program.cs:164-165`; Brotli and Gzip, see 1.6) **(uncommitted)**
4. `UseCors()`
5. `UseRateLimiter()` (policy `auth`, attached only to the `/auth` group)
6. `UseAuthentication()` (JWT bearer plus the session check above)
7. `UseAuthorization()`
8. endpoint groups in this order: `MapAuth` (`/auth`), `MapSetup` (`/setup`), `MapRevenue` (`/setup/revenue`), `MapPettyCash` (`/setup/pettycash`, new, see `inventory-petty-cash.md`), `MapOrganization` (`/setup`), then health (`/health/live`, `/health/ready`, `/health`), then `MapOpenApi` (dev and test only).

Because the request-id middleware runs before the exception handler, CORS and the rate limiter, `X-Request-ID` is present on 429s and 401s.

### 1.8 Error response shapes (catalogue)

There are **three different error vocabularies**. A client must never be given the wrong one for an endpoint family.

**(A) `/auth/**`: the `AuthResponse` envelope** (always JSON, always all seven properties):

```json
{ "status": "authentication_failed", "accessToken": null, "refreshToken": null,
  "retryAfterSeconds": null, "developmentCode": null, "maskedEmail": null, "minimumPinLength": null }
```

Property order on the wire: `status, accessToken, refreshToken, retryAfterSeconds, developmentCode, maskedEmail, minimumPinLength`
(`Application/AuthContracts.cs:27`). `Content-Type: application/json; charset=utf-8`. The HTTP status is chosen together with
`status` (table in section 3.1). The empty-body exceptions on `/auth/**` are: 401 from the JWT middleware (missing or bad
access token on `session` and `devices/{id}/revoke`), 403 from `Results.Forbid()` (revoke of another device's id), 429 from
the rate limiter, and the framework's 404/405/415/400.

**(B) `/setup/**` (all groups): RFC 7807 `application/problem+json`** produced by the endpoint filter `WithSetupErrors`
(`Api/SetupEndpoints.cs:25-43`) through `Results.Problem(...)`. The body is `{ "type": <RFC 9110 URL for the status>,
"title": ..., "status": <int>, "detail": ... (omitted when null) }` plus optional extension members. `type` is the
framework default (`https://tools.ietf.org/html/rfc9110#section-15.5.1` for 400, `#section-15.5.4` for 403,
`#section-15.5.5` for 404, `#section-15.5.10` for 409; framework default, unverified). `Results.Problem` bodies carry **no**
`traceId` and **no** `requestId` (those are added only by the problem-details service on the 500 path; framework default,
unverified, no test asserts them on 4xx). Clients read only `detail`, `title`, `status` and `current`, never `type` (`earliestMissing` was read until 9276c51 removed the refusal that carried it, drift log entry 24).

Mapping (exception thrown in a use case -> response):

| Exception | Status | `title` | `detail` |
|---|---|---|---|
| `UnauthorizedAccessException` | 403 | `Not permitted in this organization or data scope.` | the exception's own message when it is a custom one (the strings are listed in section 3), otherwise omitted |
| `KeyNotFoundException` | 404 | `Record not found in your scope.` | omitted |
| `ArgumentException` (every validation and business-rule refusal) | 400 | `Invalid setup change` | the message (this is what the UI shows) |
| `DbUpdateConcurrencyException` | 409 | `Settings changed. Reload before saving.` | omitted (any message thrown with it is **not** used) |
| `DbUpdateException` (unique-index or FK violation) | 409 | `A conflicting record exists. Reload before saving.` | omitted |

Revenue group only (`Api/RevenueEndpoints.cs:21-38`): an inner filter that wins over the table above for these three:

| Exception | Status | `title` | `detail` | Extension members |
|---|---|---|---|---|
| `RevenueConflictException` | 409 | `This day already has a different record.` | `This day was changed after you opened it. Check the current record and save again.` | `current`: a full revenue cell (section 3.6) |
| `DbUpdateConcurrencyException` | 409 | `This day was changed by another save.` | `Reload the current record and try again.` | none |
| `RevenueEarlierDayMissingException` (an `ArgumentException`) | 400 | `Invalid setup change` | `Record yyyy-MM-dd before this date first.` (the date is the earliest missing day) | `earliestMissing`: `"yyyy-MM-dd"` **(removed by 9276c51: days are captured in any order; see the drift log entry 24)** |

Organization settings section save only (`Api/OrganizationEndpoints.cs:23-29`; the refusals are produced as results, not exceptions, in `Application/Settings/SettingsSections.cs:103,105`): the one place that answers with a plain
JSON object instead of a problem: `400 {"detail":"Enter an organization name and a lowercase slug using letters, numbers, and hyphens."}`
and `409 {"detail":"This organization slug is already in use."}` (no `title`, `Content-Type: application/json`, NOT `application/problem+json`; test `OrganizationSettingsTests.cs:220-242` asserts the 409's media type and the absent `title`). Nothing is saved on either, no version moves and no change-log row is written. These
are the only two bodies a client gets with no `title`, which is why every client reads `detail`, then `title`.

**(C) Everything else (an unhandled exception): 500** from `UseExceptionHandler`: `application/problem+json`
`{ "type": "https://tools.ietf.org/html/rfc9110#section-15.6.1", "title": "An error occurred while processing your request.", "status": 500, "traceId": "...", "requestId": "<X-Request-ID>" }`
with **no `exception` member** (`Program.cs:131-136`; test `OperabilityTests.cs:113-131` asserts `requestId` equals the
caller's `X-Request-ID`, `traceId` is non-empty and `exception` is absent). Exceptions that are **not** mapped to 4xx and
therefore end as 500 include `InvalidOperationException` ("A read changed state", the append-only and "Tenant cannot
change" guards in `Infrastructure/OrganizationModel.cs` and `Infrastructure/Setup/SetupModel.cs:122-133`) and any database
failure (for example a `SqlException`, or `SaveChanges` failing at commit in the auth flow).

Status by family:

| Status | `/auth/**` | `/setup/**` |
|---|---|---|
| 400 | `AuthResponse` `invalid_request` or `invalid_pin` | Problem `Invalid setup change`, or the organization-section `{detail}` object |
| 401 | `AuthResponse` `authentication_failed` (credentials, codes, refresh); empty body when the JWT is missing or invalid | empty body (JWT missing, invalid, expired, revoked session, bumped security version) |
| 403 | empty body (revoke of a device id that is not the caller's own) | Problem `Not permitted in this organization or data scope.` |
| 404 | none from handlers (only an unknown route: empty body) | Problem `Record not found in your scope.` |
| 409 | none | Problem (several titles above) |
| 423 | `AuthResponse` `paused` + `retryAfterSeconds` | none |
| 429 | empty body | none (not rate limited) |
| 500 | Problem (C) | Problem (C) |
| 503 | `AuthResponse` `service_unavailable` (new-device email could not be sent) | none from handlers (`GET /health/ready` can return 503) |

How the clients treat the codes (what they really rely on is in section 4): the web proxy replaces every upstream status
>= 500 with `503 {"status":"service_unavailable","requestId":"<proxy id>"}`; mobile treats >= 500 as "server error / unreachable".

### 1.9 Request binding and content-type behaviour (framework default, unverified unless a test is cited)

- A body parameter that is declared non-nullable (`AuthRequest`, `SavePerson`, `SaveCompany`, `SaveVehicle`, `SaveRecurring`,
  `StopRecurring`, `SaveRevenue`, `SaveInvestment`, `SaveExpenseCategory`, `SaveExpenseItem`, `CompanyLifecycleRequest`,
  `VehicleLifecycleRequest`, `VehicleRestoreRequest`, `SaveOrganizationSettings`, `SaveLogo`, `SaveUserPreferences`)
  requires `Content-Type: application/json` and a non-empty JSON body. A missing or wrong content type gives **415**; an empty
  body or invalid JSON gives **400**; in Production these two binding failures have an empty body (the framework sets only the
  status code; in Development they throw and surface through the exception handler). The web proxy comment confirms the 415 case:
  "An empty body is not forwarded: fetch would send it as text/plain, which the API refuses (415)"
  (`apps/web/app/api/setup/[...path]/route.ts:95`).
- The only nullable (optional) body parameter is `PersonLifecycleRequest?` on the activate and deactivate routes of a person.
  With no body and no content type it binds `null` and the use case answers 409 "reload" (test
  `tests/api/AccessLifecycleTests.cs:75-102`: status 409, `application/problem+json`, title contains `Reload before saving`).
- Endpoints with **no** body parameter ignore any body that is sent: `POST /setup/people/{id}/sign-out`,
  `POST /setup/recurring/{id}/restore`, the stop and restore routes of expense categories and expense items, all `DELETE`
  routes, and `POST /auth/devices/{id}/revoke` (which never reads its body even though both clients send one).
- Query and route values are parsed with invariant culture: `int` (`page`, `pageSize`), `long` (`before`), `bool` (`true` or
  `false` only), `Guid`, `DateOnly` (`yyyy-MM-dd`). A value that does not parse gives **400** (framework default, unverified).
  Defaults: `page=1`, `pageSize=25`, dashboard `period="week"`, history `includeTotal=true` **(uncommitted)**; `GET /setup/revenue` `page` and `pageSize` have NO default (both absent means the unpaged legacy listing, see R01).
- Routing is case-insensitive and ignores a trailing slash (framework default). A path that matches no route is **404 with an
  empty body**; a known path with the wrong verb is **405** with an `Allow` header and an empty body.
- No body-size limit is configured; Kestrel's default (about 30 MB) applies. The web proxy caps request bodies at 1 MiB
  (`apps/web/app/api/body.ts:26`). The logo endpoint caps its own data URL (section 2.11).

### 1.10 Rate limiting

- Exactly one policy, named **`auth`** (`Program.cs:93-98`), applied with `MapGroup("/auth").RequireRateLimiting("auth")`, that is to
  **all 13 `/auth` endpoints, including `GET /auth/session` and `POST /auth/devices/{id}/revoke`**. No other route is limited
  (no limit on `/setup/**`, `/health*`).
- Fixed window, 1 minute, `PermitLimit` = `RateLimiting:AuthPermitLimit` (default 30; 10000 in Testing), `QueueLimit = 0`.
- Partition key: `HttpContext.Connection.RemoteIpAddress.ToString()` after forwarded-header processing, or the literal `"unknown"`.
  Behind the Next.js proxy every web user shares the proxy's IP unless the proxy forwards `X-Forwarded-For`
  (web env `TRUSTED_PROXY_HOPS` > 0, `apps/web/app/api/body.ts:50-61`) AND the API trusts the proxy (`ForwardedHeaders:KnownProxies`).
- Rejection: **HTTP 429, empty body, no `Retry-After`**, but `X-Request-ID` is present (`Program.cs:95`; `Api/AuthEndpoints.cs:25-27`
  says "The rate limiter's 429 has no body.").
- Tests: `ForwardedClientTests.cs` (limit 2 per minute: 401, 401, 429; separate browsers behind a trusted proxy have separate
  limits; a forwarded address from an untrusted peer is ignored; configured proxies replace loopback).
- Separate from rate limiting, the account lockout model produces 423 `paused` (section 3.1).

### 1.11 CORS

`AddDefaultPolicy(p => p.WithOrigins(Cors:Origins ?? []).AllowAnyHeader().AllowAnyMethod())`, applied through `UseCors()`
(`Program.cs:77,166`). Origins come from configuration key `Cors:Origins` (an array; the default in `appsettings.json` is
`["http://localhost:3000"]`; an absent key yields an empty list, meaning no origin is allowed). No `AllowCredentials`, no
`WithExposedHeaders`, no preflight max-age. Neither client needs it: the web calls the API server-to-server and the mobile
app is native. The Python app should keep an equivalent allow-list policy, but no current client exercises it.

### 1.12 Health endpoints (no authentication, no rate limit)

| Route | Behaviour | Source |
|---|---|---|
| `GET /health/live` | 200, default health-check body, and **no database call** (`Predicate = _ => false`) | `Program.cs:175`, `OperabilityTests.cs:35-40` |
| `GET /health/ready` | runs the check tagged `ready` (named `database`: opens a connection, 10 s timeout). 200 `Healthy`; **503** `Unhealthy` when the database cannot be reached | `Program.cs:76,176`, `Infrastructure/DatabaseHealthCheck.cs`, `OperabilityTests.cs:42-69` |
| `GET /health` | **200 `{"status":"ok"}`** JSON, never touches the database (legacy) | `Program.cs:177`, `OperabilityTests.cs:81-89` |

The default health-check writer returns the plain text body `Healthy`, `Unhealthy` or `Degraded` with `Content-Type: text/plain`
(framework default, unverified; the tests check only the status code).

### 1.13 OpenAPI

- Document route: `GET /openapi/v1.json` (`MapOpenApi()` default pattern), served only in `Development` and `Testing`
  (`Program.cs:179-180`). No Swagger UI is mapped.
- Tests that pin it (`tests/api/OpenApiTests.cs`):
  (a) `paths` contains `/auth/sign-in` and `/setup/people`;
  (b) `POST /auth/sign-in` responses `202` and `423` have `application/json` content with schema `$ref` `#/components/schemas/AuthResponse`, and the operation has **no** `security` member;
  (c) `POST /setup/people/{id}/deactivate` response `409` has `application/problem+json` content with `$ref` `#/components/schemas/ProblemDetails`, and `security[0]` has the key `Bearer`;
  (d) `components.securitySchemes.Bearer` has `type: "http"` and `scheme: "bearer"` (the code also sets `bearerFormat: "JWT"` and a description).
- `Api/OpenApiDocumentation.cs` adds the `Bearer` scheme, adds a `401 Unauthorized` response and a `Bearer` security
  requirement to every operation that has authorize metadata and no anonymous metadata, and forces `needs` to be required and
  non-nullable on the `PermissionItem` schema.
- Tags: `Setup` (`/setup/**` except the next two), `Organization` (`/setup/organization/**`, `/setup/appearance`,
  `/setup/preferences`), `Revenue` (`/setup/revenue/**`). `/auth/**` has no explicit tag. Operation ids (`WithName`) are listed per
  endpoint in section 2; auth endpoints have none. Documented statuses per auth endpoint come from the `Answers(...)` helper
  (`Api/AuthEndpoints.cs:67-72`) and are reproduced in section 2.

---

## 2. Endpoint table

Totals: **70 always-on routes** (13 auth + 44 in `SetupEndpoints` + 3 revenue + 7 organization/appearance/preferences + 3 health)
plus **1 conditional route** (`GET /openapi/v1.json`, Development and Testing only) = 71, plus **10 petty cash routes** under `/setup/pettycash` **(uncommitted)** that this table does not list (see `inventory-petty-cash.md`) = 81. Source of the route list:
`Api/AuthEndpoints.cs:26-64`, `Api/SetupEndpoints.cs:50-173`, `Api/RevenueEndpoints.cs:18-57`,
`Api/OrganizationEndpoints.cs:17-51`, `Program.cs:175-180`.

### 2.0 Legend and rules that apply to many rows

- **member** = the caller has an active `OrganizationMembership` in the organization named by the JWT `org` claim. Every
  `/setup/**` endpoint requires it. Without it (or with an empty `org` or `sub` claim) the answer is 403 Problem (no `detail`).
- **perm X** = member AND the caller's effective permission set (resolved from the database: role defaults from the catalog, plus
  per-person overrides, dependencies expanded, denied permissions removed; section 3.2) contains X. **any of [X, Y]** = at least
  one. A missing permission is 403 Problem `Not permitted in this organization or data scope.` with no `detail`, unless the row
  names a custom detail.
- **scope** = data scope. The caller's `SetupActor` has `AllCompanies`, `CompanyIds`, `VehicleIds`. Visible vehicles = AllCompanies,
  or the vehicle's company is in CompanyIds, or the vehicle id is in VehicleIds. Visible companies = AllCompanies, or id in
  CompanyIds, or the company owns a visible vehicle. A record outside scope is reported as **404**
  (`Record not found in your scope.`) unless the row says otherwise.
- **business date ("today")** = `Organization.BusinessDate` when one is held, else today's calendar date in the organization time
  zone (`OrganizationLocalization.TimeZone`, default `Africa/Nairobi`; `Infrastructure/Setup/SetupExecution.cs:42-49`). Never the
  caller's or the browser's date.
- **write** = serializable transaction + `SaveChanges` + commit, retried up to 3 times (random 5-25 ms times the attempt number)
  when only the organization row collided (every write that logs to the change log bumps `Organization.SettingsVersion`, a
  concurrency token) or on SQL Server deadlock 1205 (`Infrastructure/OrganizationRepository.cs:50-92`). **read** = no transaction;
  a read that changed tracked state fails with a 500.
- **change-log write** = the write also appends an `OrganizationSettingsVersion` row (section, entity id, before and after JSON
  text, reason, actor, UTC instant, new version number = the bumped `SettingsVersion`) and an `AuditEvent`. Reasons are generated
  by the server (exact strings per row and in section 3.9). A typed `reason` is optional (after trimming 1-500 chars, else 400
  `A reason of 1–500 characters is required.`) and is appended as `. Reason: <typed>.` (a typed reason already ending in `.`, `!`
  or `?` does not get a second full stop).
- **Paging** (`Page<T>`) = query `page` (default 1) and `pageSize` (default 25). Both are validated: page 1..100000 and pageSize
  1..100, else 400 `Page must be 1–100000 and page size 1–100.` (the dash is an EN DASH, U+2013). Response
  `{ items, pageNumber, pageSize, total }`; `pageNumber` and `pageSize` echo the request.
- Every `/setup/**` row also has these answers, which are not repeated: 401 empty body (bad or missing JWT), 403 Problem, 500
  Problem (C). The rows list only what is specific.
- Request bodies are JSON with `Content-Type: application/json`; property names match case-insensitively; unknown properties are
  ignored (section 1.3).
- The DTO catalog (section 3) holds every field list; the "Success" column names the DTO.

### 2.1 Master index (one row per endpoint)

| ID | Method and route | Auth | Rate limit | Success | OpenAPI operationId |
|---|---|---|---|---|---|
| A01 | `POST /auth/sign-in` | anonymous | `auth` | 200 `AuthResponse` authenticated; 202 verification_required | none |
| A02 | `POST /auth/unlock` | anonymous | `auth` | same handler as A01 | none |
| A03 | `POST /auth/verify-device` | anonymous | `auth` | 200 `AuthResponse` authenticated | none |
| A04 | `POST /auth/setup-pin/request` | anonymous | `auth` | 202 `AuthResponse` check_email | none |
| A05 | `POST /auth/setup-pin/verify` | anonymous | `auth` | 200 `AuthResponse` code_verified | none |
| A06 | `POST /auth/setup-pin/complete` | anonymous | `auth` | 200 `AuthResponse` authenticated | none |
| A07 | `POST /auth/pin-reset/request` | anonymous | `auth` | 202 `AuthResponse` check_email | none |
| A08 | `POST /auth/pin-reset/verify` | anonymous | `auth` | 200 `AuthResponse` code_verified | none |
| A09 | `POST /auth/pin-reset/complete` | anonymous | `auth` | 200 `AuthResponse` authenticated | none |
| A10 | `POST /auth/refresh` | anonymous (refresh token in body) | `auth` | 200 `AuthResponse` authenticated | none |
| A11 | `POST /auth/sign-out` | anonymous (refresh token in body) | `auth` | 200 `AuthResponse` signed_out | none |
| A12 | `POST /auth/devices/{id}/revoke` | JWT, own device only | `auth` | 200 `AuthResponse` device_revoked | none |
| A13 | `GET /auth/session` | JWT | `auth` | 200 `AuthSessionResponse` | none |
| S01 | `GET /setup/access/catalog` | member | none | `PermissionGroup[]` | `GetAccessCatalog` |
| S02 | `GET /setup/access/roles` | perm `people.view` | none | `AccessRole[]` | `ListAccessRoles` |
| S03 | `GET /setup/access/scope-options` | perm `people.manage` | none | `ScopeOptions` | `GetAccessScopeOptions` |
| S04 | `GET /setup/access/me` | member | none | `MyScope` | `GetMyAccessScope` |
| S05 | `GET /setup/people` | perm `people.view` | none | `Page<PersonDto>` | `ListPeople` |
| S06 | `GET /setup/people/{id}` | perm `people.view` | none | `PersonDto` | `GetPerson` |
| S07 | `POST /setup/people` | perm `people.manage` plus extra rules | none | `{id}` | `CreatePerson` |
| S08 | `PUT /setup/people/{id}` | perm `people.manage` plus extra rules | none | `{id}` | `UpdatePerson` |
| S09 | `POST /setup/people/{id}/activate` | perm `people.manage` | none | `{id}` | `ActivatePerson` |
| S10 | `POST /setup/people/{id}/deactivate` | perm `people.manage` | none | `{id}` | `DeactivatePerson` |
| S11 | `POST /setup/people/{id}/sign-out` | perm `people.manage` | none | `{id}` | `SignOutPerson` |
| S12 | `GET /setup/companies` | perm `companies.manage` | none | `Page<CompanyDto>` | `ListSetupCompanies` |
| S13 | `POST /setup/companies` | perm `companies.manage` and AllCompanies | none | `{id}` | `CreateSetupCompany` |
| S14 | `PUT /setup/companies/{id}` | perm `companies.manage` | none | `{id}` | `RenameSetupCompany` |
| S15 | `POST /setup/companies/{id}/archive` | perm `companies.manage` | none | `{id}` | `ArchiveSetupCompany` |
| S16 | `POST /setup/companies/{id}/restore` | perm `companies.manage` | none | `{id}` | `RestoreSetupCompany` |
| S17 | `GET /setup/vehicles` | any of [`vehicles.manage`, `invest.view`] | none | `Page<VehicleDto>` | `ListSetupVehicles` |
| S18 | `POST /setup/vehicles` | perm `vehicles.manage` | none | `{id}` | `CreateSetupVehicle` |
| S19 | `PUT /setup/vehicles/{id}` | perm `vehicles.manage` | none | `{id}` | `UpdateSetupVehicle` |
| S20 | `GET /setup/vehicles/company-options` | perm `vehicles.manage` | none | `CompanyOption[]` | `ListVehicleCompanyOptions` |
| S21 | `POST /setup/vehicles/{id}/retire` | perm `vehicles.manage` | none | `{id}` | `RetireSetupVehicle` |
| S22 | `POST /setup/vehicles/{id}/restore` | perm `vehicles.manage` | none | `{id}` | `RestoreSetupVehicle` |
| S23 | `GET /setup/vehicles/{id}/report` | perm `vehicles.manage` | none | `VehicleReport` | `GetSetupVehicleReport` |
| S24 | `GET /setup/recurring` | perm `commitments.view` | none | `Page<RecurringDto>` | `ListSetupRecurring` |
| S25 | `GET /setup/recurring/vehicle-options` | perm `commitments.manage` | none | `VehicleOption[]` | `ListRecurringVehicleOptions` |
| S26 | `POST /setup/recurring` | perm `commitments.manage` | none | `{id}` | `CreateSetupRecurring` |
| S27 | `PUT /setup/recurring/{id}` | perm `commitments.manage` | none | `{id}` | `ReviseSetupRecurring` |
| S28 | `POST /setup/recurring/{id}/stop` | perm `commitments.manage` | none | `{id}` | `StopSetupRecurring` |
| S29 | `POST /setup/recurring/{id}/restore` | perm `commitments.manage` | none | `{id}` | `CancelSetupRecurringStop` |
| S30 | `GET /setup/history` | perm `audit.view` | none | `HistoryPage` (uncommitted; HEAD: `Page<HistoryEntry>`) | `ListSetupHistory` |
| S31 | `GET /setup/expense-categories` | any of [`expenses.view`, `expenses.setup`, `commitments.view`] | none | `Page<ExpenseCategoryDto>` | `ListExpenseCategories` |
| S32 | `GET /setup/expense-items/options` | any of [`expenses.view`, `expenses.setup`, `commitments.view`, `commitments.manage`] | none | `ExpenseItemOption[]` | `ListExpenseItemOptions` |
| S33 | `POST /setup/expense-categories` | perm `expenses.setup` | none | `{id}` | `CreateExpenseCategory` |
| S34 | `PUT /setup/expense-categories/{id}` | perm `expenses.setup` | none | `{id}` | `UpdateExpenseCategory` |
| S35 | `POST /setup/expense-categories/{id}/stop` | perm `expenses.setup` | none | `{id}` | `StopExpenseCategory` |
| S36 | `POST /setup/expense-categories/{id}/restore` | perm `expenses.setup` | none | `{id}` | `RestoreExpenseCategory` |
| S37 | `POST /setup/expense-categories/{id}/items` | perm `expenses.setup` | none | `{id}` | `CreateExpenseItem` |
| S38 | `PUT /setup/expense-items/{id}` | perm `expenses.setup` | none | `{id}` | `RenameExpenseItem` |
| S39 | `POST /setup/expense-items/{id}/stop` | perm `expenses.setup` | none | `{id}` | `StopExpenseItem` |
| S40 | `POST /setup/expense-items/{id}/restore` | perm `expenses.setup` | none | `{id}` | `RestoreExpenseItem` |
| S41 | `GET /setup/vehicles/{id}/investment` | perm `invest.view` | none | `InvestmentDto` | `GetVehicleInvestment` |
| S42 | `POST /setup/vehicles/{id}/investment` | perm `invest.manage` | none | `{id}` | `AddVehicleInvestment` |
| S43 | `PUT /setup/investment/{id}` | perm `invest.manage` | none | `{id}` | `UpdateVehicleInvestment` |
| S44 | `DELETE /setup/investment/{id}` | perm `invest.manage` | none | `{id}` | `DeleteVehicleInvestment` |
| R01 | `GET /setup/revenue` | perm `revenue.view` | none | `RevenueWeekDto` | `GetRevenueWeek` |
| R02 | `GET /setup/revenue/dashboard` | any of [`dash.capture`, `dash.revenue`, `dash.gaps`, `dash.edits`] | none | `RevenueDashboardDto` | `GetRevenueDashboard` |
| R03 | `PUT /setup/revenue/{vehicleId}/{date}` | any of [`revenue.capture`, `revenue.correct`] plus per-case rules | none | `RevenueSaved` `{id, version}` | `SaveRevenue` |
| O01 | `GET /setup/organization/settings` | perm `organization.manage` | none | `OrganizationSettingsResponse` | `GetOrganizationSettings` |
| O02 | `PUT /setup/organization/settings/{section}` | perm `organization.manage` | none | `{section}` | `UpdateOrganizationSettings` |
| O03 | `PUT /setup/organization/logo` | perm `organization.manage` | none | `{logo}` | `UpdateOrganizationLogo` |
| O04 | `DELETE /setup/organization/logo` | perm `organization.manage` | none | `{logo: null}` | `DeleteOrganizationLogo` |
| O05 | `GET /setup/appearance` | member | none | `AppearanceResponse` | `GetAppearance` |
| O06 | `GET /setup/preferences` | member | none | `PreferencesResponse` | `GetUserPreferences` |
| O07 | `PUT /setup/preferences` | member | none | `UserPreference` | `UpdateUserPreferences` |
| H01 | `GET /health/live` | anonymous | none | 200 | none |
| H02 | `GET /health/ready` | anonymous | none | 200, or 503 | none |
| H03 | `GET /health` | anonymous | none | 200 `{"status":"ok"}` | none |
| X01 | `GET /openapi/v1.json` (Development and Testing only) | anonymous | none | 200 OpenAPI document | none |

Notes on the index
- A success shown as `{id}` is `Results.Ok(new IdResponse(Guid))`: HTTP **200** (not 201) with body `{"id":"<guid>"}`, creates
  included. A no-op (nothing changed) returns the same 200 `{id}` and writes no change-log row.
- Route templates written `{id}` under `/setup/**` are `{id:guid}` constraints (a non-GUID segment is a 404 with an empty body).
  In `/auth/devices/{id}/revoke` the id is a free string. Revenue is `{vehicleId:guid}/{date}`; organization settings is `{section}`.

### 2.2 Auth endpoints in detail (A01-A13)

**Common to A01-A11** (`Api/AuthEndpoints.cs:28-48,73-83`, `Infrastructure/AuthUnitOfWork.cs:11-47`)
- Request body `AuthRequest`: `{ "email": "", "phoneNumber": "", "pin": "", "deviceId": "", "code": "", "refreshToken": "" }`, all strings.
  Both clients always send all six (blank when unused); the mobile comment says "The API rejects a request with any field missing"
  but the server actually defaults an omitted field to `""` (only an explicit `null` is refused).
- Pre-validation (400 `{"status":"invalid_request", ...nulls}`, before any lookup): `deviceId` null or length outside 1..128; `phoneNumber` null
  or longer than 14; `email` null, longer than 320, or non-empty and not a valid address (.NET `MailAddress.TryCreate`); `pin` null or
  longer than 8; `code` null or longer than 32; `refreshToken` null or longer than 256. (The web proxy applies stricter limits first:
  phone <= 20, email <= 320, pin <= 8, code <= 6.)
- Serialisation (`Infrastructure/AuthUnitOfWork.cs:11-33`, `Infrastructure/AuthGate.cs:7-43`): per phone number (normalised `+254...`, or `device:<deviceId>` when the phone does not normalise; for A12 the lock key is the ACCOUNT's phone, see A12) a per-key `SemaphoreSlim` in the singleton `AuthGate`
  serialises the request; the work runs inside the DB execution strategy in a SERIALIZABLE transaction with SaveChanges and commit (a retried attempt starts with `ChangeTracker.Clear()`), the semaphore is released, and only then `Deliver` sends the email of the COMMITTED attempt (`AuthResult.Mail`; a rolled-back or retried attempt never mails).
  The lock map is capped at 10 000 keys (above that the least recently used idle semaphores are evicted down to 80 percent; evicted semaphores are never disposed). In-process only. Concurrent wrong PINs therefore all count (test `ConcurrentFailuresCannotLoseAttempts`).
- Rate limit `auth` on every one. Content-Type of the answer `application/json`.
- Enumeration resistance (byte-for-byte equal responses, tests `AuthTests.cs:36-72,112-127,147-167,575-598`): for a number with no account, a number that does not normalise,
  an inactive account, a paused account seen from an untrusted device, an untrusted device past the per-account cap, a wrong PIN from
  an untrusted device, the answer is identical (same status, same headers apart from `Date`, `Content-Length`, `X-Request-ID`, same body):
  401 `authentication_failed` for sign-in/unlock/verify/complete; 202 `check_email` for the two `request` endpoints. Do not add any new
  per-request response header on `/auth/**` without excluding it from this comparison.

**A01 `POST /auth/sign-in` and A02 `POST /auth/unlock`** (identical handler `SignInService.SignIn`, `Application/Authentication/SignInService.cs:11-56`)
- Uses `phoneNumber`, `pin`, `deviceId`.
- 200 `authenticated` (+`accessToken`, `refreshToken`): PIN correct and this device is trusted (TrustedDevice row valid) and not paused. Clears the failed-attempt counter.
- 202 `verification_required` (+`maskedEmail`, +`developmentCode` only in DevelopmentMode): PIN correct but the device is not trusted; a 6-digit code was issued by email (purpose NewDevice). `maskedEmail` = first character + `***` + the rest from `@` (`a***@example.com`; `***` if no usable `@`).
  Issuance is silently skipped (still 202, `developmentCode` null, no email) when a non-withdrawn NewDevice code is less than 1 minute old (not in DevelopmentMode), or the user already has 5 non-withdrawn codes in the last hour or 10 in 24 hours.
- 401 `authentication_failed`: unknown, inactive or PIN-less account; wrong PIN; paused account seen from a device that is not trusted; untrusted device past the cap.
- 423 `paused` (+`retryAfterSeconds` = ceil(seconds until `PausedUntil`)): the account is paused and this device IS trusted. The wrong PIN that reaches the lockout threshold already answers 423 with the full pause length (policy `lockoutMinutes` x 60, default 900).
- 503 `service_unavailable`: the NewDevice email could not be sent (the code is withdrawn so a retry sends a new one). Only this purpose is sent before the reply; setup and reset codes are sent after the reply.
- 429 / 500 as in section 1.
- Lockout model: wrong PIN on a trusted device increments `FailedAttempts`; at `policy.lockoutThreshold` (default 5, clamped 3..10) the account is paused for `lockoutMinutes` (default 15, clamped 1..60). Pause end clears the counter lazily on the next attempt. Wrong PIN on an untrusted device increments `UntrustedFailedAttempts` (cap `SignInService.UntrustedAttemptLimit` = 10, `SignInService.cs:9`); at or past 10 an untrusted device gets 401 without any PIN check. The cap resets only on `SetPin` or a verified new device (A03); a correct PIN from a trusted device does not reset it, and issuing tokens does not clear lockout (the callers do).
- PIN verification always runs PBKDF2 (a dummy hash for unknown users) to equalise timing.

**A03 `POST /auth/verify-device`** (`SignInService.VerifyDevice`, `SignInService.cs:58-72`)
- Uses `phoneNumber`, `code`, `deviceId`. Succeeds only for a NewDevice code that was issued FOR THIS `deviceId` (a code issued to device X cannot trust device Y; test `AUTH13`).
- 200 `authenticated` (+tokens): user active, has a PIN, not paused; the newest unconsumed NewDevice code for (user, deviceId) is usable (not consumed, `now <= expiresAt`, fewer than 5 failed tries) and equals `code` (constant-time compare of the HMAC hash). Effects: code consumed, lockout cleared, `UntrustedFailedAttempts` reset to 0, `TrustedDevice` created or re-trusted (expiry `now + Auth:TrustLifetimeDays` days, or never when unset), tokens issued.
- 401 `authentication_failed` for every other case. A wrong code increments that code's failed-try counter; the 5th wrong try consumes it (a later correct code then also fails). 400 invalid_request per pre-validation.

**A04 `POST /auth/setup-pin/request` and A07 `POST /auth/pin-reset/request`** (`PinSetupService.Request`, `Application/Authentication/PinSetupService.cs:10-15`)
- Uses `phoneNumber`, `deviceId`. Setup (FirstSetup) is only honoured for an active user WITHOUT a PIN; reset (PinReset) only for an active user WITH a PIN. Otherwise nothing is sent.
- Always **202** `{"status":"check_email", developmentCode: <code only in DevelopmentMode, else null>, others null}` regardless of whether an email was sent (enumeration resistance). The email is sent after the reply (so response time does not reveal accounts); a failed send is logged, the code is withdrawn (consumed and expired) and the reply is still 202 `check_email`. Code rules as in A01 (10 minute expiry, 6 digits zero-padded, 1-minute cooldown, 5 per hour, 10 per day).
- Codes are bound to purpose and `deviceId`.

**A05 `POST /auth/setup-pin/verify` and A08 `POST /auth/pin-reset/verify`** (`PinSetupService.VerifyCode`, `PinSetupService.cs:17-23`)
- Uses `phoneNumber`, `code`, `deviceId`. 200 `{"status":"code_verified"}` when the purpose matches the account state (setup: no PIN; reset: has PIN) and the newest unconsumed code for (user, deviceId, purpose) is usable and equal. The code is NOT consumed (the same code is then sent again to complete). 401 `authentication_failed` otherwise; wrong tries count towards the code's 5-try limit.

**A06 `POST /auth/setup-pin/complete` and A09 `POST /auth/pin-reset/complete`** (`PinSetupService.CompletePin`, `PinSetupService.cs:25-48`)
- Uses `phoneNumber`, `pin`, `code`, `deviceId`. Order of checks:
  1. PIN rules (`PinRules.IsValid`): 4-8 ASCII digits `0-9` only, not all the same digit, not a full +1 or full -1 step sequence (so `1111`, `0000`, `1234`, `4321`, `01234567`, `87654321`, `123`, `123456789`, full-width digits and `58a6` are refused). Failure => **400** `{"status":"invalid_pin","minimumPinLength":4}`. This check runs FIRST, before any account lookup, so it leaks nothing about the number.
  2. User lookup: unknown, inactive, or wrong purpose state (setup needs no PIN; reset needs a PIN) => 401 `authentication_failed`.
  3. Organization policy PIN length (`pinLength`, 4..8, from the user's active membership organization; default 4): if `pin.length < pinLength` => if the code is NOT valid => 401; if the code IS valid (disclosure only with a valid code, test `PolicyPinLengthAppliesToNewPinsAndIsOnlyDisclosedWithAValidCode`) => **400** `invalid_pin` with `minimumPinLength` = the policy length. The code is not consumed on this refusal.
  4. Code must be valid and matching (consumed on success) else 401.
- Success 200 `authenticated` (+tokens). Effects: PIN hash stored (`SetPin`: SecurityVersion +1, `UntrustedFailedAttempts` = 0), lockout cleared (a reset by email lifts any pause), ALL the user's refresh tokens revoked (all devices), every other unconsumed code consumed, this device trusted, new tokens issued. Every outstanding access token dies because `SecurityVersion` changed.

**A10 `POST /auth/refresh`** (`SessionService.Refresh`, `Application/Authentication/SessionService.cs:10-37`)
- Uses `refreshToken`, `deviceId` (no Authorization header needed). Looks up the token by HMAC hash; it must belong to the same `deviceId`.
- 200 `authenticated` with a NEW `accessToken` and NEW `refreshToken`; the presented token is revoked (single use, rotation).
- 401 `authentication_failed` when: token unknown or device mismatch; the user is not active (then ALL the user's tokens are revoked); the token was already revoked (replay: revokes all the user's tokens for that device); the token is expired (`now >= expiresAt`); the user is currently paused; the device is no longer trusted. Failures that revoke commit their revocations (no exception is thrown).
- Role, name and permissions in the new access token are re-read, so this is how clients pick up changed access after the 401 caused by a SecurityVersion bump.

**A11 `POST /auth/sign-out`** (`SessionService.SignOut`, `SessionService.cs:39-47`)
- Uses `refreshToken`, `deviceId`. Revokes all refresh tokens of that user on that device when the token matches (hash and device). **Always 200** `{"status":"signed_out"}`, even for an unknown token. The trusted-device row is left in place (the device stays trusted).

**A12 `POST /auth/devices/{id}/revoke`** (`Api/AuthEndpoints.cs:50-56`, `SessionService.RevokeDevice`, `SessionService.cs:49-59`)
- Requires a valid JWT (otherwise 401, empty body). `id` must equal the JWT `device` claim exactly (ordinal, case-sensitive) else **403 with an empty body** (`Results.Forbid()`); a device can only revoke itself. The request body is not read.
- 200 `{"status":"device_revoked"}`: the `TrustedDevice` is marked revoked, the user's refresh tokens for that device are revoked, pending codes for that device are consumed. The caller's own access token stops working immediately (device check) and the next sign-in on that device needs an email code again (`verification_required`).
- 400 `invalid_request` if `id` is longer than 128 characters (it is run through the same pre-validation with an otherwise blank request).
- Lock key (changed in phase 4 to 6): the request waits on the ACCOUNT's lock, the normalised phone of the JWT user (`SessionService.AccountKey`, `SessionService.cs:61-63`; `AuthEndpoints.cs:55`), so a revoke cannot interleave with that account's sign-in or refresh. Only when the user row is not found does it fall back to `device:<id>`. The body is still not read.
- The web proxy maps its own path `devices/current/revoke` to `devices/<its device cookie>/revoke`.

**A13 `GET /auth/session`** (`Api/AuthEndpoints.cs:57-64`)
- Requires a valid JWT. 200 `AuthSessionResponse` built from the TOKEN CLAIMS, not the database: `{"userId":"<sub>","firstName":"<first_name or ''>","lastName":"<last_name or ''>","role":"<role or ''>","permissions":["..."]}` (permissions in token order, i.e. the order of the effective permission set at issue time). Order of properties: `userId, firstName, lastName, role, permissions`.
- 401 empty body otherwise. A token whose user, SecurityVersion or device no longer validates is a 401 here (tests `RevokedUserIsRejected`, `RevokedDeviceIsRejected`).

### 2.3 Access and people endpoints in detail (S01-S11)

**S01 `GET /setup/access/catalog`** (`AccessUseCases.Catalog`): any member (no permission). 200 `PermissionGroup[]`: the static catalog of section 3.2, in that exact group and item order.
Labels only, so every member may read them ("Your access"). Used by web ("Your access" dialog, people editor) and by mobile (`apps/mobile/src/shell/AppShell.tsx:51`).

**S02 `GET /setup/access/roles`**: perm `people.view`. Runs as a WRITE (serializable transaction) because it creates any catalog role the organization is missing
(`Owner`, `Office admin`, `Fleet manager`, `Revenue clerk`). 200 `AccessRole[]` sorted by role name: `{ id: guid, name: string, permissions: string[] }` where `permissions` = the role's default permissions with dependencies expanded (a set; order not significant).

**S03 `GET /setup/access/scope-options`**: perm `people.manage`. 200 `{ companies: [{id,name}], vehicles: [{id,registration,companyId}] }` limited to what the caller may hand on:
companies = (AllCompanies or id in CompanyIds) and not archived as of today, ordered by name; vehicles = (AllCompanies or vehicle in VehicleIds or company in CompanyIds) and joined by today and not left and company not archived, ordered by registration.

**S04 `GET /setup/access/me`**: any member. 200 `{ allCompanies: bool, companies: [{id,name}], vehicles: [{id,registration,companyId}] }` = the caller's own visible companies (ordered by name) and visible vehicles (ordered by registration, retired ones included).

**S05 `GET /setup/people?page&pageSize`**: perm `people.view`. 200 `Page<PersonDto>`. Visible people = memberships that have a role link, narrowed for a scoped caller by `PeopleVisibility.People` (the caller themself; for AllCompanies everyone; anyone whose company scope meets the caller's companies or the companies of the caller's vehicles; anyone whose vehicle scope holds a vehicle the caller can see).
Order: `lastName`, `firstName`, then user id. `companyIds` and `vehicleIds` are filtered to what the caller can reach; `otherCompanies` and `otherVehicles` count the hidden ones.
**S06 `GET /setup/people/{id}`**: perm `people.view`. 200 `PersonDto`; 404 when the person is not visible.

**S07 `POST /setup/people`** and **S08 `PUT /setup/people/{id}`**: perm `people.manage`. Body `SavePerson` (section 3.3). Checks, in order (all 400 `Invalid setup change` with the message as `detail` unless marked 403/409):
1. `firstName`, `lastName` trimmed 1..100: `First and last name are required.`
2. `email` trimmed, <= 320, valid address: `A valid email is required.`
3. `phoneNumber` normalises to `+254...`: `A valid mobile number is required.`
4. `scopeMode` is `all`, `companies` or `vehicles`: `Choose a data scope.`
5. `companies` needs >= 1 `companyIds`, `vehicles` needs >= 1 `vehicleIds`: `Choose at least one item in the data scope.`
6. ids distinct: `Data scope items must be distinct.`
7. `permissions` non-empty and distinct (ordinal) and `approvalLimit` not negative: `Permissions and approval limit are invalid.`
8. `role` matches (case-insensitively) one of the four catalog role names: `Unknown role.`
9. (PUT) person must be visible: 404. (PUT) `version` must be present: `Reload this person before saving.` (400); `version` must equal the membership `version`: **409** Problem `Settings changed. Reload before saving.`
10. Hidden-scope preservation and scope validation: `all` needs a caller with AllCompanies (403 `Only someone who can see every company can give access to every company.`); chosen companies/vehicles must exist (400 `Choose companies in your organization.` / `Choose vehicles in your organization.`) and be within the caller's own scope (403 `You can only give access to companies in your own data scope.` / `You can only give access to vehicles in your own data scope.`), except ones the person already holds outside the caller's view, which are kept; a scoped caller cannot switch the kind of scope of a person who holds hidden scope (403 `This person's data scope includes companies or vehicles outside your own, so you cannot change which kind of scope they have. Their companies and vehicles outside your view are kept as they are.`).
11. (PUT) editing yourself: 400 `You cannot change your own access here.`
12. Giving the Owner role needs an Owner caller: 403 `Only an Owner can give the Owner role.` Editing an Owner needs an Owner caller: 403 `Only an Owner can change, remove or sign out an Owner.`
13. Permission keys must all exist in the catalog (after dependency expansion): `Unknown permission.`
14. Access rules (non-Owner callers): a role may only be granted if the caller holds every default permission of that role (403 `You can only grant roles whose permissions you hold.`); a deviation from the role's defaults or an approval-limit change needs `access.manage` (403 `Changing single permissions or an approval limit needs "Change single permissions and approval limits for a person".`) and only permissions the caller holds may be granted (403 `You can only grant permissions you hold.`).
15. (PUT) changing email or phone: Owner OK; otherwise the caller must see the person's full scope (403 `Only an Owner, or someone who can see this person's full data scope, can change their email or mobile number.`) and hold everything the person holds (403 `Only an Owner, or someone who holds everything this person holds, can change their email or mobile number.`).
16. Phone or email already used by another user: `That mobile number or email already belongs to someone.`
- Success 200 `{id}` (the user id). Create adds a User (Active, no PIN: they set one via A04-A06), an active membership (`version` 1), the role link, scope rows and permission overrides = differences from the role defaults. Update replaces role, scope and overrides; `membership.version` +1 when anything changed.
  Side effects on update: name, role or single-permission change bumps the person's `SecurityVersion` (their access token is refused once, they renew via refresh and are not signed out); an email or phone change bumps it AND revokes all their trusted devices and refresh tokens (next sign-in needs an email code to the new address; the PIN is kept).
- Change log (section `people`): create `Added {First Last} as {Role}`; update `Changed {name, sign-in details, role, single permissions, data scope, approval limit} for {First Last}` (joined as `a`, `a and b`, `a, b and c`).
  Snapshots (`before`/`after`) are JSON text with PascalCase keys (section 3.9).

**S09 `POST /setup/people/{id}/activate` and S10 `POST /setup/people/{id}/deactivate`**: perm `people.manage`. Body `PersonLifecycleRequest?` = `{ version?: long, reason?: string }`; the body is **optional**
(null body and no content type are accepted, `Api/SetupEndpoints.cs:88-92`).
- Order: self => 400 `You cannot deactivate your own access.` (both routes use this text); person not visible => 404; target is an Owner and caller is not => 403 `Only an Owner can change, remove or sign out an Owner.`
- If the person is already in the requested state => 200 `{id}` with no change and no version needed (repeating a completed transition is harmless).
- Otherwise `version` must be present and equal the membership `version`, else **409** Problem title `Settings changed. Reload before saving.` (this is also what a body-less call gets).
- Deactivate also needs a typed `reason` (trimmed 1-500) else 400 `A reason of 1–500 characters is required.`; activate ignores `reason`.
- Effects. Deactivate: membership inactive (`version` +1), user `Status = Removed` (`SecurityVersion` +1), all trusted devices and refresh tokens revoked; change-log `Removed access for {First Last}. Reason: {typed}.`; audit `person.deactivated`.
  Activate: membership active (`version` +1), user `Status = Active`; change-log `Restored access for {First Last}`; audit `person.activated`. A person who was removed keeps their PIN, but all devices were revoked, so they must verify the device by email code again.
- 200 `{id}`.
**S11 `POST /setup/people/{id}/sign-out`**: perm `people.manage`. No body. Self => 400 `Use sign out for your own session.`; not visible => 404; Owner rule as above => 403.
Revokes all the person's trusted devices and refresh tokens; change-log `Signed {First Last} out of every device` (before and after snapshots equal). 200 `{id}`. (Their access tokens die at once because the device rows are revoked.)

### 2.4 Companies endpoints in detail (S12-S16)

**S12 `GET /setup/companies?page&pageSize`**: perm `companies.manage`. 200 `Page<CompanyDto>`, visible companies ordered by `name` then `id`. `vehicleCount` = the caller's visible vehicles of that company that are active today (joined by today, not left). `active` = `archivedOn` is null or after today.
**S13 `POST /setup/companies`**: perm `companies.manage` AND the caller must have AllCompanies (else 403, no detail). Body `{ name: string, reason?: string }`.
- Errors: bad typed reason (400); `name` trimmed 1..160 (400 `Name must contain 1-160 characters.`); another company with the same name ignoring case (400 `Another company already has this name.`).
- Change log `companies`: `Added company {name}`. 200 `{id}`.
**S14 `PUT /setup/companies/{id}`**: perm `companies.manage`. Body `{ name, reason? }`. 404 if not visible. Archived (as of today) => 400 `Archived companies cannot be renamed. Restore it first.` Same name rules as create (the company itself is excluded from the duplicate test). Unchanged name => 200 `{id}`, no log. Change log: `Renamed company {old} to {new}`.
**S15 `POST /setup/companies/{id}/archive`** and **S16 `POST /setup/companies/{id}/restore`**: perm `companies.manage`. Body `CompanyLifecycleRequest` = `{ reason?: string }` (the body itself is required; the web sends `{}`).
- Archive: 404 if not visible. If not yet archived and the company still has any vehicle that is not retired as of today (`LeftOn` null or after today, including vehicles that have not yet joined) => 400 `Retire every vehicle in this company before archiving it.` Archiving stores `archivedOn = today`; archiving again on the same day is a no-op; on another day => 400 `The company is already archived.` Change log `Archived company {name}`.
- Restore: clears `archivedOn` (also cancels an archive dated after the current business date); no-op when not archived. Change log `Restored company {name}`. 200 `{id}` in all cases.

### 2.5 Vehicles endpoints in detail (S17-S23)

**S17 `GET /setup/vehicles?page&pageSize&companyId`**: member, then needs `vehicles.manage` OR `invest.view` (else 403, no detail). Page validation comes after that check. 200 `Page<VehicleDto>`: the caller's visible vehicles ordered by `registration`; with `companyId`, only that company's, counted and paged as the matches only (an unknown or unseen company gives an empty page; an unparsable id is 400) (`Api/SetupEndpoints.cs:107-108`, `Infrastructure/Setup/SetupRepository.cs:79-83` in 9276c51; `tests/api/ListFilterTests.cs:16-33`).
For a caller who lacks `vehicles.manage` (investment viewers) `weeklyTarget` is `null`, `targets` is `[]` and `recurringItems` is `null`.
`weeklyTarget` = the target in force today (latest `effectiveFrom` not after today, ties by highest `revision`) for a vehicle active today, otherwise `0`. `targets` ascend by `revision`. `away` ascends by `leftOn`.
`recurringItems` = number of distinct scheduled items currently posting to the vehicle (current version allocates to it, `end` not before today, not stopped on or before today) for vehicles active today, `0` otherwise.
**S18 `POST /setup/vehicles`** and **S19 `PUT /setup/vehicles/{id}`**: perm `vehicles.manage`. Body `SaveVehicle` = `{ companyId: guid, registration: string, joinedOn: date, weeklyTarget: number, reason?: string }`. Checks in order:
1. typed `reason` (400 if non-blank and over 500 after trimming).
2. `registration`: trim, upper-case, remove spaces, must match `^K[A-Z]{2}[0-9]{3}[A-Z]$` (400 `Use the registration format KDA 482M.`). Stored and returned as three letters, a space, the rest (`KDA 482M`).
3. `weeklyTarget`: > 0, at most 2 decimals, <= 999999999999.99 (400 `Amount must be positive with at most two decimal places.`).
4. `joinedOn` not the default date and not after today (400 `A vehicle cannot join after the business date.`).
5. `companyId` must be a visible company (404 `Record not found in your scope.`) that is not archived as of today (400 `Choose an active PSV company.`).
6. Create: the caller needs AllCompanies or the company in their `companyIds` (403, no detail). Update: the vehicle must be visible (404).
7. Update: vehicle already retired (400 `Retired vehicles must be restored before they can be edited.`); `registration` differs after normalising (400 `Registration cannot change after a vehicle is added.`).
8. Create: registration already exists in the organization (400 `This registration already exists.`).
9. Update: moving `joinedOn` LATER than the first day that has a revenue record (400 `{reg} has revenue recorded on {yyyy-MM-dd}. A vehicle cannot join the fleet after a day it has a record for.`).
- Create makes the vehicle with a first target (`effectiveFrom = joinedOn`, `revision` 1). Update (`FleetVehicle.Update`) may change company and `joinedOn`, and appends a new target revision (effective today, or on `joinedOn` if that is later) when `weeklyTarget` differs from the target in force; moving `joinedOn` earlier also appends a target at the old join date's amount when needed so no day is left without a target. Nothing changed => 200 `{id}`, no log.
- Change log `vehicles`: create `Added vehicle {reg} to {company} with a weekly target of {CUR} {amount} from {yyyy-MM-dd}`; update joins (with `; `) any of `moved {reg} to {company}`, `changed when {reg} joined the fleet to {yyyy-MM-dd}`, `changed the weekly target of {reg} to {CUR} {amount} from {yyyy-MM-dd}`, falling back to `changed vehicle {reg}`, first letter upper-cased. `{CUR}` = organization currency code (default `KES`); `{amount}` = `#,##0` when whole, else `#,##0.00`, invariant culture.
- 200 `{id}`.
**S20 `GET /setup/vehicles/company-options`**: perm `vehicles.manage`. 200 `[{id,name}]` of visible, non-archived companies ordered by name then id.
**S21 `POST /setup/vehicles/{id}/retire`**: perm `vehicles.manage`. Body `VehicleLifecycleRequest` = `{ leftOn: date, reason?: string }`. 404 if not visible. Refused (400) when revenue exists on or after `leftOn`: `{reg} has revenue recorded on {last day}. A vehicle cannot leave the fleet on or before a day it has a record for.`
Domain rules (400): `leftOn` default, after today, or before `joinedOn` => `A vehicle's leave date must be from its join date through the business date.`; before the last return date => `A vehicle's leave date must be on or after the day it last returned to the fleet.`; already retired on a different date => `The vehicle is already retired.`; retired on the same date => no-op. Log `Vehicle {reg} left the fleet on {yyyy-MM-dd}`. 200 `{id}`.
**S22 `POST /setup/vehicles/{id}/restore`**: perm `vehicles.manage`. Body `VehicleRestoreRequest` = `{ reason?: string, returnedOn?: date }` (defaults to today). 404 if not visible or its company is not visible; company archived => 400 `Restore the vehicle's archived company first.`
Not retired => no-op 200. `returnedOn` default, before `leftOn` or after today => 400 `A vehicle's return date must be from the day it left through the business date.` When `returnedOn` is after `leftOn` an away period `[leftOn, returnedOn)` is recorded (those days are neither expected nor missing).
Log `Vehicle {reg} returned to the fleet on {yyyy-MM-dd}` plus `; it was away from {leftOn} to {returnedOn minus 1 day}` when a stretch was recorded. 200 `{id}`.
**S23 `GET /setup/vehicles/{id}/report`**: perm `vehicles.manage`. Query `period` (`week` or `month`) OR both `from` and `through` (`yyyy-MM-dd`). With `period`: `week` => from the first day of the current organization week (first day = `localization.firstDayOfWeek`, default 1 = Monday) through today; `month` => first of the month through today; any other period text => 400 `Period must be week or month.`
Without `period`, missing `from` or `through` => 400 `Choose a period, or a from and through date.` Range: `through < from`, more than 366 days between them, or `through` after today => 400 `Report range must be at most 367 days and cannot include the future.` The vehicle must be visible (404). 200 `VehicleReport` (section 3.5).

### 2.6 Scheduled expenses and savings ("recurring") endpoints in detail (S24-S29)

**S24 `GET /setup/recurring?page&pageSize&kind&companyId&status`**: perm `commitments.view`. 200 `Page<RecurringDto>`. A caller with AllCompanies sees every item; otherwise an item is listed when any of its versions allocates to a visible vehicle.
Filters (`Api/SetupEndpoints.cs:123-124`, `Application/Setup/SetupContracts.cs:9-29` `RecurringFilter.Of`, `Infrastructure/Setup/SetupRepository.cs:175-203` in 9276c51; `tests/api/ListFilterTests.cs:69-102`), read in the endpoint before the use case runs, so before the membership, permission and page checks: `kind` `cost` or `savings` (the current version's kind), else 400 `Kind must be cost or savings.`; `status` `running` or `stopped`, else 400 `Status must be running or stopped.`; null, empty or `all` keeps every item, and both are case-sensitive; `companyId` keeps items whose current version shares to a vehicle of that company the caller sees. an item runs while it has not stopped (`stoppedFrom` null or after the business date), its current version has not ended (`end` null or on or after it) and that version shares to a vehicle the caller sees that is in the fleet that day (joined on or before it, not left); `stopped` is every other item.
Order: running items first, then current (latest revision) name as the database collates it, then item id. Each row is the item's latest version. The caller sees only the allocations on vehicles they can see (`partial: true` when the item also posts to vehicles outside their scope); `amount` = sum of the listed allocations (retired vehicles included), `activeAmount` = the part on vehicles still in the fleet. `bucket` = reported bucket of a cost (a cost saved without a bucket reports `2`, recurring charges), `null` for savings.
**S25 `GET /setup/recurring/vehicle-options`**: perm `commitments.manage`. 200 `VehicleOption[]` ordered by registration: visible vehicles active today whose company is not archived; `active` is always `true`.

**S26 `POST /setup/recurring`** and **S27 `PUT /setup/recurring/{id}`**: perm `commitments.manage`. Body `SaveRecurring` (section 3.5): `{ name?, kind, amount, frequency, day?, lastDay, start, end?, allocations: [{vehicleId, amount}], reason?, expenseItemId?, note?, month? }`.
A body from the old web that still carries `category` is read and the field ignored. Order of checks (400 `Invalid setup change` unless marked):
1. typed `reason`.
2. If `kind` is not `1` (Cost): `expenseItemId` must be null (`Savings must not have an expense item.`); the name is the typed `name`. If `kind` is `1`: `expenseItemId` must name an item that is in use today in a category in use today (`Choose an expense item that is in use.`); the saved name is then the expense item's name and the bucket is that category's bucket (the typed `name` is ignored for costs).
3. Schedule: `frequency` 2 (weekly) needs `day` 0..6 (Sunday = 0) and `lastDay` false; 3 (monthly) needs `day` 1..28 with `lastDay` false, or `lastDay` true with `day` null; 4 (yearly) needs `month` 1..12 plus the monthly day rule; `month` only for yearly; 1 (daily) allows no day. Message: `Choose a weekday (0–6), a month day (1–28 / last), or for yearly a month (1–12) and a day.`
4. (PUT) item must be visible: 404.
5. Definition checks: name 1..160 trimmed (`Name must contain 1-160 characters.`); `amount` money rule; `kind` 1 or 2 (`Costs need an expense item; savings must not have one.`); `note` at most 200 chars (`A note can have at most 200 characters.`); `end` not before `start` (`End date must be on or after start date.`); 1..500 allocations with distinct non-empty vehicle ids (`Choose 1-500 distinct vehicles.`); every allocation amount a valid money value; allocations sum exactly equal `amount` (`Vehicle shares must equal the total exactly.`).
6. New-save rules: frequency 1 refused (`Daily schedules are no longer offered. Choose weekly, monthly or yearly.`); a saving must be weekly or monthly (`Savings are set aside weekly or monthly.`); a cost needs an item (`Choose the expense item this cost is for.`); `start` required (`Start date is required.`); a `start` earlier than the first day of the current business month is refused unless it equals the item's current version start (`A schedule can start no earlier than the first of the current month.`).
7. Every allocation's vehicle must be visible, and its company visible (404 otherwise); a vehicle or company that is not active today is refused (`New recurring shares must use active vehicles and companies.`) unless the vehicle is already on the item's current version.
8. (PUT) every vehicle on the item's current version must be visible, else 403 (no detail). If nothing differs from the current version => 200 `{id}`, no log.
9. (PUT) `Stopped items cannot be edited.` when `stoppedFrom` is on or before today; `An already running item's start date cannot change.` when the current version's start is before today and `start` differs.
- A revision appends a new immutable version (`revision` +1). Its `effectiveFrom` is today for a running item (or one whose new `start` is today or later), else the (backdated) `start`. Versions and allocations are append-only; items are never deleted.
- Change log `recurring`: create `Added scheduled saving {name}` or `Added scheduled expense {name}`; update `Changed the {type, expense item or name, bucket, amount, schedule, start date, end date, vehicles, note} of {name}` (`bucket` only when the expense item is unchanged, `RecurringUseCases.Changed`) (joined `a`, `a and b`, `a, b and c`; `Changed {name}` if none matched). 200 `{id}` (the item id).
**S28 `POST /setup/recurring/{id}/stop`**: perm `commitments.manage`. Body `StopRecurring` = `{ confirmed: bool, reason: string }` (required body). Order: `reason` trimmed 1..500 (400 `A reason of 1–500 characters is required.`); `confirmed` must be true (400 `Confirm stopping this item. Past postings are retained; no posting occurs from today.`); item visible (404); every vehicle on the current version visible (403).
Stop sets `stoppedFrom = today`. Already stopped on another date: later than today => 400 `This item is already due to stop on a later date. Cancel that stop first.`; on or before today => 400 `The item is already stopped.`; same day => no-op. Log `Stopped {name} from {yyyy-MM-dd}` plus the typed reason. 200 `{id}`.
**S29 `POST /setup/recurring/{id}/restore`**: perm `commitments.manage`. No body is read. 404 not visible; 403 when a vehicle on the current version is not visible; not stopped => no-op; stop already in effect (`stoppedFrom` on or before today) => 400 `This item has already stopped. Add a new scheduled item instead.`; otherwise clears `stoppedFrom`, log `Cancelled the stop of {name}`. 200 `{id}`. (Its name in the code is `CancelStop`; the route is `restore`.)

### 2.7 Change log endpoint in detail (S30)

**S30 `GET /setup/history`**: perm `audit.view`.
- Query: `page` (default 1), `pageSize` (default 25; both validated as in 2.0), `section` (string, blank = all), `from` and `to` (`yyyy-MM-dd`, both days included, read in the ORGANIZATION time zone), `text` (trimmed; blank = none), and **(uncommitted)** `before` (`long`, must be >= 1) and `includeTotal` (`bool`, default `true`).
- Errors (400 `Invalid setup change`): `The first date cannot be after the last date.`; `Search for 200 characters or fewer.`; **(uncommitted)** `Before must be a change log version.`
- Filters: `section` equals the stored section key; `from`: `occurredAt >=` local midnight of `from` in the organization zone; `to`: `occurredAt <` local midnight of the day after `to`; `text`: case-insensitive "contains" (SQL `LIKE %text%` with `[`, `%`, `_` escaped) on `reason` OR on the actor's `First Last` name.
- Order: `version` descending (newest first). Without `before`: offset paging by `page`. **(uncommitted)** With `before=N`: only rows with `version < N`, `page` offset ignored (cursor mode, stable while new rows arrive).
- Response, committed HEAD: `{ items: HistoryEntry[], pageNumber, pageSize, total }`. **(uncommitted)** superset `HistoryPage`: `{ items, pageNumber, pageSize, total (int, or null only when includeTotal=false), hasMore: bool, nextBefore: long or null }`; `nextBefore` = the last returned item's `version` when `hasMore`, else `null`. (`total` is cached per organization, settings version, caller scope and filter for 5 minutes; it is exact because every change-log row has a new settings version.)
- Visibility per caller (this is part of the contract, because it decides what a scoped person can learn):
  - `people` entries are only shown to callers with `people.view`, and for scoped callers only for people the caller can see; their `before` and `after` snapshots have `CompanyIds` and `VehicleIds` redacted to what the caller can reach.
  - Callers with AllCompanies see every other section. Scoped callers see: `companies` for visible companies; `vehicles`, `investment`, `revenue` for visible vehicles (**uncommitted:** matched through the new `OrganizationSettingsVersion.vehicleId` column; HEAD matched `vehicles`/`investment` by entity id and `revenue` through the record's vehicle); `pettycash` rows (new section, see `inventory-petty-cash.md`) for visible vehicles in the same way (`VehicleId` not null and visible); `recurring` only for items whose every allocation is on a visible vehicle; `expenses` always; the organization-settings sections (`organization`, `businessDate`, `localization`, `branding`, `securityPolicy`, `logo`) NOT at all.
- `HistoryEntry` = `{ version: long, section: string, entityId: guid, reason: string, occurredAt: instant, actorId: guid, actorName: string ("First Last", or "" when the actor has no membership), before: string or null, after: string or null }`. `before` and `after` are JSON TEXT (a string containing JSON, PascalCase keys, `"null"` or null for a create/remove), see section 3.9. Sections used: `companies`, `vehicles`, `investment`, `expenses`, `recurring`, `people`, `revenue`, `pettycash` **(uncommitted, new)**, `organization`, `businessDate`, `localization`, `branding`, `securityPolicy`, `logo`. `HistoryEntry` has no `vehicleId` field (verified in `Application/Setup/SetupContracts.cs:17-19`); the `VehicleId` column is internal to visibility. The paging mechanics were re-verified against `Infrastructure/Setup/SetupRepository.cs:291-336`: `before` seeks `Version < before` and ignores the `page` offset, `pageNumber` in the reply still echoes the requested `page`, `hasMore` comes from fetching `pageSize + 1` rows, and `total` is `null` only when `includeTotal=false`.

### 2.8 Expense catalog endpoints in detail (S31-S40)

All of these are organization-wide (no data scope). Reasons are always automatic (no typed reason is read).
**S31 `GET /setup/expense-categories?page&pageSize`**: member plus any of [`expenses.view`, `expenses.setup`, `commitments.view`] (else 403). 200 `Page<ExpenseCategoryDto>`: categories ordered by name then id; each with its `items` ordered by name then id. `active` = `stoppedOn` is null or after today. The web asks with `pageSize=100`.
**S32 `GET /setup/expense-items/options`**: any of [`expenses.view`, `expenses.setup`, `commitments.view`, `commitments.manage`]. 200 `ExpenseItemOption[]`: items in use today whose category is in use today, ordered by category name, item name, item id.
**S33 `POST /setup/expense-categories`**: perm `expenses.setup`. Body `{ name?: string, bucket: int }`. `name` trimmed 1..100 (400 `Name must contain 1-100 characters.`); `bucket` must be 1, 2 or 3 (400 `Choose repairs and maintenance, recurring charges or loan repayments.`); duplicate name ignoring case (400 `That category already exists.`). Log (section `expenses`): `Added expense category {name}`. 200 `{id}`.
**S34 `PUT /setup/expense-categories/{id}`**: same body/rules; 404 if unknown; unchanged => 200 no log. Log: `Renamed expense category {old} to {new}` or `Changed {name} to count as {bucket label lower-cased}` or `Renamed expense category {old} to {new}, counted as {label}`. Labels: `repairs and maintenance`, `recurring charges`, `loan repayments`.
**S35 `POST /setup/expense-categories/{id}/stop`** and **S36 `.../restore`**: no body read. Stop sets `stoppedOn = today`; already stopped on another day => 400 `It is already turned off. Turn it on first to cancel that.`; same day => no-op. Restore clears it. Log `Turned off expense category {name}` / `Turned on expense category {name}`. 404 if unknown. 200 `{id}`.
**S37 `POST /setup/expense-categories/{id}/items`**: body `{ name?: string }`; 404 if the category is unknown; name 1..100 (`Name must contain 1-100 characters.`); duplicate within the category ignoring case (400 `That item already exists in this category.`). Log `Added expense item {name} under {category}`. 200 `{id}` (the new item id). A stopped category still accepts new items.
**S38 `PUT /setup/expense-items/{id}`**: body `{ name }`; 404 unknown; same rules; log `Renamed expense item {old} to {new}`; 200 `{id}`.
**S39 `POST /setup/expense-items/{id}/stop`** and **S40 `.../restore`**: as for categories; log `Turned off expense item {name}` / `Turned on expense item {name}`.

### 2.9 Investment endpoints in detail (S41-S44)

Investment is never counted as money out. A vehicle outside the caller's scope (and an entry on such a vehicle) is a 404.
**S41 `GET /setup/vehicles/{id}/investment`**: perm `invest.view`. 200 `InvestmentDto` (section 3.5). `returned` = the vehicle's net contribution (money in less money out, section 3.5 report maths) from `joinedOn` through today (may be negative). `percentPaidOff` = `null` when `totalInvested` is 0, else `round(returned / totalInvested * 100)` half away from zero, as a number.
**S42 `POST /setup/vehicles/{id}/investment`**: perm `invest.manage`. Body `{ date: date, description?: string, amount: number }`. 400s: `date` default or after today => `An investment date is required and cannot be after the business date.`; `description` trimmed 1..160 => `Say what it was, in 1-160 characters.`; `amount` => `Amount must be positive with at most two decimal places.` Records `recordedBy` (the caller) and `recordedAt` (UTC now). Log (section `investment`, entity id = the VEHICLE id): `Recorded investment {description} on {reg}`. 200 `{id}` (the entry id).
**S43 `PUT /setup/investment/{id}`**: same body/rules; 404 for an unknown entry or one on an invisible vehicle; unchanged => 200 no log; log `Changed investment {description} on {reg}`. 200 `{id}`.
**S44 `DELETE /setup/investment/{id}`**: the only HARD delete in the API. 404 as above; log `Removed investment {description} on {reg}` (after = null). 200 `{id}`.

### 2.10 Revenue endpoints in detail (R01-R03)

All three live in the group `/setup/revenue` (tag `Revenue`) with the extra endpoint filter described in 1.8(B): `409` with `current` (plus `vehicleId` when a day save of several vehicles conflicts, `RevenueEndpoints.cs:26-30`) and `409` "changed by another save". The `400` with `earliestMissing` was removed by 9276c51 (drift log entry 24). The same group also holds `GET /day`, `PUT /day/{date}` and `GET /export` (9276c51 and uncommitted; drift register rows 3 and 4 of `docs/prompts/README.md`, built by prompt 08b).
**R01 `GET /setup/revenue?weekStart&companyId&vehicleId`**: perm `revenue.view`. All three query values optional (`weekStart` `yyyy-MM-dd`, the ids GUIDs).
- The week: `firstDay` = `localization.firstDayOfWeek` (0 = Sunday .. 6; default 1). `currentWeekStart` = first day of the week containing today. `weekStart` = first day of the week that CONTAINS the supplied date (so any date names its week; absent => the current week). Refused when that start is after `currentWeekStart` or earlier than `currentWeekStart` minus 3650 days: 400 `Choose a week from the last ten years through the current week.` `weekThrough` = `weekStart` + 6 days.
- Vehicles: the caller's visible vehicles ordered by registration (then id), optionally filtered by `companyId`. Without `vehicleId` only vehicles that are in the fleet on some day of the week are listed (`joinedOn <= weekThrough` and (`leftOn` null or after `weekStart`)); with `vehicleId` exactly that vehicle is returned for ANY week (all cells `none` outside its time in the fleet). A `vehicleId` the caller cannot see (or that does not exist) is **404** (`Record not found in your scope.`).
- `companies`: visible companies (ordered by name then id) that are not archived as of today, or archived but with a visible vehicle running in that week.
- 200 `RevenueWeekDto` (section 3.6): per vehicle 7 `days` (one `RevenueCellDto` per date, `weekStart` first), `earliestMissing`, per-vehicle and grand totals, `percent` (`null` when expected is 0), and since phase 5 the paging fields, `dayTotals` and `firstGap` (next bullets).
- **Paging** (`Application/RevenueContracts.cs:105-121`, `Application/RevenueUseCases.cs:13-16`, `Api/RevenueEndpoints.cs:40-44`; tests `RevenueWeekPagingTests.cs:53-230`): optional query `page` and `pageSize` (ints). Neither given = the unpaged legacy listing: page 1 of up to **500** vehicles (`RevenueWeekPage.LegacyLimit`), response `pageNumber` 1, `pageSize` 500, and `truncated` true only when the grid holds more than 500 vehicles. Either one given = paging, the other defaulted (`page` 1, `pageSize` 100 = `RevenueWeekPage.DefaultSize`); both are validated by `SetupPagination.Validate`: page 1..100000 and pageSize 1..100, else **400** Problem `Invalid setup change` with `detail` `Page must be 1–100000 and page size 1–100.` (EN DASH). A paged response echoes the request in `pageNumber`/`pageSize`, has `truncated` false, and a page past the end is 200 with empty `vehicles`. Vehicles are ordered by `registration`, then `id`, and the page is a slice of that order. `totalVehicles` is the size of the whole filtered, scoped grid. **A request with `vehicleId` is never paged and its `page`/`pageSize` are not even validated** (`page=0&pageSize=1000` is 200): `totalVehicles` 1, `pageNumber` 1, `pageSize` 500 (a vehicle outside the caller's scope is still 404).
- **Whole-grid figures**: `totalAmount`, `totalExpected`, `percent`, `dayTotals` and `firstGap` always cover EVERY vehicle of the filtered, scoped grid, not just the listed page, so every page of one week carries identical values for them (and for `weekStart`, `weekThrough`, `currentWeekStart`, `businessDate`, `companies`). Totals are summed unrounded and rounded once (11,500 of 20,000 is 57.5 shown as 58). `dayTotals` = exactly 7 items `{ date, amount, expected }` in week order: `amount` sums the amounts recorded on that day (zero for days after today, which show no amounts) and `expected` sums each vehicle's `target/7` over the days that count (active that day and (before today or recorded)), both rounded to 2 decimals. `firstGap` = `{ vehicleId, date }` or `null`: the earliest day that still needs capture over the whole grid (a vehicle's earliest missing day, or today while today has no record), the first vehicle in grid order on a tie; it is NOT permission-gated beyond `revenue.view` and the caller's data scope (it is present for callers who cannot capture).
- Money maths: per day `expected = round(targetOn(date) / 7, 2)` (banker's rounding) but the week totals add the UNROUNDED daily expectation and round once; a day counts towards `totalExpected` only when the vehicle is active that day AND (the day is before today OR a record exists); `totalAmount` sums recorded amounts on those counted days; `percent = round(totalAmount / totalExpected * 100)` half away from zero, clamped to int range. All totals rounded to 2 decimals.
**R02 `GET /setup/revenue/dashboard?period&companyId`**: member plus any of [`dash.capture`, `dash.revenue`, `dash.gaps`, `dash.edits`]. `period` = `today`, `week` (default) or `month`, anything else 400 `Period must be today, week or month.`; `companyId` optional narrowing (a company outside the caller's reach simply matches nothing).
- 200 `RevenueDashboardDto`: `period`, `from`, `through` (= business date), `businessDate`, `revenue`, `expected`, `percent`, `capturedToday`, `vehiclesToday`, `missingDays`, `missingVehicles`, `editedRecords`. The shape is unchanged by phases 4 to 6 (`Application/RevenueContracts.cs:123-135`).
- **Computation and cache (phase 5, behaviour unchanged, cost changed)**: the figures are summed by the database (one grouped query that returns one row per vehicle, over its active days, `Infrastructure/RevenueRepository.cs:88-156`), not by loading every record. They are cached per process by `RevenueDashboardCache` (`Infrastructure/RevenueDashboardCache.cs:16-86`) under the key (organization id, organization `SettingsVersion` read before any data, business date, period, company filter, scope hash) for 60 seconds, UNMASKED; `Visible` (the per-card `null` masking above) is applied per request after the cache (`Application/RevenueUseCases.cs:18-41`), so two viewers who share a scope share one entry and see only their own cards. Scope hash: `all` for an all-companies viewer, else a SHA-256 of the sorted company and vehicle ids. Concurrent requests for one key share one computation; a failed or cancelled computation is not kept. Every write that moves a figure's inputs adds a change-log row and so moves `SettingsVersion`, which is what invalidates an entry; there is no explicit invalidation. Cached entry count is capped at 10 000. Behaviour is pinned by `RevenueDashboardCacheTests.cs` (a hit issues fewer commands than a miss and returns identical JSON; saving revenue, retiring a vehicle, moving the business date, changing the first day of the week and moving a vehicle each give fresh figures).
- Each figure group is `null` unless the caller holds that card's own permission: `revenue`, `expected`, `percent` need `dash.revenue`; `capturedToday`, `vehiclesToday` need `dash.capture`; `missingDays`, `missingVehicles` need `dash.gaps`; `editedRecords` needs `dash.edits`. `period`, `from`, `through`, `businessDate` are always present.
- Maths: `from` = today (`today`), first day of the current organization week (`week`), first of the month (`month`); `through` = today. For each visible vehicle in the fleet in `[from, through]` and each day it is active (away days excluded): `expected` += target/7 and `revenue` += amount only for days before today or with a record; a day before today with no record counts as a missing day (and its vehicle once in `missingVehicles`); today with a record counts in `capturedToday`; any record with `correctedAfterDate` counts in `editedRecords`; `vehiclesToday` = vehicles active today. `revenue` and `expected` rounded to 2 decimals; `percent` as in R01.

**R03 `PUT /setup/revenue/{vehicleId}/{date}`**: member plus any of [`revenue.capture`, `revenue.correct`] (else 403), then the per-case rules below. Route: `vehicleId` GUID (constraint), `date` `yyyy-MM-dd`. Body `SaveRevenue`:
`{ "amount": number or null, "reason": string or null, "note": string or null, "version": integer or null }`. This is the capture AND offline-replay endpoint (section 3.6). There is **no idempotency-key header**; idempotency is by value comparison (step 5).
Steps in order (the first failing step answers):
1. Entry validation (400 `Invalid setup change`): `reason` trimmed; `""`/null = none; accepted spellings `Garage`, `Arrest`, `No Crew`, `NoCrew`, `Other` (case-sensitive), anything else `Choose a valid no-earnings reason.`
   With `amount` set: it must satisfy the money rule (`Amount must be positive with at most two decimal places.`) and `reason` must be empty and `note` blank (`Revenue amount cannot have a no-earnings reason.`).
   With `amount` null: a reason is required (`Enter revenue or choose a no-earnings reason.`); `Other` needs a non-blank note (`Explain what happened when choosing Other.`); note (trimmed) at most 80 chars (`The no-earnings note must be at most 80 characters.`); a note with any reason but `Other` is refused (`Only Other may have a no-earnings note.`).
2. The vehicle must be visible: otherwise **404**. 3. The day's existing record (if any) is loaded.
4. **Identical replay**: when a record exists and its `amount`, `reason` and trimmed `note` (blank = none) equal the request's, answer **200 `{id, version}` of the existing record immediately**, changing nothing, whatever `version` was sent, whatever the date is, and whatever permissions apply from here on. This is why a phone draining its queue late (even after the day closed) always succeeds.
5. `date` default or after today => 400 `Revenue cannot be recorded for a future date.`
6. Vehicle not active that day (before it joined, on or after it left, or inside an away period): 400 `The vehicle was away from the fleet on this day, so it is not a day revenue is recorded for.` (away) or `Revenue can only be recorded while the vehicle is active.`
7. Permission cases (403 Problem with a custom `detail` = `{action} needs the permission "{label}".`):
   a reason is being recorded without `revenue.no_earnings` => `Recording a no-earnings reason needs the permission "Record a no earnings reason".`;
   no record yet and no `revenue.capture` => `Recording a day that has no record yet needs the permission "Capture revenue".`;
   a record exists, the date is before today and no `revenue.correct` => `Changing a past day needs the permission "Correct revenue after the day".`
   (Authorization deliberately precedes disclosure: a 403 never carries `current`.)
8. A record exists and `version` is not equal to its `version` (a missing/null version counts as not equal) => **409** (1.8(B)) with `current` = the saved cell (`RevenueCellDto`).
9. (Removed by 9276c51, `Application/RevenueUseCases.cs:130-131`: until then a new record was refused with **400** and `earliestMissing` while an earlier active day had no record. Days are now captured in any order; the week still reports each vehicle's `earliestMissing`.)
10. Persist: new `RevenueRecord` (`version` 1, `capturedAt`/`updatedAt` = now UTC, `capturedBy`/`updatedBy` = caller) or replace the entry (`version` +1; `correctedAfterDate` becomes true when `date` is before today). Concurrency token = `version`: a racing save fails commit with **409** `This day was changed by another save.` (no `current`); two first captures racing on the unique (organization, vehicle, date) key fail as **409** `A conflicting record exists. Reload before saving.` (no `current`; clients re-read the day).
11. Change log (section `revenue`, entity = the record id, vehicle id stored for visibility): `Recorded revenue for {reg} on {d MMM yyyy}` (new, with amount), `Recorded no revenue for {reg} on {d MMM yyyy}: {reason label}` (new, with a reason; label `No Crew` has a space), `Corrected revenue for {reg} on {d MMM yyyy}` (existing record, `date` before today), `Updated revenue for {reg} on {d MMM yyyy}` (existing, today). `d MMM yyyy` = invariant culture, day without zero padding (`8 Oct 2026`).
- 200 `{ "id": guid, "version": long }`, exactly these two properties in this order (test `RevenueCaptureTests.cs:120`).

### 2.11 Organization, appearance and preferences endpoints in detail (O01-O07)

Group `/setup` (tag `Organization`), `RequireAuthorization()` + `WithSetupErrors()`. Since phase 5 the endpoints in `Api/OrganizationEndpoints.cs:17-51` are transport only (they take no `AuthDb`, clock or repository; `tests/api/ArchitectureTests.cs:25-41` enforces it) and call the use cases in `Application/Settings/OrganizationSettingsUseCases.cs`, which run through `ISetupExecution` (authorization, then a serializable transaction for writes, then the same change-log retry as every other write) and give the same 403 Problem with no `detail`. Response bodies are named DTOs whose JSON is byte-identical to the entities they replaced (`OrganizationDto`, `LocalizationDto`, `BrandingDto`, `SecurityPolicyDto`, `UserPreferenceDto`, `Application/Settings/SettingsContracts.cs:28-57`; test `SettingsContractTests.cs:25-86`); only the OpenAPI schema names changed.
**O01 `GET /setup/organization/settings`**: perm `organization.manage`. 200 `OrganizationSettingsResponse` = `{ organization, localization, branding, securityPolicy, effectiveBusinessDate, calendarDate, effective }` (section 3.7). The four sections are the stored entities serialised whole (including `organizationId`; a missing row yields defaults). `effectiveBusinessDate` = held business date or the calendar date; `calendarDate` = today in the ORGANIZATION zone regardless of any held date (the latest date the business date may take).
**O02 `PUT /setup/organization/settings/{section}`**: perm `organization.manage`. Body `{ "value": <json>, "reason"?: string }`. `section` in `organization`, `localization`, `branding`, `securityPolicy`, `businessDate`; any other => **404** Problem (`Record not found in your scope.`; `OrganizationSettingsUseCases.cs:37`). A typed `reason` over 500 chars (trimmed) => 400.
- `organization`: `value` = `{ name, slug }` strings. `name` trimmed 1..200; `slug` trimmed, lower-cased, 1..100, `^[a-z0-9]+(?:-[a-z0-9]+)*$`. Invalid => **400 plain `{"detail":"Enter an organization name and a lowercase slug using letters, numbers, and hyphens."}`**; slug used by another organization => **409 plain `{"detail":"This organization slug is already in use."}`**.
- `localization`, `branding`, `securityPolicy`: `value` must be a JSON object (400 `Send the section's settings as an object.`). It is MERGED onto the saved section (property names case-insensitive; omitted fields keep their stored value; `organizationId` in the payload is ignored), then deserialised (a wrongly typed value => 400 `A setting has the wrong type of value.`) and validated with the entity's `Validate` (messages in 3.7). Localization changes also require the held business date to stay on or before today in the (new) zone: 400 `The held business date would be in the future in that time zone. Change the business date first.` (`Organization.ChangeTimeZone`, which no longer bumps the version itself: the save's change-log entry moves `settingsVersion` exactly once, so `GET /setup/appearance` `settingsVersion` is +1 after a localization save, test `OrganizationSettingsTests.cs:204-217`). **`useGrouping` (phase 6, uncommitted)**: the localization field is `useGrouping`; a payload that sends the old name `useGroupping` is accepted and treated as `useGrouping`, and when both names are sent the current name wins (`MergedSection` `legacyNames`, `Application/Settings/SettingsSections.cs:35-38,48-67`; test `OrganizationSettingsTests.cs:78-100`). Automatic reasons read `Changed digit grouping to off` / `... to on`.
- `businessDate`: `value` = `null` (follow the calendar) or `"yyyy-MM-dd"`; unparsable, a non-string, or `0001-01-01` => 400 `Business date must be a valid calendar date or null.`; after today's date in the organization zone => 400 `The business date cannot be in the future.`
- No change (before text equals after text) => 200 `{ "section": "<section>" }` with NO version bump and NO log. Otherwise one change-log row and `organization.settingsVersion` +1 (written only by `SettingsChangeLog.Record`, `Application/Settings/SettingsChangeLog.cs:11-19`), then 200 `{ "section": "<section>" }`. A section's own refusal (the slug 400/409 above) saves nothing. The write is retried up to three times when only the change-log counter collided with another writer; a collision that keeps happening ends as 409 Problem `Settings changed. Reload before saving.` (4 transactions; test `ChangeLogAndScopeTests.cs:142-185`), the same for the logo endpoints. Automatic reason: `Changed the {setting} to {value}` for each changed field, joined `a`, `a and b`, `a, b and c`, e.g. `Changed the first day of the week to Sunday and the currency to USD`; setting words come from a fixed map (3.9) or the field name split into lower-case words; values read `on`/`off`/`none`, the weekday name for `firstDayOfWeek`, strings as is. `businessDate`: `Set the business date to {yyyy-MM-dd}` or `Returned the business date to the calendar`. Typed reason appended as in 2.0.
**O03 `PUT /setup/organization/logo`**: perm `organization.manage`. Body `{ "dataUrl": string, "reason"?: string }`. `dataUrl` must be `data:image/png|jpeg|webp;base64,<base64>` (regex `^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)$`), at most `ceil(262144/3)*4 + 64` characters, decoded size 1..262144 bytes, and the bytes must carry the declared type's signature (PNG 8-byte signature, JPEG `FF D8 FF`, WebP `RIFF....WEBP`). 400 messages: `The logo must be at most 256 KB.`, `Upload a PNG, JPEG or WebP image.` (this includes SVG), `The image could not be read.`, `The file is not the image type it claims to be.`
200 `{ "logo": "<data URL rebuilt from the stored bytes>" }`. Log section `logo`: `Uploaded a new logo`. Replaces any existing logo.
**O04 `DELETE /setup/organization/logo?reason=`**: perm `organization.manage`. Optional query `reason`. 200 `{ "logo": null }` (also when there was no logo, then nothing is logged). Log `Removed the logo`. This is a hard delete of the stored image.
**O05 `GET /setup/appearance`**: any member (no permission). 200 `AppearanceResponse` (section 3.7) = `{ organizationName, settingsVersion, businessDate, branding: {displayName, logoAlt, primary, secondary, accent, logo}, formats: {...}, themeMode, reducedMotion, fontScale, lockoutThreshold, lockoutMinutes }`.
It is "what every member's screens need to look and format as the organization and the person chose" and is the ONLY place a non-administrator can read the organization's wrong-PIN policy (`lockoutThreshold`, `lockoutMinutes`, "appended for the phone, which enforces the wrong-PIN policy offline; older clients ignore them", `Application/Settings/OrganizationSettingsUseCases.cs:90-92`).
`businessDate` = held business date or today's calendar date in the organization zone. `branding.logo` = the uploaded logo as a data URL, or `null`. Effective values: see 3.7. The effective settings are validated on every read; a stored value that fails validation (for example a brand colour that no longer meets contrast) turns this read into a 400.
**O06 `GET /setup/preferences`**: any member. 200 `PreferencesResponse`: the caller's personal row (defaults when none: all `null`, `reducedMotion` false, `fontScale` 1) where `locale`, `timeZone`, `hour12`, `themeMode` are returned as `null` whenever the organization does not allow that override (a stored value is never offered back), plus `allowLocaleOverride`, `allowTimeZoneOverride`, `allowHour12Override`, `allowThemeOverride` and `organization: { locale, timeZone, hour12 }` (the organization defaults). `reducedMotion` and `fontScale` are returned as stored.
**O07 `PUT /setup/preferences`**: any member. Body `SaveUserPreferences` = `{ locale?: string or null, timeZone?: string or null, hour12?: bool or null, themeMode?: string or null, reducedMotion: bool, fontScale: number }`; extra fields (the web sends the whole GET payload back) are ignored. `fontScale` is a non-optional number: omitting it means 0, which fails validation.
- Validation (400 `Invalid setup change`): `locale` must match `^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$` (`Use BCP 47 locale.`); `timeZone` must be a known zone id (`'{value}' is an unknown or invalid time zone identifier. (Parameter 'value')`; note the .NET suffix); `themeMode` null, `light`, `dark` or `system`, and `fontScale` finite and 1..3 (`Invalid accessibility preferences`); then the override flags: `Your organization does not allow a personal locale.`, `... a personal time zone.`, `... a personal clock format.`, `... a personal theme.` (only when the corresponding field is non-null and the flag is off).
- The row is created or updated inside the same serializable transaction as other writes (`OrganizationSettingsUseCases.cs:118-131`); no change-log entry, no settings-version bump. 200 body is the saved `UserPreferenceDto` (`organizationId`, `userId`, `locale`, `timeZone`, `hour12`, `themeMode`, `reducedMotion`, `fontScale`), with the validated/canonicalised `locale` and `timeZone`.

### 2.12 Health and OpenAPI

See 1.12 and 1.13. **H01** `GET /health/live` 200 always (no database); **H02** `GET /health/ready` 200, or 503 when the database cannot be connected to (10 s check timeout); **H03** `GET /health` 200 `{"status":"ok"}`; **X01** `GET /openapi/v1.json` in Development and Testing only.
None of them is rate limited or authenticated; all carry `X-Request-ID`.

---

## 3. Per-feature detail: DTOs, enums and call sequences

Notation: `T?` = may be `null` (always written as `null`, never omitted). All property names are camelCase on the wire. "date" = `yyyy-MM-dd`, "instant" = UTC ISO-8601, "guid" = lower-case hyphenated.

### 3.1 Authentication and devices

**Request `AuthRequest`** (used by A01-A11; A12 ignores its body): `{ email: string, phoneNumber: string, pin: string, deviceId: string, code: string, refreshToken: string }` (all default `""`).
Field use per operation:

| Operation | phoneNumber | pin | code | deviceId | refreshToken | Bearer |
|---|---|---|---|---|---|---|
| sign-in, unlock | yes | yes | no | yes | no | no |
| verify-device | yes | no | yes | yes | no | no |
| setup-pin/request, pin-reset/request | yes | no | no | yes | no | no |
| setup-pin/verify, pin-reset/verify | yes | no | yes | yes | no | no |
| setup-pin/complete, pin-reset/complete | yes | yes (new PIN) | yes | yes | no | no |
| refresh | no | no | no | yes | yes | no |
| sign-out | no | no | no | yes | yes | no |
| devices/{id}/revoke | no | no | no | (path id) | no | required |

`email` is never used for lookup (accounts are found by phone number only); it is only length/format validated.

**Response `AuthResponse`** (all seven properties always present):

| `status` | HTTP | Populated extras | Produced by |
|---|---|---|---|
| `authenticated` | 200 | `accessToken`, `refreshToken` | A01-A03, A06, A09, A10 |
| `verification_required` | 202 | `maskedEmail`; `developmentCode` in DevelopmentMode | A01/A02 |
| `check_email` | 202 | `developmentCode` in DevelopmentMode | A04, A07 |
| `code_verified` | 200 | none | A05, A08 |
| `paused` | 423 | `retryAfterSeconds` (int, > 0) | A01/A02 |
| `authentication_failed` | 401 | none | A01-A03, A05, A06, A08-A10 |
| `invalid_pin` | 400 | `minimumPinLength` (int 4..8) | A06, A09 |
| `invalid_request` | 400 | none | pre-validation of A01-A12 |
| `signed_out` | 200 | none | A11 |
| `device_revoked` | 200 | none | A12 |
| `service_unavailable` | 503 | none | A01/A02 (new-device email failed) |

Notes: `payload_too_large` (413) is produced only by the web proxy and is not part of `AuthStatus` in `packages/shared/src/auth.ts`. The web proxy never forwards `accessToken`/`refreshToken` to the browser (it moves them into HttpOnly cookies) and drops `developmentCode` in production builds.
**`AuthSessionResponse`** (A13): `{ userId: guid, firstName: string, lastName: string, role: string, permissions: string[] }`.

**Token and credential formats (needed to keep existing accounts working after a rewrite)**
- PIN hash (`users.PinHash`): `base64(salt 16 bytes) + "." + base64(PBKDF2-HMAC-SHA256(pin as UTF-8, salt, 210000 iterations, 32 bytes))`. A wrong-length or malformed stored hash would throw (500), so keep the format.
- Verification codes and refresh tokens are stored as the UPPER-CASE hex of HMAC-SHA256 with key = UTF-8 bytes of `Auth:SigningKey` over the UTF-8 value (`TokenIssuer.Hash`). Changing the signing key invalidates all outstanding codes and refresh tokens (access tokens too).
- Verification code: 6 decimal digits (`000000`..`999999`, zero padded), expires 10 minutes after creation (`now <= expiresAt` is still valid, one tick later is not), at most 5 wrong tries, single use, bound to user + purpose (`FirstSetup`, `NewDevice`, `PinReset`) + `deviceId`.
- Email (SMTP, port from `Email:Port` default 587, SSL): subject `Your verification code`, body `Your {Purpose} code is {code}. It expires in 10 minutes.` where `{Purpose}` is the raw enum name (`FirstSetup`, `NewDevice`, `PinReset`); From = `Email:From`. In Development with a local database the sender only logs `DEV EMAIL to {Email}: {Purpose} verification code {Code} (10 minutes)`.
- Trust: a device is trusted after a verified code or a completed PIN set/reset. `TrustedDevice.trustExpiresAt` = null (never) unless `Auth:TrustLifetimeDays` is set (must be positive or null).
- Policy numbers used at sign-in come from the single active membership's organization security policy, clamped into the bounds: `lockoutThreshold` 3..10 (default 5), `lockoutMinutes` 1..60 (15), `accessTokenMinutes` 1..15 (10), `refreshTokenDays` 1..90 (30), `pinLength` 4..8 (4). A user with no active membership or no role cannot receive tokens: the sign-in answers 401 `authentication_failed` even with a correct PIN.

**Call sequences (auth)**

| Flow | Calls in order (web through its proxy; mobile direct) | Outcome / client reaction |
|---|---|---|
| Sign in, trusted device | `POST sign-in` (web) or `POST unlock` (mobile lock screen; mobile uses `sign-in` on first entry) with `phoneNumber`, `pin`, `deviceId` | 200 `authenticated`; mobile stores `{phoneNumber, accessToken, refreshToken, lastOnlineAt}` then `GET auth/session`; web proxy sets cookies and the UI calls `GET /api/auth/session` |
| Sign in, new device | `POST sign-in` -> 202 `verification_required` (+`maskedEmail`) -> user types the 6-digit code -> `POST verify-device` `{phoneNumber, code, deviceId}`; "Send a new code" repeats `sign-in` with the same PIN | 200 `authenticated`; device now trusted. 401 on a wrong code (5 wrong codes kill it) |
| First PIN | `POST setup-pin/request` -> 202 `check_email`; `POST setup-pin/verify` `{phoneNumber, code}` -> 200 `code_verified`; `POST setup-pin/complete` `{phoneNumber, pin, code}` (same code) | 200 `authenticated`; 400 `invalid_pin` + `minimumPinLength` -> client re-asks with the longer length; 401 -> "code no longer works" |
| Forgot PIN | same three calls under `pin-reset/` (only for accounts that already have a PIN) | Success revokes every refresh token and every access token of the user; clients on other devices get 401 then a failing refresh |
| Renew | any authorized call returns 401 -> `POST refresh` `{refreshToken, deviceId}` -> retry the call once; a second 401 ends the session | web: one shared refresh at a time (`POST /api/auth/refresh` with body `{}`; the proxy fills the cookie values); mobile: one shared renew at a time. Refresh 401 = session over |
| Sign out | `POST sign-out` `{refreshToken, deviceId}` | 200 `signed_out`; web clears `access`, `refresh` cookies |
| Switch user / forget this phone | mobile: `POST devices/{deviceId}/revoke` (Bearer); if 401 -> renew and retry once; any other failure -> `POST sign-out`; then wipes local keys | 200 `device_revoked`; device must verify by email code on the next sign-in |
| Admin removes or signs out a person | `POST /setup/people/{id}/deactivate` or `.../sign-out` | their next call is 401 (device revoked / SecurityVersion), refresh is 401, client shows sign-in |
| Admin changes a person's role, name or single permissions | `PUT /setup/people/{id}` | their next call is 401 once (SecurityVersion bump); refresh succeeds and the new token carries the new role and permissions |

Mobile-only behaviour that depends on the API: wrong-PIN counting and the pause timer run locally using `lockoutThreshold` and `lockoutMinutes` from `GET /setup/appearance`; when `unlock` fails with a network error or a 5xx the phone falls back to an offline PIN check (PBKDF2 100 000 iterations, client side only) valid for 72 hours after the last online sign-in or renewal.

### 3.2 Permissions, roles and data scope

**Permission catalog** (`GET /setup/access/catalog`; `Application/AccessContracts.cs:26-94`; order is the wire order). `needs` = direct dependencies (`PermissionDependencies.DirectFor`); an item with none has `"needs": []`.

| Group | key | label | needs |
|---|---|---|---|
| Dashboard | `dash.capture` | See today's capture for my vehicles | `revenue.capture` |
| Dashboard | `dash.float` | See my petty cash float | `pettycash.spend` |
| Dashboard | `dash.revenue` | See revenue totals | `revenue.view` |
| Dashboard | `dash.net` | See net contribution and weakest vehicles | `revenue.view`, `expenses.view`, `commitments.view` |
| Dashboard | `dash.costs` | See cost totals | `expenses.view`, `commitments.view` |
| Dashboard | `dash.gaps` | See missing revenue days | `revenue.view` |
| Dashboard | `dash.pettycash` | See petty cash waiting for approval | `pettycash.view_all` |
| Dashboard | `dash.commitments` | See renewals due | `commitments.view` |
| Dashboard | `dash.investment` | See money invested and how much is back | `invest.view` |
| Dashboard | `dash.edits` | See records edited after capture | `audit.view` |
| Revenue | `revenue.view` | View revenue records | none |
| Revenue | `revenue.capture` | Capture revenue | `revenue.view` |
| Revenue | `revenue.no_earnings` | Record a no earnings reason | `revenue.capture` |
| Revenue | `revenue.correct` | Correct revenue after the day | `revenue.view` |
| Expenses | `expenses.view` | View expenses | none |
| Expenses | `expenses.capture` | Record an expense straight onto a vehicle | `expenses.view` |
| Expenses | `expenses.correct` | Change an expense after the day | `expenses.view` |
| Expenses | `expenses.setup` | Set up expense categories and items | `expenses.view` |
| Petty cash | `pettycash.spend` | Record spending from my float | none |
| Petty cash | `pettycash.view_all` | View every float | none |
| Petty cash | `pettycash.approve_item` | Approve single entries | `pettycash.view_all` |
| Petty cash | `pettycash.approve_day` | Approve a whole day | `pettycash.approve_item` |
| Petty cash | `pettycash.issue` | Record money sent to a float | `pettycash.view_all` |
| Petty cash | `pettycash.issue_negative` | Send money that takes a float below zero | `pettycash.issue` |
| Office bills | `bills.view` | View office bills | none |
| Office bills | `bills.capture` | Capture office bills | `bills.view` |
| Office bills | `bills.approve` | Approve office bills | `bills.view` |
| Scheduled expenses and savings | `commitments.view` | View scheduled expenses and savings | none |
| Scheduled expenses and savings | `commitments.manage` | Set up, change and stop scheduled expenses and savings | `commitments.view` |
| Reports | `reports.view` | View reports | none |
| Reports | `reports.export` | Export reports | `reports.view` |
| Setup | `companies.manage` | Set up PSV companies | none |
| Setup | `vehicles.manage` | Set up vehicles and weekly targets | none |
| Setup | `invest.view` | See what was invested in a vehicle | none |
| Setup | `invest.manage` | Record what was invested in a vehicle | `invest.view` |
| Setup | `people.view` | View people | none |
| Setup | `people.manage` | Add people, choose their role and what they can see, remove access | `people.view` |
| Setup | `access.manage` | Change single permissions and approval limits for a person | `people.manage` |
| Setup | `audit.view` | View the change log | none |
| Setup | `organization.manage` | Manage organization settings | none |

Wire shape: `[ { "name": "Dashboard", "items": [ { "key": "dash.capture", "label": "...", "needs": ["revenue.capture"] } ] } ]`. Group names exactly: `Dashboard`, `Revenue`, `Expenses`, `Petty cash`, `Office bills`, `Scheduled expenses and savings`, `Reports`, `Setup`. The phone looks up the groups `Revenue`, `Petty cash`, `Office bills` BY NAME (test `Phase1AppearanceAndCatalogContractTests`).

**Role defaults** (before dependency expansion; role names are matched case-insensitively; `GET /setup/access/roles` returns them expanded):

| Role | Default permissions |
|---|---|
| `Owner` | every catalog key except `dash.capture` |
| `Office admin` | `dash.revenue`, `dash.costs`, `dash.gaps`, `dash.commitments`, `dash.edits`, `revenue.view`, `revenue.correct`, `expenses.view`, `expenses.capture`, `expenses.correct`, `expenses.setup`, `bills.view`, `bills.capture`, `commitments.view`, `commitments.manage`, `reports.view`, `reports.export`, `invest.view`, `invest.manage`, `companies.manage`, `vehicles.manage`, `people.view`, `people.manage`, `audit.view` |
| `Fleet manager` | `dash.float`, `dash.revenue`, `dash.costs`, `dash.gaps`, `revenue.view`, `revenue.capture`, `revenue.no_earnings`, `revenue.correct`, `pettycash.spend`, `expenses.view`, `reports.view` |
| `Revenue clerk` | `dash.capture`, `dash.gaps`, `revenue.view`, `revenue.capture`, `revenue.no_earnings` |

**Effective permissions** (`EffectivePermissionResolver`): inactive membership => empty set. Otherwise start from the role defaults plus every GRANTED override, expand dependencies transitively, remove every DENIED override, then repeatedly remove any permission whose direct dependencies are no longer all present. Per-person overrides are stored only as differences from the role defaults (granted = requested but not default; denied = default but not requested). The JWT `permission` claims and `GET /auth/session` carry this set as computed at sign-in/refresh; request-time checks recompute it from the database.
**Data scope** per person: exactly one of `all` (a `SetupDataScope` row with `allCompanies`), `companies` (list of company ids), `vehicles` (list of vehicle ids). `scopeMode` on the wire: `all` if the all-companies row exists, else `companies` if any company scope exists, else `vehicles`. Roles `Owner` and `Office admin` get `all` when provisioned from the command line.
**Permission keys and refusal wording (phase 5, `Domain/PermissionKeys.cs:4-53`, `Application/AccessContracts.cs:98-102`)**: the 40 keys above are the constants of `PermissionKeys`, the single list that the catalog, the role defaults, the dependency graph and every `execution.Read/Write(...)` call use; `PermissionKeysTests.cs:29-52` fails when a constant is missing from the catalog or the catalog has a key without a constant, and `packages/shared/src/permissions.ts` (`PERMISSION_KEYS`, untracked **(uncommitted)**) must list the same keys in the same order (`PermissionKeysTests.cs:38-45`). A permission refusal that names a permission is `PermissionCatalog.Refusal(action, key)` = 403 Problem whose `detail` is `{action} needs the permission "{label}".` with the catalog label of `key`; for a key the catalog does not label the detail uses the key itself (`Doing that needs the permission "no.such_key".`) instead of failing with a 500 as before (`PermissionKeysTests.cs:54-59`). The wording for the three revenue refusals is unchanged (2.10 step 7); petty cash adds more of them (`inventory-petty-cash.md`). A plain missing permission in the use-case pipeline is still the detail-less 403.
**Anti-escalation rules** (403 messages in 2.3): only an Owner grants, edits, removes or signs out an Owner; nobody edits or deactivates themselves; a non-Owner can only grant roles/permissions they hold themselves and only inside their own data scope; single-permission changes and approval limits need `access.manage`; email/phone changes need an Owner or a caller who sees the person's full scope and holds everything the person holds.

### 3.3 People and access DTOs

| DTO | Fields (wire order) |
|---|---|
| `PersonDto` | `id` guid, `firstName`, `lastName`, `email`, `phoneNumber` (`+254...`), `role`, `active` bool, `scopeMode` (`all`/`companies`/`vehicles`), `companyIds` guid[], `vehicleIds` guid[], `permissions` string[] (effective set, assigned permissions are kept for inactive people), `approvalLimit` number?, `hasPin` bool, `version` long, `otherCompanies` int, `otherVehicles` int |
| `SavePerson` (body) | `firstName`, `lastName`, `email`, `phoneNumber`, `role`, `scopeMode`, `companyIds` guid[], `vehicleIds` guid[], `permissions` string[], `approvalLimit` number?, `version` long? (required on update, ignored on create) |
| `PersonLifecycleRequest` (optional body) | `version` long?, `reason` string? |
| `AccessRole` | `id` guid, `name`, `permissions` string[] |
| `ScopeOptions` | `companies` `[{id, name}]`, `vehicles` `[{id, registration, companyId}]` |
| `MyScope` | `allCompanies` bool, `companies` `[{id, name}]`, `vehicles` `[{id, registration, companyId}]` |
| `IdResponse` | `id` guid |

| Concept | Facts |
|---|---|
| Person identity | `id` = the user id (same as JWT `sub` and session `userId`). Phone and email are unique across ALL users (unique indexes, phone index ignores the empty string) |
| Invite / accept | **Does not exist.** Creating a person (S07) sends no email. The person opens the sign-in screen, taps "first time", and runs A04-A06 (setup PIN) which emails a code to the address on file. Web toast on create: `{name} added. They sign in with {phone} and set a PIN with an email code.` |
| Organization switch | **Does not exist.** A user has exactly one active membership (unique filtered index `Memberships(UserId) WHERE Active = 1`); the token carries one `org` claim; every query is filtered by it. Provisioning supports a single organization (`Program.cs --provision-user`, `UserProvisioning.EnsureOrganization`) |
| `hasPin` | false until the person completes setup; `signInState` in the web derives "waiting for PIN" from `active` + `hasPin` |
| Concurrency | `version` on `PersonDto` is `OrganizationMembership.version` (starts 1, +1 on deactivate/reactivate and on any access change). Update and lifecycle calls must echo it; mismatch = 409 `Settings changed. Reload before saving.` |
| Visible people | see 2.3 S05; a scoped caller never sees ids outside their own scope (counts only) |

### 3.4 Companies and vehicles DTOs

| DTO | Fields (wire order) |
|---|---|
| `CompanyDto` | `id`, `name`, `vehicleCount` int, `active` bool, `archivedOn` date? |
| `CompanyOption` | `id`, `name` |
| `VehicleDto` | `id`, `companyId`, `companyName`, `registration` (`KDA 482M`), `joinedOn` date, `leftOn` date?, `active` bool, `weeklyTarget` number? , `targets` `TargetDto[]`, `recurringItems` int?, `away` `AwayPeriodDto[]` |
| `TargetDto` | `effectiveFrom` date, `weeklyAmount` number, `revision` int |
| `AwayPeriodDto` | `leftOn` date, `returnedOn` date (away from `leftOn` through the day before `returnedOn`) |
| `SaveCompany` | `name`, `reason`? |
| `CompanyLifecycleRequest` | `reason`? |
| `SaveVehicle` | `companyId` guid, `registration`, `joinedOn` date, `weeklyTarget` number, `reason`? |
| `VehicleLifecycleRequest` | `leftOn` date, `reason`? |
| `VehicleRestoreRequest` | `reason`?, `returnedOn` date? |

| Rule | Definition |
|---|---|
| Vehicle active on date D | `D >= joinedOn` AND (`leftOn` null OR `D < leftOn`) AND D is not inside any away period `[leftOn, returnedOn)` |
| Target on D | 0 if not active; else `weeklyAmount` of the target with the greatest `effectiveFrom <= D` (ties: greatest `revision`); daily expectation = target / 7 |
| Company active on D | `archivedOn` null OR `archivedOn > D` |
| Registration | uppercase `K` + 2 letters + 3 digits + 1 letter, stored with one space after the 3rd character; unique per organization; immutable |
| Name limits | company 1..160, expense category/item 1..100, recurring name 1..160, reason 1..500 (after trim), investment description 1..160, recurring note <= 200, revenue note <= 80, organization name <= 200, slug <= 100 |
| Deletion | none of company, vehicle, recurring item, expense category/item, revenue record is ever deleted; only investment entries and the logo are hard-deleted. Targets, away periods, recurring versions/allocations and change-log rows are append-only |

### 3.5 Scheduled items, expense catalog, investment and vehicle report DTOs

| DTO | Fields (wire order) |
|---|---|
| `RecurringDto` | `id` (item), `versionId`, `revision` int, `name`, `kind` int (1 Cost, 2 Savings), `amount`, `frequency` int (1..4), `day` int?, `lastDay` bool, `start` date, `end` date?, `stoppedFrom` date?, `allocations` `AllocationDto[]`, `partial` bool, `expenseItemId` guid?, `expenseItemName` string?, `bucket` int? (1..3, cost only), `note` string?, `month` int?, `activeAmount` number |
| `AllocationDto` | `vehicleId`, `amount`, `registration` string?, `active` bool |
| `VehicleOption` | `id`, `companyId`, `companyName`, `registration`, `active` bool |
| `SaveRecurring` (body) | `name` string?, `kind` int, `amount` number, `frequency` int, `day` int?, `lastDay` bool, `start` date, `end` date?, `allocations` `[{vehicleId, amount}]`, `reason` string?, `expenseItemId` guid?, `note` string?, `month` int? |
| `StopRecurring` (body) | `confirmed` bool, `reason` string |
| `ExpenseCategoryDto` | `id`, `name`, `bucket` int, `active` bool, `stoppedOn` date?, `items` `ExpenseItemDto[]` |
| `ExpenseItemDto` | `id`, `categoryId`, `name`, `active` bool, `stoppedOn` date? |
| `ExpenseItemOption` | `id`, `name`, `categoryId`, `categoryName`, `bucket` int |
| `SaveExpenseCategory` / `SaveExpenseItem` | `{name?, bucket}` / `{name?}` |
| `InvestmentDto` | `vehicleId`, `totalInvested`, `returned` number?, `percentPaidOff` number?, `entries` `InvestmentEntryDto[]` |
| `InvestmentEntryDto` | `id`, `date`, `description`, `amount`, `recordedBy` (full name or `""`), `recordedAt` instant |
| `SaveInvestment` (body) | `date`, `description` string?, `amount` |
| `VehicleReport` | `vehicleId`, `from` date, `through` date, `moneyIn`, `target`, `repairs`, `charges`, `loans`, `moneyOut`, `net`, `savings`, `afterSavings`, `costs`, `postings` `PostingDto[]` |
| `PostingDto` | `itemId`, `versionId`, `date`, `name`, `kind` int, `amount`, `bucket` int?, `source` string? **(uncommitted)** (`"pettycash"` for approved petty cash spending, whose `itemId` and `versionId` are the entry id; `null` for a scheduled item; appended last, `Application/Setup/SetupContracts.cs:69-72`, test `VehicleReportTests.cs:117-124`) |

| Enum | Values |
|---|---|
| `kind` | 1 = Cost, 2 = Savings |
| `frequency` | 1 = Daily (legacy, readable, never accepted on save), 2 = Weekly, 3 = Monthly, 4 = Yearly |
| `bucket` | 1 = repairs and maintenance, 2 = recurring charges, 3 = loan repayments (fuel and crew pay are not tracked) |
| `day` | weekly: 0..6 (0 = Sunday); monthly/yearly: 1..28; with `lastDay` true `day` is null and the item falls on the last day of the month |

| Report rule | Definition |
|---|---|
| Window | `first = max(from, joinedOn)`; `last = min(through, today)`, and if `leftOn <= last` then `last = leftOn - 1 day` |
| `moneyIn` | sum of `amount` of the vehicle's revenue records in `[first, last]` (reason-only days add 0) |
| `target` | sum of `targetOn(d) / 7` over days in `[first, last]` that are before today or have a record, rounded to 2 decimals |
| Postings | every item with a share on this vehicle: due dates in `[first, last]` computed per version (a version rules from its `effectiveFrom` until a higher revision takes over, within its `start`..`end` and before `stoppedFrom`), amount = this vehicle's share; ordered by date, then name (ordinal), then item id; **(uncommitted)** every APPROVED, not removed petty cash EXPENSE entry of the vehicle dated in the window is added as a Cost posting named after its expense item, with that item's category bucket and `source` `"pettycash"` (`Infrastructure/Setup/SetupRepository.cs:254-261,269`), so it counts in `repairs`/`charges`/`loans` and `moneyOut` |
| Buckets | `repairs`, `charges`, `loans` = sums of Cost postings by reported bucket (cost with no stored bucket counts as 2); `savings` = sum of Savings postings |
| Totals | `moneyOut = repairs + charges + loans` (investment is never included); `net = moneyIn - moneyOut`; `afterSavings = net - savings`; `costs = moneyOut` (kept for older screens) |
| Due-day rules | weekly: `dayOfWeek == day`; monthly: day of month == `day` (or the last day when `lastDay`); yearly: month == `month` and the same day rule; a day that does not exist in a month is skipped |

### 3.6 Revenue DTOs and the capture / offline-replay sequence

| DTO | Fields (wire order) |
|---|---|
| `RevenueCellDto` | `date`, `status` (string enum `CellStatus`, the only string enum on the wire: `none`/`future`/`missing`/`amount`/`reason`, `Application/RevenueContracts.cs:19-28`), `expected` number (per-day target/7, 2 dp), `amount` number?, `reason` string? (label: `Garage`, `Arrest`, `No Crew`, `Other`), `note` string?, `canEdit` bool, `editedAfterCapture` bool, `version` long? (null when no record) |
| `RevenueVehicleDto` | `id`, `companyId`, `companyName`, `registration`, `joinedOn`, `leftOn` date?, `earliestMissing` date?, `days` `RevenueCellDto[7]`, `totalAmount`, `totalExpected`, `percent` int? |
| `RevenueWeekDto` | `weekStart`, `weekThrough`, `currentWeekStart`, `businessDate`, `companies` `[{id, name}]`, `vehicles`, `totalAmount`, `totalExpected`, `percent` int?, then (phase 5, appended in this order, `Application/RevenueContracts.cs:82-97`; key order pinned by `RevenueWeekPagingTests.cs:174-175`) `pageNumber` int, `pageSize` int, `totalVehicles` int, `truncated` bool, `dayTotals` `RevenueDayTotalDto[7]` (`{ date, amount, expected }`, numbers rounded to 2 dp, `:100`), `firstGap` `RevenueGapDto?` (`{ vehicleId: guid, date }`, null when no vehicle needs capture, `:103`) |
| `RevenueDashboardDto` | `period`, `from`, `through`, `businessDate`, `revenue`?, `expected`?, `percent`?, `capturedToday`?, `vehiclesToday`?, `missingDays`?, `missingVehicles`?, `editedRecords`? (`?` = null when the caller lacks that card's permission) |
| `SaveRevenue` (body) | `amount` number?, `reason` string?, `note` string?, `version` long? |
| `RevenueSaved` | `id` guid, `version` long (exactly these two, this order) |
| 409 Problem extension | `current`: a `RevenueCellDto` |
| 400 Problem extension | `earliestMissing`: date **(removed by 9276c51: days are captured in any order; see the drift log entry 24)** |

| Cell rule | Definition (`RevenueCellDto.For`) |
|---|---|
| `status` | not active that day => `none`; after today => `future`; no record => `missing`; record with an amount => `amount`; record with only a reason => `reason` |
| `canEdit` | `missing`: holds `revenue.capture` (every missing day, in any order, since 9276c51 `RevenueContracts.cs:54-55`; it used to need the date on or before the vehicle's earliest missing day); `amount`/`reason`: today => `revenue.capture` OR `revenue.correct`, an earlier day => `revenue.correct`; `none`/`future`: false |
| `editedAfterCapture` | the record's `correctedAfterDate` (set when a day before today is changed after capture) |
| `earliestMissing` | the first active day before today (or before `leftOn`) with no record; null when the vehicle is complete |
| `version` | the record's concurrency version; the client must echo it to change that day |

| Step | Capture on the web | Capture or replay from the mobile queue |
|---|---|---|
| Read | `GET setup/revenue?weekStart=<any date in week>&companyId=` ; one vehicle: `GET setup/revenue?weekStart=<date>&vehicleId=<guid>` | `GET setup/revenue` (current week, written to a local capture list), `GET setup/revenue?weekStart=&vehicleId=` for another week or vehicle |
| Write | `PUT setup/revenue/{vehicleId}/{date}` body `{amount, reason, note, version}` (`version` = the cell's `version`, `null` for a first capture) | same URL (vehicle id URL-encoded), same body from the stored queue entry: `{amount, reason, note, version}`; `Content-Type: application/json`; Bearer token |
| 200 | `{id, version}`; grid reloads; moves to the next missing vehicle/day | entry removed from the queue. An identical replay (same amount, reason, note) is also 200 and changes nothing (the phone may resend after a lost response, even after the day closed) |
| 409 + `current` | shows "Saved value" vs "Yours"; "Replace with mine" resends with `current.version`; "Keep saved" drops the entry | entry becomes `conflict` (message "Someone else saved this day first."), `current` kept; "Replace with mine" resends with `current.version` |
| 409 without `current` | re-reads the day (`GET setup/revenue?weekStart=<date>&vehicleId=`) and shows the choice | the phone re-reads the day (`weekStart` = date minus 6 days, `vehicleId`) and uses that cell; if none is found the conflict has no saved value |
| 400 + `earliestMissing` | no longer sent (9276c51) | no longer sent; a stored `blocked` entry from an earlier version reads as `pending` and its `earliestMissing` is dropped (`apps/mobile/src/revenue/queue.ts:40-52,147-152`); every 400 makes the entry `failed` |
| other 400 / 403 / 404 | shows `detail` (or `title`) | entry becomes `failed` with `detail` or `title` (fallbacks: 404 "This vehicle is no longer in your view.", 403 "Your access does not allow this entry.", 400 "The API did not accept this entry.") |
| 429 | n/a | attempt counted, round stops (the API does not rate limit this route; kept for proxies) |
| 5xx / no network | error message | entry stays; retried with back-off 1, 2, 4, 8 then 16 s (capped at 16 s); after 10 failed tries it becomes `failed` ("This entry could not be sent after several tries.") |
| Ordering | one request per click | oldest `date` first (then registration), one request at a time per phone; up to 500 entries per person are kept |

Mobile queue entry JSON (stored in the secure store, one slot per entry plus an index): `{vehicleId, registration, date, amount, reason, note, version, state, message, current, queuedAt, attempts, lastAttemptAt}` with `state` in `pending`, `conflict`, `failed` (an older stored `blocked` reads as `pending`, its `earliestMissing` dropped); `current` = `{amount, reason, note, version, canEdit}`.

### 3.7 Organization settings, appearance and preferences DTOs

| DTO | Fields (wire order) |
|---|---|
| `OrganizationDto` (inside O01; OpenAPI schema name changed from `Organization` in phase 5, same JSON) | `id`, `slug`, `name`, `businessDate` date? (the HELD date, null = follow the calendar), `settingsVersion` long |
| `LocalizationDto` (was schema `OrganizationLocalization`) | `organizationId`, `locale`, `timeZone`, `datePattern`, `hour12`, `firstDayOfWeek`, `weekNumbering`, `currency`, `useGrouping` **(uncommitted, was `useGroupping`)**, `numberDecimals`, `allowLocaleOverride`, `allowTimeZoneOverride`, `allowHour12Override`, `allowThemeOverride` |
| `BrandingDto` (was schema `OrganizationBranding`) | `organizationId`, `displayName`, `legalName`, `logoLight`?, `logoDark`?, `logoAlt`, `favicon`?, `primary`, `secondary`, `accent`, `domain`?, `supportEmail`?, `termsUrl`?, `privacyUrl`? |
| `SecurityPolicyDto` (was schema `OrganizationSecurityPolicy`) | `organizationId`, `passwordMinLength`, `passwordComplexity`, `passwordHistory`, `pinLength`, `lockoutThreshold`, `lockoutMinutes`, `accessTokenMinutes`, `refreshTokenDays`, `idleUnlockSeconds`, `allowPinSignIn` |
| `OrganizationSettingsResponse` (O01) | `organization`, `localization`, `branding`, `securityPolicy`, `effectiveBusinessDate`, `calendarDate`, `effective` (`{formats, branding, securityPolicy, themeMode, reducedMotion, fontScale}`) |
| `SaveOrganizationSettings` (O02 body) | `value` (any JSON), `reason`? |
| `SettingsSectionResponse` | `section` |
| `SaveLogo` / `LogoResponse` | `{dataUrl, reason}` / `{logo}` |
| `EffectiveFormats` | `locale`, `timeZone`, `datePattern`, `hour12`, `firstDayOfWeek`, `weekNumbering`, `currency`, `useGrouping` **(uncommitted)**, `numberDecimals`, `direction` (`rtl` for languages `ar`, `fa`, `he`, `ur`, else `ltr`), then a computed legacy property `useGroupping` = the same boolean again for released apps, to be removed once they are retired (`Domain/Organization.cs:345-348`); it appears in `GET /setup/appearance` `formats` and in `effective.formats` of O01, nowhere else |
| `AppearanceResponse` (O05) | `organizationName`, `settingsVersion` long, `businessDate`, `branding` `{displayName, logoAlt, primary, secondary, accent, logo}`, `formats` (`EffectiveFormats`), `themeMode`, `reducedMotion`, `fontScale`, `lockoutThreshold`, `lockoutMinutes` |
| `UserPreferenceDto` (O07 reply; was schema `UserPreference`, same JSON as the stored row) | `organizationId`, `userId`, `locale`?, `timeZone`?, `hour12`?, `themeMode`?, `reducedMotion`, `fontScale` |
| `PreferencesResponse` (O06) | `organizationId`, `userId`, `locale`?, `timeZone`?, `hour12`?, `themeMode`?, `reducedMotion`, `fontScale`, `allowLocaleOverride`, `allowTimeZoneOverride`, `allowHour12Override`, `allowThemeOverride`, `organization` `{locale, timeZone, hour12}` |

| Setting | Default | Rule (400 message in brackets) |
|---|---|---|
| `locale` | `en-GB` | `^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$` (`Use BCP 47 locale.`) |
| `timeZone` | `Africa/Nairobi` | a zone the host resolves (`'{value}' is an unknown or invalid time zone identifier. (Parameter 'value')`) |
| `datePattern` | `medium` | `short`, `medium`, `long` (`Invalid format settings`) |
| `hour12` | false | bool |
| `firstDayOfWeek` | 1 | integer 0..6, 0 = Sunday (`Invalid format settings`) |
| `weekNumbering` | `iso8601` | `iso8601` or `local` (`Invalid format settings`) |
| `currency` | `KES` | `^[A-Z]{3}$` (`Invalid format settings`) |
| `useGrouping` | true | bool; `useGroupping` is accepted as an alias on save (`legacyNames`, current name wins) **(uncommitted)** |
| `numberDecimals` | 2 | integer 0..2 (`Invalid format settings`) |
| `allowLocaleOverride`, `allowHour12Override`, `allowThemeOverride` | true | bool |
| `allowTimeZoneOverride` | false | bool |
| branding `displayName`, `legalName`, `logoAlt` | `XCODE`, `XCODE`, `XCODE` | non-blank; <= 100, <= 200, <= 200 (`Brand names and logo alt text are required.`) |
| `primary`, `secondary`, `accent` | `#1D5FD6`, `#14213D`, `#1E6B3A` | `^#[0-9a-fA-F]{6}$` (`Use a six-digit hex colour`) and WCAG contrast >= 4.5 against `#FFFFFF` AND `#F6F3EC` (`Brand colors must meet WCAG AA (4.5:1) against the fixed surfaces`) |
| `logoLight`, `logoDark`, `favicon`, `termsUrl`, `privacyUrl` | null | absolute `https` URL <= 2048 (`Brand URLs must use HTTPS.`) |
| `domain` | null | DNS host name <= 253 (`Invalid domain.`) |
| `supportEmail` | null | valid address <= 320 (`Invalid support email.`) |
| security `passwordMinLength` | 12 | 12..128 |
| `passwordComplexity` | true | bool |
| `passwordHistory` | 5 | 0..24 |
| `pinLength` | 4 | 4..8 |
| `lockoutThreshold` | 5 | 3..10 |
| `lockoutMinutes` | 15 | 1..60 |
| `accessTokenMinutes` | 10 | 1..15 |
| `refreshTokenDays` | 30 | 1..90 |
| `idleUnlockSeconds` | 300 | 30..3600 |
| `allowPinSignIn` | true | must stay true (`PIN sign-in cannot be disabled.`); any other numeric breach: `Invalid security policy.` |
| preference `themeMode` / `fontScale` | null / 1 | `light`/`dark`/`system`/null; finite 1..3 (`Invalid accessibility preferences`) |

Effective values (`EffectiveSettingsResolver`): `locale` = org locale unless `allowLocaleOverride` and the person set one; same for `timeZone` (`allowTimeZoneOverride`) and `hour12` (`allowHour12Override`); `themeMode` = person's value or `system` when `allowThemeOverride`, else `light`; `reducedMotion` and `fontScale` always the person's (defaults false and 1); date pattern, week settings, currency, grouping, decimals always the organization's. The security policy sent in `effective` and used for lockout is clamped into the bounds above even if an older stored row is outside them. Business-date maths always use the ORGANIZATION zone, never the person's override.

### 3.8 Health and operability (summary)

| Item | Wire fact |
|---|---|
| Liveness / readiness / legacy | `GET /health/live` 200 no DB; `GET /health/ready` 200 or 503 (DB check, 10 s timeout); `GET /health` 200 `{"status":"ok"}` |
| Request id | `X-Request-ID` in (optional) and out (always); copied to the 500 Problem as `requestId` |
| Logs | outside Development: JSON console logs with scopes (`RequestId`), UTC timestamps |
| 500 body | Problem with `traceId` and `requestId`, no `exception` |
| Compression | `/setup/**` responses are Brotli or Gzip compressed when accepted (1.6); `/auth/**` never |
| Startup | Production refuses to start without `Email:Host`, `Email:From`, `ConnectionStrings:Auth` and a 32-byte signing key and never migrates by itself (1.2); `--migrate` applies migrations and exits; `--provision-user <email> --phone <mobile> [--role] [--first-name] [--last-name] [--organization-name]`; `--remove-user <email>` (no HTTP surface) |

### 3.9 Change log: entries, snapshots and reason strings

`before` / `after` on `HistoryEntry` are strings holding JSON. Casing differs by writer:

| Section | Entity id | Snapshot keys (as serialised) |
|---|---|---|
| `companies` | company | PascalCase: `Id`, `Name`, `ArchivedOn`, `Active` |
| `vehicles` | vehicle | `Id`, `Registration`, `CompanyId`, `JoinedOn`, `LeftOn`, `Targets` `[{EffectiveFrom, WeeklyAmount, Revision}]`, `Away` `[{LeftOn, ReturnedOn}]` |
| `recurring` | item | `Id`, `StoppedFrom`, `Versions` `[{Id, Revision, EffectiveFrom, Name, Kind, Amount, Frequency, Day, LastDay, Month, Start, End, ExpenseItemId, Bucket, Note, Allocations: [{VehicleId, Amount}]}]` (enums as numbers) |
| `expenses` | category or item | category `Id`, `Name`, `Bucket`, `StoppedOn`; item `Id`, `CategoryId`, `Name`, `StoppedOn` |
| `investment` | the VEHICLE | `Id`, `VehicleId`, `Date`, `Description`, `Amount` |
| `revenue` | the record | `Id`, `VehicleId`, `BusinessDate`, `Amount`, `Reason` (enum NAME string such as `NoCrew`, or null), `Note`, `CapturedAt`, `CapturedBy`, `UpdatedAt`, `UpdatedBy`, `CorrectedAfterDate`, `Version` |
| `people` | the person | `FirstName`, `LastName`, `Email`, `PhoneNumber`, `Role`, `Active`, `ScopeMode`, `CompanyIds`, `VehicleIds`, `Permissions` (sorted ordinal), `ApprovalLimit`, `Name` (the computed `"{First} {Last}"`, serialised last; `AccessUseCases.cs:611-614`) |
| `organization` | the organization | camelCase (Web options): `name`, `slug` |
| `localization`, `branding`, `securityPolicy` | the organization | camelCase entity keys incl. `organizationId` (`SettingsText.Json`, Web defaults); localization snapshots written from phase 6 use `useGrouping`, rows written before it keep `useGroupping` inside their stored text (the log is write-once) **(uncommitted)** |
| `pettycash` | the entry | see `inventory-petty-cash.md` |
| `businessDate` | the organization | a JSON string `"yyyy-MM-dd"` or `null` |
| `logo` | the organization | camelCase `{contentType, bytes, updatedAt}` (no image data) or `"null"` |

Create: `before` is the string `null`; remove: `after` is `null`. The web history screen parses these strings, humanises key names (`WeeklyTarget` and `weeklyTarget` both read "Weekly target"), hides keys matching `^(ids?|version)$` or ending `Id`/`Ids`, hides bare GUID values, and shows dates (`yyyy-MM-dd`) and instants in the viewer's formats.

Words used in automatic settings reasons (`SettingNames`): `name` the organization name; `hour12` the 12-hour clock; `datePattern` the date format; `firstDayOfWeek` the first day of the week; `weekNumbering` week numbering; `useGrouping` digit grouping (reason text unchanged, `Changed digit grouping to off`; `Application/Settings/SettingsText.cs:30-54`); `numberDecimals` the decimal places; `allowLocaleOverride` personal locales; `allowTimeZoneOverride` personal time zones; `allowHour12Override` personal clock formats; `allowThemeOverride` personal themes; `logoAlt` the logo text; `logoLight` the light logo; `logoDark` the dark logo; `primary` the primary colour; `secondary` the secondary colour; `accent` the accent colour; `passwordComplexity` password complexity; `pinLength` the PIN length; `lockoutThreshold` the wrong PIN tries before a pause; `lockoutMinutes` the pause in minutes; `allowPinSignIn` PIN sign-in. Any other key becomes `the ` + the key split before capitals and lower-cased (`timeZone` -> `the time zone`). `organizationId` is never mentioned.

### 3.10 Where the exact message strings are

| Family | Location in this document |
|---|---|
| Auth status codes | 3.1 |
| Pagination, reason, generic Problem titles | 1.8, 2.0 |
| People, scope, anti-escalation (400/403/409) | 2.3 |
| Companies, vehicles | 2.4, 2.5 |
| Recurring | 2.6 |
| Change log, expenses, investment | 2.7-2.9 |
| Revenue (400/403/409) | 1.8(B), 2.10 |
| Permission refusals that name a permission (`{action} needs the permission "{label}".`) | 2.10 step 7, 3.2 (`PermissionCatalog.Refusal`; unknown key prints the key) |
| Organization, logo, preferences | 2.11 |
| Validation limits and defaults | 3.4, 3.7 |

---

## 4. Client expectations

### 4.1 packages/shared (`@xcode/shared`, `packages/shared/src`)

| Module | What it fixes about the contract |
|---|---|
| `auth.ts` | `AuthStatus` = `authenticated`, `verification_required`, `check_email`, `code_verified`, `paused`, `authentication_failed`, `invalid_pin`, `invalid_request`, `signed_out`, `device_revoked`, `service_unavailable`. `AuthRequest` = `email?`, `phoneNumber?`, `pin?`, `deviceId?`, `code?`, `refreshToken?`, plus web-only `rememberDevice?`. `AuthResponse` = `status`, `accessToken?`, `refreshToken?`, `retryAfterSeconds?`, `developmentCode?`, `maskedEmail?`, `minimumPinLength?` (each `T or null`). `AuthOperation` = `sign-in`, `verify-device`, `setup-pin/request`, `setup-pin/verify`, `setup-pin/complete`, `pin-reset/request`, `pin-reset/verify`, `pin-reset/complete`, `unlock`, `refresh`, `sign-out`, plus the template `devices/${string}/revoke`. `AuthenticatedPerson` = `userId`, `firstName`, `lastName`, `role`, `permissions[]` |
| `auth.ts` `createAuthClient(baseUrl, fetcher)` | `POST {baseUrl}/{operation}`, headers `Content-Type: application/json` and, when a token is given, `Authorization: Bearer <token>`; body `JSON.stringify(request)`; reads the body as JSON and falls back to `{status:"authentication_failed"}` when it is empty or not JSON (so empty 401/403/429/503 bodies are tolerated); any non-2xx throws `AuthError(response, httpStatus)` |
| `auth.ts` `AuthError.message` | `paused` => "Sign-in is paused. Try again when the timer ends, or reset your PIN."; `invalid_pin` => "Use {min}-8 digits, not all the same or an ascending/descending sequence." (min from `minimumPinLength`, default 4); HTTP 429 => "Too many requests. Please wait a minute."; HTTP >= 500 => "The service is not available right now. Try again shortly."; else "Authentication could not be completed. Check your details and try again." |
| `auth.ts` PIN rules | `validatePin`: 4-8 ASCII digits, not all equal, not full ascending/descending steps (same rule as the server) |
| `revenue.ts` | `RevenueStatus` = `REVENUE_STATUSES` = `none`, `future`, `missing`, `amount`, `reason` (must equal the API `CellStatus` wire values, `PermissionKeysTests.cs:67-74`); **(uncommitted)** `RevenueWeek` also types the paging fields, `dayTotals` and `firstGap` as optional (`packages/shared/src/revenue.ts:101-117`), `REVENUE_WEEK_PAGE_SIZE` = 100 and `remainingWeekPages`/`mergeWeekPages` fetch the pages after a truncated first response (`:119-140`); `REVENUE_REASONS` = `["Garage","Arrest","No Crew","Other"]`; `REVENUE_NOTE_LIMIT` = 80; `RevenueCell`, `RevenueVehicle`, `RevenueWeek`, `RevenueDashboard` (figures `number or null`), `SaveRevenue` = `{amount, reason, note, version?}`; periods `today`, `week`, `month` (report periods `week`, `month`); amount parsing `^\d{1,12}(\.\d{1,2})?$` or grouped with commas |
| `dates.ts` | calendar dates are `yyyy-MM-dd` strings handled as UTC days (`isDate` regex plus real-calendar check); instants parsed with `new Date(value)`; `formatTimestamp` falls back to the raw string when unparsable |
| `format.ts` | `Formats` = `locale`, `timeZone`, `datePattern`, `hour12`, `currency`, `useGrouping` **(uncommitted, was `useGroupping`)**, `numberDecimals`, `firstDayOfWeek`; `FormatsInput`/`currentFormats` read the old key `useGroupping` and map it to `useGrouping` unless the current key is also present (`packages/shared/src/format.ts:31-42`; mobile applies it to the stored appearance JSON in `apps/mobile/src/appearance.ts:28`) (client defaults equal the server defaults `en-GB`, `Africa/Nairobi`, `medium`, false, `KES`, true, 2, 1); `normalisePhone` turns `+254712345678`/`254...`/`712345678` into `0712345678`; `phoneError` requires `^0[17]\d{8}$`; `percentText` caps display at `999%+` |
| Not in shared | no `/setup` or `/revenue` client, (permission keys now ARE in shared: `packages/shared/src/permissions.ts` `PERMISSION_KEYS`/`PermissionKey`, **uncommitted**), no `Page<T>` type (defined in `apps/web/lib/types.ts`), no problem/error type (`ApiError` is web-only), no idempotency or conflict helper (web `RevenuePage.tsx` and mobile `queue.ts` each implement it). `packages/shared/package.json` `main`/`types`/`exports["."]` name `./src/index.ts`, which does not exist; every consumer imports a subpath (`@xcode/shared/auth`, `/dates`, `/format`, `/revenue`) |

### 4.2 Web: the Next.js proxy is the real client of the API

| Proxy behaviour | Detail (`apps/web/app/api/auth/[...path]/route.ts`, `setup/[...path]/route.ts`, `body.ts`) |
|---|---|
| Auth POST allow-list | `sign-in`, `verify-device`, `setup-pin/request`, `setup-pin/verify`, `setup-pin/complete`, `pin-reset/request`, `pin-reset/verify`, `pin-reset/complete`, `refresh`, `sign-out`, `devices/current/revoke` (rewritten to `devices/<device cookie>/revoke`). `unlock` is NOT reachable from the web. Only GET: `session` |
| Setup allow-list (any method GET, POST, PUT, DELETE) | first segment one of `companies`, `vehicles`, `recurring`, `revenue`, `expense-categories`, `expense-items`, `investment`, `history`, `preferences`, `appearance`, `people`, `organization/logo`, `organization/settings` (+ `/organization`, `/localization`, `/branding`, `/securityPolicy`, `/businessDate`), `access/catalog`, `access/me`, `access/roles`, `access/scope-options`; then any further single-segment steps; forwarded to `{API_URL}/setup/<same path>` with the original query string. Segments `""`, `.`, `..` or containing `/` or `\` are 404 |
| Request to the API | `Authorization: Bearer <cookie access>`; `X-Request-ID: <uuid>`; `X-Forwarded-For: <one address>` only when env `TRUSTED_PROXY_HOPS` > 0 (the Nth entry from the right of the browser's XFF, validated as an IP); `Content-Type: application/json` ONLY when a non-empty body is forwarded (an empty body is never forwarded because `fetch` would label it `text/plain` and the API answers 415); `cache: no-store`; 15 s timeout |
| Auth body built by the proxy | `{ phoneNumber, email, pin, code, deviceId, refreshToken }` with `deviceId` = cookie `device` or a new UUID, `refreshToken` = cookie `refresh` or `""`; the browser's fields must be strings (else treated as `""`) and phone <= 20, email <= 320, pin <= 8, code <= 6, otherwise 400 `{status:"invalid_request"}` |
| What it needs back (auth) | HTTP < 500 and a JSON object body with a string `status`; otherwise (empty 401/403/429 body, non-JSON, no `status`) it answers **503** `{status:"service_unavailable", requestId}`. It forwards `status`, `retryAfterSeconds` (number), `developmentCode` (non-production only), `maskedEmail`, `minimumPinLength` (number) and the upstream HTTP status; tokens never reach the browser |
| Cookies set | `device` (device id; 365 days when "remember this device", else session), `remember` (`1`/empty), `access` (max-age = JWT `exp` minus now, default 600 s), `refresh` (90 days when remembered, else session); all `HttpOnly`, `SameSite=Strict`, `Path=/`, `Secure` in production. `access` and `refresh` are cleared (max-age 0) on a successful `sign-out`/`devices/current/revoke` and on a `refresh` answered 401. `device`/`remember` are set when a trusting call succeeds (`verify-device`, `setup-pin/complete`, `pin-reset/complete`) or when no device cookie existed |
| Setup response handling | upstream status >= 500 => 503 `{status:"service_unavailable", requestId}`; otherwise the upstream status, body and `Content-Type` (e.g. `application/problem+json`) are returned with `Cache-Control: no-store` **(uncommitted)** and `X-Request-ID`; fetch has already decoded a Brotli or Gzip body, so the upstream `Content-Encoding` and length headers are NOT carried over (`apps/web/app/api/setup/[...path]/route.ts:135-142`). No `access` cookie => proxy answers 401 `{status:"authentication_failed"}` without calling the API |
| Other proxy limits | request bodies > 1 MiB => 413 `{status:"payload_too_large"}`; an `Origin` header that does not match the host => 403 `{status:"invalid_request"}`; path not allowed => 404 `{status:"invalid_request"}` |

### 4.3 Web data layer: status codes and fields the screens branch on

| Mechanism | Behaviour |
|---|---|
| `apiRequest(path)` (`apps/web/lib/data/request.ts`) | calls `/api/<path>` with `Content-Type: application/json`; body parsed as JSON (empty/invalid => `{}`); on non-2xx throws `ApiError(message, status, body)` where message = `body.detail`, else for 403 `Your access does not include this. Ask your admin if you need it.`, else `body.title`, else `The request could not be completed.` A network failure => status 0 `Unable to reach the server. Check your connection.` |
| 401 handling (`apps/web/lib/session.ts`) | on a 401 the browser POSTs `/api/auth/refresh` with body `{}` once (shared by concurrent calls) and retries the original request once; a second 401 raises the session-expired event (back to sign-in). `GET /api/auth/session` on load uses the same one-refresh rule |
| Retry on reads (`retry.ts`) | `useResource`/`useStreamedList` retry on network failure or status 503 or 0, after 1000 ms then 3000 ms; no other status is retried |
| Paged lists (`useStreamedList`) | requests `?page=N&pageSize=P` (P = 25, or 100 for expense categories) from page 1 until `items.length >= total` or a page comes back empty; needs `items` to be an array and `total` a number |
| 409 on revenue save | reads `body.current` (a cell) else re-reads `GET setup/revenue?weekStart=<date>&vehicleId=<guid>` and takes that day's cell; `Replace with mine` resends with `current.version` |
| 400 on revenue save | `detail` is shown (the `earliestMissing` branch went with the refusal in 9276c51) |
| HTML interception | a 2xx answer with `Content-Type: text/html` from `/api/*` is treated as a bot-check page (`SecurityCheckError`); no API response may be HTML |
| Session | `fetchWithSession("/api/auth/session")` => `{userId, firstName, lastName, role, permissions}`; `can(p)` is `permissions.includes(p)` |
| Bodies the web sends | companies `{name}` (create, rename), `{}` (archive, restore); vehicles `{registration, companyId, weeklyTarget, joinedOn}`, retire `{leftOn}`, restore `{returnedOn}`; recurring `{name, kind, amount, frequency, day, lastDay, start, end, allocations:[{vehicleId, amount}], expenseItemId, note, month}`, stop `{confirmed:true, reason}`, restore `{}`; expense catalog `{name, bucket}` / `{name}`; investment `{date, description, amount}`; people `{firstName, lastName, email, phoneNumber (national form), role, scopeMode, companyIds, vehicleIds, permissions, approvalLimit, version}`, activate/deactivate `{version, reason?}` (deactivate `reason` required), sign-out no body; organization section `{value}`, business date `{value: "yyyy-MM-dd" or null}`, logo `{dataUrl}` / DELETE; preferences = the whole object read from GET; revenue `{amount, reason, note, version}`. The web never sends a typed `reason` for companies, vehicles, recurring create/update or organization settings (the server writes it) |
| Screens that read the `Problem` | people lifecycle/edit 409 shows `title` `Settings changed. Reload before saving.` (no `detail`); settings sections show `detail` of the `{detail}` bodies; a 403 without `detail` shows the fixed access message above |

### 4.4 Mobile (Expo / React Native)

| Topic | Facts |
|---|---|
| Base URL and timeouts | `${EXPO_PUBLIC_API_URL}/auth/<op>` and `${EXPO_PUBLIC_API_URL}/<path>`; 15 s abort; any fetch failure => "offline" (a hung or refused call is offline); HTTPS required in release builds |
| Auth request | always sends all six `AuthRequest` fields (`email:""`, `phoneNumber`, `pin`, `code`, `deviceId`, `refreshToken` from the stored session) and `Authorization: Bearer <stored accessToken>` when a session exists (even on `sign-in`) |
| Authorized calls | `apiGet(path)` and `apiPutResult(path, body)`: Bearer token; on 401 one renew (`POST auth/refresh`) then one retry; 401 again or no session => session ended. `apiGet` throws `ServerError` for >= 500 and otherwise `Error(detail or title or "The request could not be completed.")`. `apiPutResult` returns `{status, body}` for every HTTP outcome |
| Renew result | `status === "authenticated"` and `accessToken` present, else session ended; refresh answered 401 or 403 => session ended; other failures => server error (session kept) |
| Unlock fallback | on `unlock`: network error or HTTP >= 500 => offline PIN check; HTTP 401 => wrong PIN (counted locally); `paused` => timer from `retryAfterSeconds` (default `lockoutMinutes * 60`) |
| Calls made | `POST auth/{sign-in,unlock,verify-device,setup-pin/*,pin-reset/*,refresh,sign-out}`, `POST auth/devices/{deviceId}/revoke`, `GET auth/session`, `GET setup/appearance`, `GET setup/access/catalog`, `GET setup/revenue[?weekStart=&vehicleId=]`, `GET setup/revenue/dashboard?period=today`/`week`/`month`, `PUT setup/revenue/{vehicleId}/{date}` |
| Fields read | session: `userId`, `firstName`, `lastName`, `role`, `permissions`. Appearance: `organizationName`, `settingsVersion`, `businessDate`, `branding{displayName, logoAlt, primary, secondary, accent, logo}`, `formats`, `themeMode`, `reducedMotion`, `fontScale`, `lockoutThreshold`, `lockoutMinutes` (accepted only when integers 3..10 and 1..60). Catalog: `name`, `items[{key, label, needs}]`. Week/dashboard/cell: all fields in 3.6 |
| Secure-store JSON that must stay compatible | `xcode.device` (UUID string), `xcode.session` `{phoneNumber, accessToken, refreshToken, lastOnlineAt?}`, `xcode.person` `{userId?, phoneNumber, firstName, lastName, role, permissions[], pinLength (4..8), lockoutThreshold?, lockoutMinutes?}`, `xcode.pin-check` `{version:2, salt (hex), hash (hex PBKDF2-SHA256, 100 000 iterations)}` (legacy v1 SHA-256 of `salt:pin`), `xcode.offline-tries` `{count, pausedUntil}`, `xcode.capture-list` `{owner, weekStart, weekThrough, currentWeekStart, businessDate, vehicles[{id, registration, companyName, days[]}], savedAt}`, `xcode.appearance` (the appearance response), `xcode.revenue-queue.<userId>` `{used:"0/1 string"}` and `xcode.revenue-queue.<userId>.<slot>` queue entry (3.6). The queue owner key is the API `userId`, so user ids must be preserved |
| Device id | `Crypto.randomUUID()` generated once, stored; the web uses `crypto.randomUUID()` in a cookie. The API treats it as an opaque string of 1..128 characters |

### 4.5 Fields the clients read, per endpoint (from the files read)

| Endpoint | Web reads | Mobile reads | Sent but not read by either (in files read) |
|---|---|---|---|
| `GET auth/session` | `userId`, `firstName`, `lastName`, `role`, `permissions` | same | none |
| `GET setup/appearance` | `organizationName`, `settingsVersion`, `businessDate?`, `branding.*`, `formats.*` (incl. `firstDayOfWeek`, `weekNumbering`, `direction`), `themeMode`, `reducedMotion`, `fontScale` | all of those plus `lockoutThreshold`, `lockoutMinutes` | `lockoutThreshold`, `lockoutMinutes` (web) |
| `GET setup/organization/settings` | `organization.{name,slug,businessDate}`, `effectiveBusinessDate`, `calendarDate`, `localization.*`, `branding.{displayName,legalName,logoAlt,supportEmail,domain,primary,secondary,accent}`, `securityPolicy.*` | not used | `effective`, `organization.{id,settingsVersion}`, all `organizationId`, `branding.{logoLight,logoDark,favicon,termsUrl,privacyUrl}` |
| `GET setup/preferences` | `locale`, `timeZone`, `hour12`, `themeMode`, `reducedMotion`, `fontScale`, `allow*Override`, `organization.{locale,timeZone,hour12}` | not used | `organizationId`, `userId` |
| `GET setup/companies` | `id`, `name`, `vehicleCount`, `active`, `archivedOn` | not used | none |
| `GET setup/vehicles` | `id`, `companyId`, `companyName`, `registration`, `joinedOn`, `leftOn`, `active`, `weeklyTarget`, `targets.*`, `recurringItems`, `away.*` | not used | none |
| `GET setup/recurring` | `id`, `name`, `kind`, `amount`, `activeAmount`, `frequency`, `day`, `lastDay`, `start`, `end`, `stoppedFrom`, `allocations.*`, `partial`, `expenseItemId`, `expenseItemName`, `bucket`, `note`, `month` | not used | `versionId`, `revision` |
| `GET setup/history` | `items[].{version,section,entityId,reason,occurredAt,actorId,actorName,before,after}`, `total` | not used | `hasMore`, `nextBefore` **(uncommitted)**; no client sends `before` or `includeTotal=false` yet |
| `GET setup/vehicles/{id}/report` | every field incl. `costs` | not used | none |
| `GET setup/expense-categories`, `expense-items/options` | all fields | not used | none |
| `GET setup/vehicles/{id}/investment` | all fields | not used | none |
| `GET setup/people`, `access/*` | `Person` fields incl. `version`, `otherCompanies`, `otherVehicles`, `hasPin`; roles `id,name,permissions`; catalog; scope options; `access/me` | catalog only | none |
| `GET setup/revenue` | all fields of `RevenueWeek`; **(uncommitted)** `RevenuePage.tsx` reads `firstGap` (`:137`) and `dayTotals[].{date,amount}` (`:369`) and pages through `truncated`/`totalVehicles` via the shared helpers | all fields except the new ones (the phone rebuilds its week from its saved capture list and does not read `dayTotals`, `firstGap` or the paging fields) | `dayTotals[].expected`, `pageNumber` (in the files read) |
| `GET setup/revenue/dashboard` | figures; `period`, `businessDate` | same | `from`, `through` (not seen being read) |
| `PUT setup/revenue/...` | `409.current`, `detail`, `title` | same, plus `status` of every outcome | none |
| any non-2xx | `detail`, `title` (and `status` via HTTP) | `detail`, `title`, `current` | `type`, `traceId`, `requestId` |

### 4.6 Flags: expectations the API does not obviously meet, and unused output

| # | Observation | Where |
|---|---|---|
| 1 | The web proxy converts any non-JSON or status-less upstream answer to 503. An empty-bodied 429 (rate limit) or 401 (JWT) on `/auth/*` therefore reaches the browser as 503 `service_unavailable`; the shared message for HTTP 429 ("Too many requests. Please wait a minute.") is only reachable on mobile | `apps/web/app/api/auth/[...path]/route.ts:182-190`, `packages/shared/src/auth.ts:121-122` |
| 2 | Mobile handles HTTP 429 on the revenue PUT (stops the round, counts an attempt) but the API never rate limits `/setup/**` | `apps/mobile/src/revenue/queue.ts:336`, `Program.cs:93-98` |
| 3 | Mobile re-reads a conflicted day with `weekStart = date - 6 days` and then looks for that date in the returned week. The API turns any date into its organization week, so the cell is found only when `date` falls in the week that contains `date - 6` (that is, when `date` is the last day of its week); otherwise the conflict is stored without the saved value | `apps/mobile/src/revenue/queue.ts:263-276`, `RevenueRepository.cs:20` |
| 4 | Mobile comment: "The API rejects a request with any field missing". The server defaults omitted fields to `""` and rejects only explicit `null` | `apps/mobile/src/lib/api.ts:81`, `AuthEndpoints.cs:78-79` |
| 5 | The `rememberDevice` field is in the shared `AuthRequest` but is consumed by the web proxy and never sent to the API | `route.ts:135-166` |
| 6 | Web type `Person.approvalLimit?: number` while the API writes `null` | `apps/web/lib/types.ts:66`, `AccessContracts.cs:17` |
| 7 | `AuthStatus` has no `payload_too_large`, which the web proxy emits (413) | `route.ts:120` |
| 8 | History `before`/`after` casing: the web humanises keys so both `WeeklyTarget` and `weeklyTarget` work, but it hides keys by pattern (`Id`, `Version`, `...Id(s)`); a port that renames keys changes what is hidden or shown | `apps/web/components/setup/HistoryPage.tsx:49-52` |
| 9 | The mobile app reads `lockoutThreshold`/`lockoutMinutes` from `setup/appearance` (any member may read it), which is why those two fields sit next to display settings | `Application/Settings/OrganizationSettingsUseCases.cs:90-92` |
| 10 | `GET /auth/session` returns the permissions in the TOKEN, not the live ones; after an access change the first call after the SecurityVersion bump is a 401, the clients renew, and the session then reflects the change | `AuthEndpoints.cs:57-64` |

### 4.7 Tests that already pin this contract (reusable against the Python API)

| File | What it pins |
|---|---|
| `tests/api/Phase1ContractTests.cs` | every property name, JSON kind, nullability and status code the Phase 1 web and phone read, with "new properties are fine, renamed/re-cased/removed/retyped fail" |
| `tests/api/OpenApiTests.cs`, `OperabilityTests.cs`, `ForwardedClientTests.cs` | OpenAPI document, request-id, 500 body, health routes, revoked sessions, rate limit and forwarded address |
| `tests/api/AuthTests.cs` | lockout, enumeration resistance (byte-equal answers), code limits, refresh rotation, PIN rules |
| `tests/api/RevenueCaptureTests.cs` and other `Revenue*Tests.cs` | 409 `current`, the week's `earliestMissing`, idempotent replay, permission cases |
| `apps/web/tests/proxy.test.ts`, `SetupProxy.test.ts`, `packages/shared/tests/auth.test.ts`, `apps/mobile/tests/queue.test.ts`, `auth.test.tsx` | proxy allow-lists and cookie rules, shared client behaviour, mobile replay and auth flows |

---

## 5. Naming audit

The product is **xcode** (shown as `XCODE`; npm scope `@xcode`; JWT issuer `xcode-api`, audience `xcode-clients`; client storage keys `xcode.*`).

### 5.1 API names that do not match the product

| What | Name used | File |
|---|---|---|
| .NET project / assembly | `Auth.Api` (also the default OpenAPI title, `Auth.Api \| v1`, framework default, unverified) | `apps/api/Auth.Api.csproj` |
| Namespaces | `Auth.Api`, `Auth.Application`, `Auth.Application.Setup`, `Auth.Application.Revenue`, `Auth.Domain`, `Auth.Domain.Setup`, `Auth.Infrastructure`, `Auth.Infrastructure.Setup` | all of `apps/api` |
| Test project / namespace | `Auth.Tests` | `tests/api/Auth.Tests.csproj` |
| DbContext | `AuthDb` (holds the whole domain: companies, vehicles, revenue, settings, not only auth); `AuthDbModelSnapshot`, `AuthDbDesignFactory` | `apps/api/Infrastructure/AuthDb.cs`, `Migrations/AuthDbModelSnapshot.cs` |
| Config | section `Auth` (`Auth:SigningKey`, `Auth:Issuer`, `Auth:Audience`, `Auth:TrustLifetimeDays`; env `Auth__SigningKey`), connection string name `ConnectionStrings:Auth`, default database name `XCode` (mixed case) | `appsettings.json`, `Program.cs:22,37` |
| Classes | (`AuthService` was split in phase 4 to 6 into `SignInService`, `PinSetupService`, `SessionService`, `AuthCodes`, `SessionTokens`, `AuthAccounts`, `AuthDevices`, `AuthPolicy`, `AuthUnitOfWork`), `AuthGate`, `AuthOptions`, `AuthRequest`, `AuthResponse`, `AuthResult`, `AuthSessionResponse` (the last four are wire DTOs whose names show in OpenAPI) | `Application/Auth*.cs`, `Application/Authentication/*.cs`, `Infrastructure/AuthGate.cs`, `Infrastructure/AuthUnitOfWork.cs`, `Api/AuthEndpoints.cs` |
| Class with a lower-case name | `organizationContext` | `Infrastructure/OrganizationContext.cs:8` |
| Misspellings in code | `CurrentOganizationId` (`AuthDb.cs:9`), `OccuredAt` on `AuditEvent` (`Domain/Access.cs:48`), comment "authroization" (`Application/OrganizationPort.cs:32`) |  |
| Misspelling on the WIRE (fixed in phase 6, **uncommitted**) | was `useGroupping`; now `useGrouping` in localization, `EffectiveFormats`, `Formats` in shared, the clients and the change-log reason key. The old name stays as an input alias on PUT localization and as a second output field in `formats` until released apps are retired; stored change-log text and stored mobile appearance JSON may still contain `useGroupping` | `Domain/Organization.cs:157,341,345-348`, `packages/shared/src/format.ts:15,31-42`, `Application/Settings/SettingsSections.cs:35-38` |
| Brand defaults | `OrganizationBranding.DisplayName/LegalName/LogoAlt` default `XCODE`; web fallback `document.title = "XCODE"`; seeded org names `Demo Fleet` / `My fleet`, slugs `demo-fleet` / `my-fleet` | `Domain/Organization.cs:191-195`, `apps/web/lib/appearance.ts:131` |
| Email text | the verification email prints the raw enum name: `Your NewDevice code is ...`, `Your FirstSetup code ...`, `Your PinReset code ...` | `Infrastructure/Security.cs:110-111` |

### 5.2 One concept, several names (API, shared, web, mobile)

| Concept | Names in use |
|---|---|
| Scheduled expense or saving | route and DTO `recurring` (`/setup/recurring`, `RecurringDto`, `SaveRecurring`, `RecurringItem`), permission keys `commitments.view`/`commitments.manage` and card `dash.commitments`, UI and reasons "scheduled expenses and savings"; op ids `...SetupRecurring` |
| Change log | route `history`, permission `audit.view`, UI "Change log", entity `OrganizationSettingsVersion` (the log) vs `AuditEvent` (a separate append-only audit table that no endpoint reads), field `version` = the organization `settingsVersion` at that moment |
| Ending something | company `archive`/`archivedOn`; vehicle `retire`/`leftOn` (UI "left the fleet"); expense category/item and recurring `stop`/`stoppedOn`/`stoppedFrom`; person `deactivate`/`active`; `restore` is the undo for all of them, and `POST /setup/recurring/{id}/restore` is really "cancel a pending stop" (op id `CancelSetupRecurringStop`) |
| Signed-in person | API `AuthSessionResponse`; shared `AuthenticatedPerson` / `PersonIdentity`; web `Session`; mobile `StoredPerson`, `AuthSession` in test comments; people list `PersonDto` / web `Person` |
| Weekly target | `weeklyTarget` (vehicle, save body) vs `targets[].weeklyAmount`; daily expectation `expected` |
| Money out | `moneyOut` and `costs` (same number); `cost` also means recurring `kind` 1; `bucket` vs expense `category` (the retired `category` field) |
| Dates | held `organization.businessDate`, `effectiveBusinessDate`, `appearance.businessDate`, `revenue.businessDate`, `dashboard.businessDate`; `calendarDate` is a different thing; "today" in code means the business date |
| Version | `settingsVersion` (organization, appearance), `version` (membership, revenue record, change-log entry), `revision` (target, recurring version) |
| Paging | request `page`/`pageSize`, response `pageNumber`/`pageSize`/`total` |
| Phone | `phoneNumber` everywhere on the wire; UI "mobile number"; stored normalised `+254...`, clients send `07...` |
| Auth operations | `setup-pin/*` (UI "first time"), `pin-reset/*` ("Forgot PIN"), `unlock` (same handler as `sign-in`), mobile alias `revoke-device` and web alias `devices/current/revoke` for `devices/{id}/revoke` |
| Section keys | change-log `section`: `companies`, `vehicles`, `investment`, `expenses`, `recurring`, `people`, `revenue`, `organization`, `businessDate`, `localization`, `branding`, `securityPolicy`, `logo` (camelCase and plural mixed); route group `/setup` also holds revenue, people, appearance, preferences |
| Permission prefixes vs routes | `invest.*` vs route `investment`; `dash.*` vs "Dashboard"; `commitments.*` vs `recurring`; `expenses.setup` vs `expense-categories` |
| Revenue no-earnings reason | revenue reason label `No Crew` (wire label, accepted input) vs `NoCrew` (enum name, accepted input alias, stored in history snapshots) |
| Duplicated TS types | `Appearance` (web `lib/appearance.ts`, mobile `appearance.ts`), `PermissionGroup` (web `lib/types.ts`, mobile `shell/access.ts`), `Page<T>` (web only), revenue types (shared) |
| Shared package | name `@xcode/shared`; `main` points at a missing `src/index.ts` while consumers use subpaths | `packages/shared/package.json` |

---

## 6. Open questions and ambiguities

| # | Question | Pointer | Why it matters |
|---|---|---|---|
| 1 | Exact bodies of framework-generated errors (401 JWT challenge, 404 no route, 405, 400/415 binding failures) in Production: empty body is assumed, ProblemDetails is possible | `Program.cs:163`, `Api/OpenApiDocumentation.cs:27-28` ("401 with no body") | web proxy turns an empty `/auth/*` answer into 503; clients tolerate empty bodies |
| 2 | Whether `Results.Problem` bodies carry `traceId` / `requestId` (assumed not) and the exact `type` URLs | `Api/SetupEndpoints.cs:32-36`, `Program.cs:131-136` | no client reads them; tests assert them only on the 500 path |
| 3 | Instant format: `+00:00` vs `Z`, fractional digits (assumed 7, trimmed) | `Domain/Setup/OrganizationSettingsVersion.cs`, `SetupModel.cs:88-91` | clients use `new Date(value)`, either works |
| 4 | JWT `permission` claim: array for 2+ values, scalar for exactly 1 | `Infrastructure/Security.cs:84` | only matters if a client ever decodes the token (none does except `exp`) |
| 5 | `ArgumentException` messages with a parameter name get a ` (Parameter 'value')` suffix (time zone message) | `Domain/Organization.cs:18` | the suffix reaches the UI as `detail` |
| 6 | `PUT .../settings/organization` with a non-object `value` throws a `JsonException` that no filter maps (probably 500) | `Application/Settings/SettingsSections.cs:99` (`OrganizationDetailsSection`), `Application/Settings/OrganizationSettingsUseCases.cs:33-47` | unspecified edge; for the three merged sections a non-object `value` is a 400 (`Send the section's settings as an object.`, `SettingsSections.cs:56-57`), only `organization` can still raise a `JsonException` |
| 7 | Time-zone ids: .NET resolves IANA (and on Windows hosts also Windows ids) depending on the host; tests only resolve `UTC` under invariant globalization | `Domain/Organization.cs:16`, `tests/api/OrganizationSettingsTests.cs:120-122` | Python `zoneinfo` accepts IANA only; existing data may hold other ids |
| 8 | Ordering and matching rely on SQL Server collation: `OrderBy(Name/Registration/LastName)`, case-insensitive `LIKE` for history `text`, uppercase `NormalizedName` uniqueness | `Infrastructure/Setup/SetupRepository.cs` (many), `:360` | PostgreSQL collation and `upper()` differ; clients re-sort only some lists |
| 9 | `GET /setup/access/roles` is a GET that writes (creates missing roles) and runs in a serializable transaction | `Application/`AccessUseCases.cs:17-24` | keep, or make roles pre-seeded |
| 10 | Rate limit covers `GET /auth/session` and the device revoke, and shares one partition for all web users unless `TRUSTED_PROXY_HOPS` and `ForwardedHeaders:KnownProxies` are set | `Api/AuthEndpoints.cs:26,56`, `apps/web/app/api/body.ts:50-61` | 30 requests per minute across all web users by default |
| 11 | **(uncommitted)** `GET /setup/history` cursor and `includeTotal`, `HistoryPage`, `OrganizationSettingsVersion.vehicleId` and the `ChangeLogVehicle` migration are another session's in-flight work; no client uses them yet | `Api/SetupEndpoints.cs:132-141`, `Application/Setup/SetupContracts.cs:19-21` | the final shape may change |
| 12 | Change-log `before`/`after` casing (PascalCase for default-serialised snapshots, camelCase for organization sections) is an accident of serializer options, yet the web renders it | `Application/*UseCases.cs` `Snapshot`, `Application/Settings/SettingsText.cs:11` | keep key names stable or accept label changes |
| 13 | Decimal text: SQL Server returns scale-2 decimals, so `1500.00` is written; JS reads the same number | `Infrastructure/*Model.cs` precision (14,2) | Python must emit numbers, not strings |
| 14 | `X-Request-ID` is echoed with no length or character validation | `Program.cs:153-156` | a port may sanitise; tests only check echo of a UUID-like value |
| 15 | Behaviour for `ValidateWrites` failures (`Cross-organization write rejected.` => 403) and the `InvalidOperationException` guards (=> 500) | `Infrastructure/OrganizationModel.cs:87-114`, `Setup/SetupModel.cs:122-133` | status mapping must match |
| 16 | `AuditEvent` rows are written but no endpoint reads them | `Application/OrganizationPort.cs`, `Infrastructure/OrganizationRepository.cs:104-114` | decide whether the table is needed |
| 17 | The dev-only `developmentCode` appears only when the environment is Development and the connection string is local | `Program.cs:29-39` | must stay off in production |
| 18 | Not opened (see below): web components `RecurringPage`, most of `AppShell`, `VehiclesPage`, `RevenuePage`, `RecurringEditor` and mobile `RevenueScreen`, `steps.tsx`, `screens.tsx`, `vault.ts`, so "field not read" statements in 4.5 are limited to the files read | n/a | verify before deleting any response field |

Files read in full: all of `apps/api/Program.cs`, `Api/*.cs`, the listed `Application` contract files, `AuthService`, `AccessUseCases`, the setup and revenue use cases, `SetupRepository`, `RevenueRepository`, `SetupExecution`, `Security.cs`, domain files, the four named API test files plus `AuthTests`, `AuthFactory`, `OrganizationSettingsTests`, `AppearanceTests`, parts of `RevenueCaptureTests`, `AccessAndSetupTests`, `AccessLifecycleTests`; `packages/shared/src` and `tests/auth.test.ts`; web proxies, `lib/*`, `AuthPanel`, and the API-call regions of the other web components; mobile `api.ts`, `storage.ts`, `queue.ts`, `week.ts`, `types.ts`, `AuthFlow.tsx`, `session.ts`, `appearance.ts`, `access.ts`.

---

## Drift log (phases 4 to 6)

Written 2026-10-08 against the working tree on branch `fix/format` (HEAD `3253914`). The .NET code is the source of truth; where this list and an older paragraph above disagree, this list wins. **(uncommitted)** = the fact exists only in modified or untracked files (remediation phase 6 is still in flight in this tree); unmarked facts are committed. Petty cash (`Api/PettyCashEndpoints.cs`, `Application/PettyCash*.cs`, `Domain/PettyCash.cs`, the two petty cash migrations) is not inventoried here, see `inventory-petty-cash.md`.

1. `GET /setup/revenue` had no paging: it now takes `page` and `pageSize`, validated by `SetupPagination.Validate` (400 `Page must be 1–100000 and page size 1–100.`); with neither it lists page 1 of up to 500 vehicles (`RevenueWeekPage.LegacyLimit`), `pageNumber` 1, `pageSize` 500, and sets `truncated` only above 500; with either it pages (other defaults: page 1, size 100) and `truncated` is false; a `vehicleId` request is never paged or validated for paging. `Application/RevenueContracts.cs:105-121`, `Application/RevenueUseCases.cs:13-16`, `Api/RevenueEndpoints.cs:40-44`, `tests/api/RevenueWeekPagingTests.cs:53-230`. **(uncommitted)**
2. `RevenueWeekDto` had 9 properties: it now has 15, the new ones appended in this order: `pageNumber` int, `pageSize` int, `totalVehicles` int, `truncated` bool, `dayTotals` `[{date, amount, expected}]` x 7, `firstGap` `{vehicleId, date}` or null; `totalAmount`, `totalExpected`, `percent`, `dayTotals` and `firstGap` cover the whole filtered scoped grid on every page, and `firstGap` is not permission-gated beyond `revenue.view`. `Application/RevenueContracts.cs:82-103`, `Infrastructure/RevenueRepository.cs:255-325`, `RevenueWeekPagingTests.cs:174-175`. **(uncommitted)**
3. Revenue cell `status` was a plain string in a DTO; it is now the enum `CellStatus` with a per-type `JsonStringEnumConverter` whose wire values are exactly `none|future|missing|amount|reason` (every other enum stays numeric, so 1.3 no longer says "no string-enum converter"). `Application/RevenueContracts.cs:19-28`, `tests/api/PermissionKeysTests.cs:61-74`, `packages/shared/src/revenue.ts:1-2`. **(uncommitted)**
4. Dashboard figures were summed from loaded records: they are now aggregated by the database (one row per vehicle) and cached for 60 s per (organization, settings version, business date, period, company, scope hash) by `RevenueDashboardCache`; `RevenueUseCases.Visible` still masks per request after the cache. The response shape and the maths are unchanged. `Infrastructure/RevenueRepository.cs:88-156`, `Infrastructure/RevenueDashboardCache.cs:16-109`, `Application/RevenueContracts.cs:123-135`, `tests/api/RevenueDashboardCacheTests.cs`. **(uncommitted)**
5. Change log `GET /setup/history` (before, hasMore, nextBefore, includeTotal) was already described here and was re-verified unchanged: `before` < 1 is 400 `Before must be a change log version.`, `before` ignores the `page` offset, `HistoryEntry` has no `vehicleId`. New: section `pettycash` exists and scoped viewers see it only for visible vehicles. `Api/SetupEndpoints.cs:132-141`, `Infrastructure/Setup/SetupRepository.cs:291-336`, `Application/Setup/SetupContracts.cs:17-21`. **(uncommitted)**
6. Organization settings endpoints did the work and took `AuthDb`; they are transport only and the work is in `OrganizationSettingsUseCases`; response DTOs are `OrganizationDto`, `LocalizationDto`, `BrandingDto`, `SecurityPolicyDto`, `UserPreferenceDto` with JSON byte-identical to the old entities (only OpenAPI schema names changed). An unknown `{section}` is 404 (`OrganizationSettingsUseCases.cs:37`). `Api/OrganizationEndpoints.cs:17-51`, `Application/Settings/SettingsContracts.cs:28-57`, `tests/api/SettingsContractTests.cs:25-86`, `tests/api/ArchitectureTests.cs:25-41`. **(uncommitted)**
7. Slug refusals: still plain JSON `{ "detail": ... }` with `Content-Type: application/json` (never problem+json), 400 for a bad name or slug and 409 `This organization slug is already in use.`, now returned as results rather than thrown and saving nothing. `Application/Settings/SettingsSections.cs:103,105`, `Api/OrganizationEndpoints.cs:27-28`, `tests/api/OrganizationSettingsTests.cs:220-242`. **(uncommitted)**
8. Settings, logo and preferences writes ran without the unit of work: they now run in `UnitOfWork.Execute` (serializable, change-log collision retry, 409 `Settings changed. Reload before saving.` after four collisions). `Application/Settings/OrganizationSettingsUseCases.cs:33-131`, `Infrastructure/OrganizationRepository.cs:50-92`, `tests/api/ChangeLogAndScopeTests.cs:142-185`. **(uncommitted)**
9. `Organization.ChangeTimeZone` bumped `SettingsVersion` itself: it no longer does, and `SettingsChangeLog.Record` is the only caller of `SettingsChanged()`, so a localization save moves `settingsVersion` by exactly 1 (visible in `GET /setup/appearance`). `Domain/Organization.cs:108-116`, `Application/Settings/SettingsChangeLog.cs:11-19`, `OrganizationSettingsTests.cs:204-217`. **(uncommitted)**
10. Localization field `useGroupping` is now `useGrouping`: `GET /setup/organization/settings` serves only `localization.useGrouping`; `PUT .../settings/localization` accepts `useGroupping` as a legacy input name (the current name wins when both are sent); `GET /setup/appearance` `formats` (and `effective.formats` of the settings response) serves BOTH `useGrouping` and a computed `useGroupping`. Clients: `packages/shared/src/format.ts:15,31-42` (`currentFormats` reads the old key), `apps/mobile/src/appearance.ts:28` (migrates stored appearance JSON), `apps/web/components/OrganizationSettingsView.tsx:47`, `apps/mobile/src/pettycash/format.ts:11`. `Domain/Organization.cs:157,341-348`, `Application/Settings/SettingsSections.cs:35-38,48-67`, `tests/api/OrganizationSettingsTests.cs:78-100`. **(uncommitted)**
11. Permission keys had no single list: `Domain/PermissionKeys.cs:4-53` holds the 40 keys (10 dashboard, 4 revenue, 4 expenses, 6 petty cash, 3 bills, 2 commitments, 2 reports, 9 setup); the catalog, role defaults, dependencies and every permission check use it, and `packages/shared/src/permissions.ts` mirrors it (`PermissionKeysTests.cs:29-45` fails on drift). The catalog content and order (3.2) are unchanged. **(uncommitted)**
12. A refusal naming a permission looked up its label with `Single(...)` and ended as a 500 for a key the catalog does not label: `PermissionCatalog.Refusal(action, key)` now prints the key itself (`Doing that needs the permission "no.such_key".`); wording for known keys is unchanged (`Recording a no-earnings reason needs the permission "Record a no earnings reason".`). `Application/AccessContracts.cs:98-102`, `Application/RevenueUseCases.cs:64-70`, `PermissionKeysTests.cs:54-59`. **(uncommitted)**
13. There was no response compression: `/setup/**` responses are now Brotli (Optimal) or Gzip when `Accept-Encoding` allows (`br` preferred over `gzip`; none = identity), with `Content-Encoding` and `Vary: Accept-Encoding`, for `application/json` and `application/problem+json`; `/auth/**` and health are never compressed. `Program.cs:138-146,164-165`, `tests/api/CompressionTests.cs:53-110`. **(uncommitted)**
14. Health was re-verified unchanged and committed: `/health/live` 200 without a database call, `/health/ready` runs `DatabaseHealthCheck` (`CanConnectAsync`, 10 s timeout, tag `ready`) and answers 503 when the database is unreachable, `/health` is 200 `{"status":"ok"}`. Bodies of the two probes are the framework default text (`Healthy`/`Unhealthy`), content type `text/plain`: no test pins them (only the status codes). `Program.cs:76,175-177`, `Infrastructure/DatabaseHealthCheck.cs:6-22`, `tests/api/OperabilityTests.cs:34-69`.
15. Production startup was described loosely: outside Development and Testing the host refuses to start without `Email:Host`, `Email:From`, `ConnectionStrings:Auth` (messages `Email:Host is required.`, `Email:From is required.`, `ConnectionStrings:Auth is required.`) and a 32-byte `Auth:SigningKey`; starting never creates or migrates the schema; `--migrate` is the only way. `Program.cs:25-27,42-47,188-213`, `tests/api/ProductionStartupTests.cs:34-73`. Committed (phase 3); only the Dockerfile that relies on it is new (entry 22).
16. Citations of `Application/AuthService.cs` (deleted) pointed at code that is now `Application/Authentication/SignInService.cs:11-72`, `PinSetupService.cs:10-48`, `SessionService.cs:10-59`, `AuthCodes.cs:17-63`, `SessionTokens.cs:11-72`, `AuthAccounts.cs:9-65`; the wire contract of A01-A13 is unchanged (re-read against the new files). **(uncommitted)**
17. Device revoke (A12) took its lock on `device:<id>`: it now waits on the ACCOUNT's lock (the user's normalised phone, `SessionService.AccountKey`), falling back to `device:<id>` only when the user row is missing. `Api/AuthEndpoints.cs:50-56`, `Application/Authentication/SessionService.cs:61-63`. **(uncommitted)**
18. A rolled-back or retried auth attempt could mail its code: the code is carried in `AuthResult.Mail` and mailed only after the committed attempt releases the account lock (new-device code before answering with 503 on failure, other codes after the reply). `Infrastructure/AuthUnitOfWork.cs:11-47`, `Infrastructure/AuthGate.cs:7-43` (cap 10 000 keys, idle eviction to 80 percent, semaphores never disposed), `Application/AuthContracts.cs:30-33`. **(uncommitted)**
19. Route count: 10 routes under `/setup/pettycash` were added (`MapPettyCash` between `MapRevenue` and `MapOrganization`), so the always-on total is 80 (+1 conditional); the vehicle report (S23) now includes approved petty cash expenses of the vehicle as Cost postings, so `repairs`/`charges`/`loans`/`moneyOut`/`net` can differ from before, and `PostingDto` gained a last property `source` (`"pettycash"` or null). `Program.cs:173`, `Api/PettyCashEndpoints.cs:18`, `Application/Setup/SetupContracts.cs:69-72`, `tests/api/VehicleReportTests.cs:117-124`. **(uncommitted)**
20. `Program.cs` citations were off by 1 to 15 lines after the compression, petty cash and settings registrations; they were renumbered (route mapping `Program.cs:170-180`, JWT session check `:115-127`, rate limit `:93-98`, startup `:181-240`). Also renumbered or repointed: `Organization.cs`, `AuthDb.cs`, `OrganizationRepository.cs` (`UnitOfWork` now `:48-115`), `OrganizationPort.cs`, `SetupEndpoints.cs`, `RevenueEndpoints.cs`, `AuthEndpoints.cs`.
21. Web proxy: the setup proxy now relays the decoded body and drops the upstream `Content-Encoding` and length headers, adding `X-Request-ID` (needed because the API compresses); shared and web read `firstGap`, `dayTotals` and the paging fields; shared exports `PERMISSION_KEYS`. `apps/web/app/api/setup/[...path]/route.ts:135-142`, `apps/web/components/RevenuePage.tsx:137,369`, `packages/shared/src/revenue.ts:88-141`, `packages/shared/src/permissions.ts:4-47`. **(uncommitted)**
22. Container and restore files exist: `apps/api/Dockerfile` (SDK build with `dotnet restore --locked-mode`, runtime `aspnet:10.0` on a non-Alpine image, `ENV ASPNETCORE_ENVIRONMENT=Production`, `EXPOSE 8080`, entrypoint `dotnet Auth.Api.dll`, comment: each release runs the image once with `--migrate`), `apps/api/.dockerignore`, and `tests/api/packages.lock.json` with `RestorePackagesWithLockFile` in `tests/api/Auth.Tests.csproj`; `apps/api/packages.lock.json` is committed. This inventory has no operational-notes section, so this entry is the note. **(uncommitted)**
23. Statements in other files that this update does not fix because only this document is writable: `inventory-domain.md:20` says every enum goes over the wire as an integer (revenue `CellStatus` is a string).

### Drift after 8 October (measured 2026-10-11 by the revenue prompt against `HEAD` 493bf82 plus the working tree of `fix/web-dropdowns`)

24. Revenue days are captured in any order (commit 9276c51): `RevenueUseCases.Save` lost step 9, the refusal of a new record while an earlier active day is missing (`RevenueEarlierDayMissingException`, 400 with `earliestMissing`, deleted from `Application/RevenueContracts.cs` and from the endpoint filter `Api/RevenueEndpoints.cs:22-34`); the save now goes from the version check straight to the write (`Application/RevenueUseCases.cs:126-151`). A `missing` cell is `canEdit` for anyone holding `revenue.capture`, on any missing day (`Application/RevenueContracts.cs:54-55`). The week still reports each vehicle's `earliestMissing` and `firstGap` unchanged. Clients followed: the mobile queue has no `blocked` state any more (an old stored one reads as `pending`, `apps/mobile/src/revenue/queue.ts:40-52,147-152`) and treats every 400 as `failed` (`:350-360`). Tests: `RevenueCaptureTests.SavingPastAGapIsAllowedAndTheGapStaysVisible`, `EarliestMissingComesFromTheWholeHistoryAndEveryMissingDayCanBeOpened`, `RevenueTests.RevenueCaptureTakesDaysInAnyOrderAndKeepsCorrectionHistory`, `RevenueWeekPagingTests.cs:222-223`, `RevenueComplexityTests.TheWeekFindsTheEarliestMissingDayFromOneAggregateRowWhateverTheHistoryLength`.
25. The revenue 409 with `current` gains a `vehicleId` extension, but only when a day save of several vehicles conflicts (`Api/RevenueEndpoints.cs:26-30`, `RevenueConflictException(current, vehicleId, registration)` in `Application/RevenueContracts.cs:139-148`); a single-cell save (R03) never sets it, and its detail stays `This day was changed after you opened it. Check the current record and save again.`
26. New routes in the revenue group, not in section 2: `GET /setup/revenue/day` (`GetRevenueDay`), `PUT /setup/revenue/day/{date}` (`SaveRevenueDay`, all rows or none, each row by the single-save rules, errors prefixed with the registration; 9276c51, `Application/RevenueDayContracts.cs`, `Infrastructure/RevenueDayQueries.cs`, `tests/api/RevenueDayTests.cs`) and `GET /setup/revenue/export` (`ExportRevenueWeek`, uncommitted, `Application/Reports/ScreenExports.cs`). They belong to `docs/prompts/08b-expenses-reports.md` (drift register rows 3 and 4).
27. `RevenueDashboardCache` changed only to pass the new repository methods through (`Infrastructure/RevenueDashboardCache.cs:99-108`); the dashboard figures, masking and cache key are unchanged. The Python design still has no cache (`docs/05-routines.md` section 7).
