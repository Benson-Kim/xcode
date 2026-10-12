# Naming

The product is **xcode**. The .NET code grew out of an authentication bootstrap and still
carries that name in places (`Auth.Api.csproj`, namespace `Auth.*`, `AuthDb`,
`ConnectionStrings:Auth`, `Auth.Tests.csproj`, option section `Auth`). The rewrite uses the
product name for the project and domain words for everything inside it. "auth" survives
only as the name of the authentication feature.

## 1. Fixed names

| Thing | Name |
|---|---|
| Folder (until renamed) | `apps/api-python` |
| Python distribution / package / CLI | `xcode-api` / `xcode_api` / `xcode-api` |
| Container image | `xcode-api` |
| Database | `xcode` |
| Schemas | `identity`, `tenancy`, `setup`, `revenue`, `pettycash`, `expenses` (central expenses), `reports` (report functions, no table), `ops`, `api` |
| Roles | `xcode_owner`, `xcode_api_executor`, `xcode_app`, `xcode_operator`, `xcode_readonly` |
| Settings prefix | `XCODE_` |
| Transaction-local settings (GUCs) | `xcode.organization_id`, `xcode.actor_id`, `xcode.request_id` |
| Operator identity for CLI actions | `XCODE_OPERATOR`, recorded in `ops.operator_actions` |
| Operator connection for CLI user and seed commands | `XCODE_DATABASE_OPERATOR_URL` (role `xcode_operator`) |
| Advisory lock key | `hashtext('xcode.migrate')` |
| JWT issuer / audience | `xcode-api` / `xcode-clients` (unchanged; clients validate nothing by issuer but tokens in flight stay valid across cutover) |
| Test template database | `xcode_template` |
| Log event prefix | none; events are dotted lowercase (`request.completed`, `auth.refused`, `mail.sent`) |

## 2. Domain vocabulary (used for tables, routines, services, schemas)

Taken from the product documents (`docs/design/XCODE_Build Notes_v1.0.pdf`) and the .NET
domain layer; the inventories in `docs/inventory/` list the source names.

| Concept | Name here | .NET name(s) | Note |
|---|---|---|---|
| Person who signs in | `user` | `User` | kept; "person" is the organization-facing word |
| Organization member record | `membership` | `Membership` | |
| Organization member as shown in the app | `person` (`api.people_*`) | People endpoints | |
| Phone-based sign-in secret | `pin` | `Pin` | |
| One-time email code | `verification_code` | `Code`, `VerificationMailer` | |
| Device remembered for a user | `trusted_device` | `TrustedDevice` | |
| Refresh token | `refresh_token` | `RefreshToken` | |
| Security version (invalidates sessions) | `security_version` | `SecurityVersion` | |
| Organization settings bump | `settings_version` | `SettingsVersion` | |
| Organization change history | `change_log` | ChangeLog (Organization) | |
| PSV company (SACCO/operator) | `psv_company` | `PsvCompany` | domain word kept |
| Vehicle | `fleet_vehicle` (table) / `vehicle` (routine noun) | `FleetVehicle` | |
| Vehicle unavailable period | `vehicle_away_period` | `VehicleAwayPeriods` | |
| Expense catalog | `expense_catalog` / `expense_item` | `ExpenseCatalog` | |
| Recurring cost item + schedule | `recurring_item`, `recurring_schedule` | `RecurringItem`, `RecurringSchedule` | |
| Vehicle investment | `vehicle_investment` | `VehicleInvestment` | |
| Dated weekly target of a vehicle | `vehicle_target` | `VehicleTarget` / `FleetVehicle.Targets` | |
| Setup data scope | `setup_data_scope` | `SetupDataScope` | |
| Revenue record | `revenue_record` | `RevenueRecord` | |
| Petty-cash float and its keeper | `holder` (`holder_id`); "float" stays a wire word (`floats`, dashboard `float`) | `HolderId`, `PettyCashFloatDto` | the Python field for the dashboard card is `float_` with alias `float` |
| Petty-cash entry kinds | `cash`, `expense`, `credit` (code table `pettycash.kinds`) | `PettyCashKind` | wire words unchanged; UI says "Cash given", "Credit note" |
| Petty-cash review states | `waiting`, `approved`, `rejected` (code table `pettycash.statuses`, codes 1, 2, 4); sent back is `sent_back_note` on a waiting expense (`docs/15-design-v2-3.md` DEC-21) | `PettyCashStatus` | wire `sentBack` for a sent-back expense |
| Tally window position | `window_position` (`before`, `within`, `after`) | `Period` constants | not the wire `period` (`day`/`week`) |

Where an inventory reveals two names for one concept across API, web and mobile, the
HTTP contract keeps the wire name the clients send today, and the database uses the
vocabulary above; the gateway maps between them in one place.

## 3. Rules

- No "Auth" in project, package, module, schema, table or settings names. `application/auth/`,
  `api.auth_*` and `/auth/...` routes are the feature, which is correct.
- No plan or phase identifiers in code, comments, migration names or routine names.
- Routine names: `api.<area>_<verb>_<noun>`; verbs from a short list: `get`, `list`,
  `create`, `update`, `delete`, `begin`, `finish`, `issue`, `verify`, `grant`, `revoke`,
  `capture`, `set`, `clear`.
- Python: modules snake_case; use cases `<Verb><Noun>` in `application/<area>/<verb>_<noun>.py` with `<Verb><Noun>Command`; repository ports `<Area>Repository`; gateways `<Area>Routines`;
  outcomes `<Noun>Outcome`; errors are nouns (`Conflict`, `NotFound`).
- Settings: `XCODE_<AREA>_<NAME>`; booleans are positive (`XCODE_DEMO_SEED`, not
  `XCODE_DISABLE_...`).
- Tests: `test_<area>_<behaviour>.py`; test functions read as sentences:
  `test_stale_version_is_refused_with_409`.

## 4. Names from the .NET code that are not copied

Collected from the naming audits of the inventories (`inventory-auth.md` section 10,
`inventory-domain.md` section 8, `inventory-http-contract.md` section 5,
`inventory-tests.md`). Wire text (JSON property names, status strings, claim names, mail
text, problem titles) is never renamed; only internal names are.

| .NET name | Problem | Name here |
|---|---|---|
| `AuthDb`, `Auth.*`, `ConnectionStrings:Auth` | the product is xcode; one context held every feature | `xcode_api`, `XCODE_DATABASE_URL` |
| `AuthRequest` (six fields for thirteen routes) | one bag reused everywhere | one request schema per route (`http/schemas/auth.py`), same wire shape |
| `TokenIssuer.Hash` | hashes codes and refresh tokens, not tokens | `keyed_digest` (`security/digests.py`) |
| `User.Version` / `User.SecurityVersion` / claim `version` | three "versions" | column `version` (row), `security_version`; the claim stays `version` |
| `TrustedDevice.DeviceId` | a client-chosen key, not the row id | column `device_id` kept (wire `deviceId`); never called "id" in prose |
| `FailedAttempts`, `UntrustedFailedAttempts` | which devices? | kept as columns (`docs/04-schema.md`); in code `trusted_device_failures`, `untrusted_device_failures` |
| `SignInService.UntrustedAttemptLimit` | constant on a service | `UNTRUSTED_DEVICE_LIMIT` in `domain/policies.py` |
| `CodePurpose.FirstSetup` / `NewDevice` / `PinReset` | enum names double as mail text | `first_setup`, `new_device`, `pin_reset` plus an explicit label map to the three mail words |
| `AuthOptions.DevelopmentMode` (computed from the connection string) | looks like configuration | `XCODE_DEVELOPMENT_CODES`, a real setting refused outside development |
| `AuthDb.Provisioning` (flag that bypasses tenant guards) | hidden mode | `tenancy.enter_organization_as_operator`, explicit and routine-scoped |
| `AuthGate` | a keyed mutex map | row locks and `pg_advisory_xact_lock` in the routines; no process lock |
| `CurrentOganizationId` | typo | `current_organization_id` |
| `PinRules.MinimumLength` versus policy `PinLength` | two minimums | `PIN_FLOOR` (4) and `policy.pin_length` |
| `OrganizationSettingsVersion` (the change-log table) | named after its counter | `tenancy.change_log` |
| `SetupExecution`, `ISetupExecution`, `UnitOfWork` | pipeline plumbing named as a domain thing | the gateway `call(...)` and the use case; no persisted execution |
| `SettingsSectionRegistry` (deleted in .NET) | | section descriptors in `domain/tenancy.py` |
| `useGroupping` (wire) | misspelling kept by the clients | column `use_grouping`; the wire serves `useGrouping` and accepts both (`docs/06-http-contract.md`) |
| `Primary`, `Secondary`, `Accent` columns | reserved word | `primary_color`, `secondary_color`, `accent_color` |
| `VehicleInvestment.Date`, `OccuredAt` | vague, misspelled | `invested_on`, `occurred_at` |
| `RevenueNoEarningsReason.NoCrew` | the snapshot text keeps `NoCrew` | code-table name `no_crew`, label `No Crew`, snapshot name `NoCrew` (section 6.2 of `docs/05-routines.md`) |
| `CancelStop` (route `restore`) | code and route disagree | routine `api.setup_recurring_cancel_stop`, route unchanged |
| test names with phase ids (`Phase1ContractTests`, `Phase1WebSettingsContractTests`) | plan identifiers | `test_contract_*.py` named by the behaviour |

## 5. Permission keys and the words of the design notes v2.29 to v2.33

Permission keys are wire text (the token's `permission` claim, the catalogue, the person
document), so a key that exists keeps its spelling for good, even when its label changes:
released phones gate their screens on it. New keys follow these rules:

- `<module>.<verb>`, lower case, `_` between words (the column `CHECK`
  `^[a-z]+\.[a-z_]+$`).
- The module is the domain word of section 2, not the prototype's abbreviation.
- The verb is the action the right allows, `view` for the module's base right.

The prototype's ids (`pc.see`, `see.vehicles`, `ppl.signin`) are design ids: they appear in
`docs/15-design-v2-3.md` section 3.1 once, mapped to the keys, and never in code.

| Prototype | Key | Why |
|---|---|---|
| `rev.*` | `revenue.*`; `rev.edit` is `revenue.correct` | kept keys |
| `exp.*` | `expenses.*`; `exp.add` is `expenses.capture`, `exp.edit` `expenses.correct` | kept keys; "central expenses" is the module's label |
| `pc.*` | `pettycash.*`; `pc.see` is `pettycash.view`, `pc.view` `pettycash.view_all`, `pc.sendback` `send_back`, `pc.negative` `issue_negative`, `pc.cash_delete` `delete_cash` | the schema word; kept keys; verbs in words |
| `dash.pc` | `dash.pettycash` | kept key |
| `sched.*`, `sav.*` | `scheduled.*`, `savings.*` | the notes' module names, "Scheduled expenses" and "Savings" |
| `rep.*` | `reports.*`; `rep.invest` is `reports.investment` | |
| `see.companies`, `co.*` | `companies.*` | |
| `see.vehicles`, `veh.*` | `vehicles.*`; `veh.target` is `vehicles.target` | |
| `see.items`, `item.*` | `catalog.*` | the expense catalogue of section 2 covers main categories, categories and items |
| `see.people`, `ppl.*` | `people.*`; `ppl.signin` is `people.sign_in` | |
| `set.log` | `audit.view` | kept key |

Retired keys (`dash.capture`, `commitments.view`, `vehicles.manage` and the rest of
`docs/15` section 3.4) keep their names as legacy keys until the last v2.11 phone is gone.

New vocabulary:

| Concept | Name here | Note |
|---|---|---|
| Dated set of seven day targets | `vehicle_target_set` (table `setup.vehicle_target_sets`), wire `TargetSet` | replaces the weekly `vehicle_target` |
| Fleet number | `fleet_number`, wire `fleetNumber` | the notes' `fleet` |
| Main category | `expense_main_category`, wire `mainCategory*` | the top of the three levels |
| How far back a person may change records | `back_limit` (`back_limit_mode`, `back_limit_count`, `back_limit_from`), wire `backLimit`; the words `canChange` | "Can change" in the notes |
| Device token | `device_token` (only its digest is stored: `token_hash`), wire `deviceToken` | never "device id", which stays the client's `deviceId` |
| Lock scopes | "every device" (`failed_attempts`), "new devices" (`untrusted_failed_attempts`) | `docs/07-auth.md` 12.5 |
| Low day | a record with an amount and a reason; the threshold `low_day_threshold`, wire `lowDayThreshold` | "Below 4,000" is `belowThresholdDays` |
| Gap to target | `gap`, its colour `gap_band` (`green`, `amber`, `red`), the setting `gap_amber_percent` | |
