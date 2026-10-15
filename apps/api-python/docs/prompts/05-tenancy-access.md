# Prompt 05: access, people, organization settings, change log

Paste everything below the line into a fresh Claude Code session running Sonnet, started in
the repository root. Requires prompts 00 to 04. Do not run beside prompt 06 (both edit
`container.py`, `main.py`, `application/repositories.py`, `tests/support/fakes.py`).

---

You are implementing the tenant-facing core of `apps/api-python`: the access catalogue,
roles and scope options, people (create, update, activate, deactivate, sign out), the
organization settings sections, logo, appearance and preferences, and the change-log
history, as routines, use cases, HTTP routes and tests. Every refusal sentence the clients
show comes from `http/messages.py`, keyed by the codes the routines raise.

## Read first, in this order

1. `CLAUDE.md`; `apps/api-python/README.md`.
2. `docs/00-principles.md`; `docs/01-architecture.md` (all); `docs/11-naming.md`;
   `docs/03-database.md` sections 3, 4, 5.
3. `docs/06-http-contract.md` sections 1 (all), 2.2, 2.5, 2.9, 3 (cross-cutting, people
   and access, change log, organization), 4, 5.
4. `docs/05-routines.md` sections 1, 2, 4.1, 4.4, 4.8, 6, 7, 8.
5. `docs/04-schema.md` sections 4 (all), 8.
6. `docs/inventory/inventory-http-contract.md` sections 2.3, 2.7, 2.11, 3.2, 3.3, 3.7, 3.9
   (check orders, DTO fields in wire order, snapshots, setting words) and
   `docs/inventory/inventory-domain.md` sections 2.2 (`AC-*`), 2.3 (`OS-*`), 3 (the
   computations for reasons, contrast, effective settings), 5.
7. `docs/inventory/inventory-tests.md` rows for `AccessAndSetupTests`,
   `AccessLifecycleTests`, `OrganizationSettingsTests`, `SettingsContractTests`,
   `ChangeLogAndScopeTests`, `ChangeLogPagingTests`, `PeopleHistoryTests`,
   `AppearanceTests`, `AutomaticReasonTests`, `PeopleQueryCostTests` (the behaviours your
   tests must pin; the query-count rows become statement budgets).
8. The code from prompts 00 to 04, in particular `http/dependencies.py`
   (`current_principal`), `http/errors.py`, `db/session.py`, `db/routines/identity.py`,
   `tests/support/*`, `tests/db/test_tenancy_helpers.py`.

Do not read the C# sources.

## Environment

As prompt 01. `git status` first; write only under `apps/api-python/`.

## Deliverables

### D1 Message catalogue (`http/messages.py`)

- One mapping from every code of `docs/06-http-contract.md` section 3 to its exact
  sentence (parameters formatted from `DETAIL`), the status each code answers, and the
  problem `title` per section 1.6 (B) (`Not permitted in this organization or data
  scope.`, `Record not found in your scope.`, `Invalid setup change`, `Settings changed.
  Reload before saving.`, `A conflicting record exists. Reload before saving.`); the two
  plain `{detail}` answers of `O02`; the revenue titles (used by prompt 07).
- `http/errors.py`: `DomainRefusal` handler builds the problem body from the catalogue
  (`type` `about:blank`, `title`, `status`, `detail` omitted when null, `requestId`,
  extension members from `DETAIL`); a code without an entry is an `IntegrityBug` (500) and
  a failing test.
- Evidence: `tests/unit/test_messages.py` (every entry formats with sample parameters; the
  EN DASH strings byte for byte), `tests/db/test_message_codes.py` (every code raised in
  `db/routines/**/*.sql` has an entry and every entry is raised somewhere; auth codes and
  trigger codes excluded by an explicit list with a reason).

### D2 Snapshot and reason helpers (`db/routines/30_tenancy/`)

- `tenancy.person_snapshot`, `tenancy.settings_snapshot(section)`,
  `tenancy.logo_snapshot` returning `json` with the exact keys and casing of
  `docs/05-routines.md` section 6.2; `tenancy.check_person_grant(...)` implementing the
  owner, holdings, hidden-scope and sign-in-details rules once for create and update.
- Evidence: `tests/db/test_access_routines.py` compares the stored `before`/`after` text
  with literal JSON strings for a created and an updated person; `test_organization_routines.py`
  does the same for each settings section and the logo.

### D3 Access and people routines (`db/routines/30_tenancy/`)

- `api.access_catalog_list`, `api.access_role_list`, `api.access_scope_options`,
  `api.access_my_scope`, `api.people_list`, `api.people_get`, `api.people_create`,
  `api.people_update`, `api.people_set_active`, `api.people_sign_out` per
  `docs/05-routines.md` section 4.1, with the sixteen-step order of
  `inventory-http-contract.md` section 2.3 for create and update and the lifecycle rules
  of S09 to S11.
- The side effects on `identity` rows (security version bump; device and token revocation
  for sign-in-detail changes, deactivation and sign-out) are performed by these routines
  through the `identity.*` helpers of prompt 03, in the same transaction.
- Evidence: `tests/db/test_access_routines.py`: one test per step (named after it), the
  anti-escalation rules (only an Owner grants Owner, cannot edit yourself, only held roles
  and permissions, `access.manage` for single permissions and limits, sign-in-details
  rules), hidden-scope preservation for a scoped caller, visibility of people per caller
  kind (`tenancy.people_visible`), `version` bump and `version_conflict`, `unchanged`
  update without a log row, lifecycle idempotence (`unchanged` without a version), the
  reason sentences, and the identity side effects asserted through
  `api.auth_resolve_session` and the token rows.

### D4 Change log (`api.history_list`)

- Per `docs/05-routines.md` section 4.4: filters, both paging forms, `has_more`,
  `next_before`, `total` on request, visibility predicate `tenancy.change_visible`, people
  redaction for scoped viewers, `actor_name` from the membership (`""` when none).
- Evidence: `tests/db/test_history_routines.py`: each filter alone and combined; `from`/
  `to` as organization-zone day bounds; text search with `%` and `_` taken literally;
  offset and seek paging return the same rows for the same filter; `before < 1`;
  visibility per section for an all-companies viewer, a company-scoped and a
  vehicle-scoped viewer (seed rows through the setup routines of prompt 06 when present,
  else through direct inserts as owner, clearly marked); redaction of `CompanyIds` and
  `VehicleIds`; `total` null when not asked.

### D5 Organization settings, logo, appearance, preferences routines

- `api.organization_settings_get`, `api.organization_settings_set`,
  `api.organization_logo_set`, `api.organization_logo_delete`,
  `api.organization_appearance_get`, `api.preferences_get`, `api.preferences_set` per
  `docs/05-routines.md` section 4.8, including the section merge (top-level keys, legacy
  `use_groupping` accepted, current key winning), `unchanged` when the snapshot text does
  not change, the version moving once per logged save, the time-zone and held-date rule,
  the slug conflict as `XC409 organization_slug_taken`, the effective-value rules and the
  clamped policy, and read-time validation on appearance.
- Evidence: `tests/db/test_organization_routines.py`: each section with a full and a
  partial payload; a wrongly typed value; every validation code of
  `docs/06-http-contract.md` section 3 (organization block) at least once; business date
  null, a date, a future date, `0001-01-01`; localization change with a held date that
  would be in the future in the new zone; the automatic reasons (`Changed the first day of
  the week to Sunday and the currency to USD`, `Set the business date to ...`, `Returned the
  business date to the calendar`, `Changed the branding settings` when nothing differs but
  the object does); `settings_version` +1 exactly once per logged save, 0 on `unchanged`;
  logo signatures for PNG, JPEG, WebP, an SVG, a PNG claiming to be JPEG, 256 KiB plus one
  byte; appearance for a member with each override flag on and off; preferences allow
  flags and the `NULL`-for-disallowed read rule.

### D6 Domain, ports, gateway, fakes

- `domain/tenancy.py` records (`Person`, `PersonSummary`, `AccessRole`, `ScopeOptions`,
  `MyScope`, `HistoryEntry`, `HistoryPage`, `OrganizationSettings`, `Appearance`,
  `Preferences`, the section payload types) and commands; `application/repositories.py`
  `TenancyRepository` Protocol, one method per routine of D3 to D5;
  `db/routines/tenancy.py` `TenancyRoutines`; `tests/support/fakes.py`
  `FakeTenancyRepository` with the parity cases added to `test_fakes_match_routines.py`
  (at least: create and update a person, version conflict, settings save unchanged and
  changed, history paging).

### D7 Use cases and HTTP

- `application/access/*`, `application/organization/*` use cases (one per endpoint row;
  pass-through ones are short), `http/schemas/access.py`, `http/schemas/organization.py`,
  `http/schemas/history.py` with the DTO fields in wire order (`inventory-http-contract.md`
  sections 3.3, 3.7, 2.7) and camelCase aliases, the legacy alias `useGroupping` accepted
  on input and served beside `useGrouping` where the contract says (appearance and the
  settings read), `http/routers/access.py`, `organization.py`, `history.py` with the
  operation ids and tags of `docs/06-http-contract.md` section 2, the optional body of
  S09/S10, the `415` for a wrong content type, the 404 for an unknown settings section, the
  plain `{detail}` answers of O02 and the problem bodies everywhere else.
- Evidence: `tests/api/test_access.py`, `test_people.py`, `test_history.py`,
  `test_organization_settings.py`, `test_appearance.py`, `test_preferences.py`: status
  codes, exact `title`/`detail` strings, DTO property names and order
  (`Phase1ContractTests` rows of `inventory-tests.md`), 401/403/404 refusals, the
  statement budget 2 per request, `X-Request-ID` and the security headers; the people
  side effects visible through `/auth/session` (401 after a role change; refresh succeeds;
  401 on refresh after deactivation).

## Invariants at the end

- Every 400 detail string a client shows comes from `http/messages.py`; no sentence is
  typed in a router, a use case or a routine (grep the routine files for the sentences:
  none).
- Only `tenancy.record_change` writes `tenancy.change_log` and moves
  `settings_version`; a logged save moves it by exactly one.
- Routers contain no branching on domain state beyond the outcome discriminator; use
  cases contain no rule (`docs/01-architecture.md` section 3).
- `domain/` and `application/` import only the standard library; `test_layers.py` green.
- Lint, types, all tests green; `db verify` exit 0; no TODO/FIXME; no plan or prompt ids.

## Verify (paste the outputs into the report)

```
cd apps/api-python
ruff check . && ruff format --check . && mypy
pytest -n auto -q
xcode-api db routines && xcode-api db verify ; echo "exit=$?"
pytest tests/db/test_message_codes.py -q -rA | tail -20
```

## Report format

1. Checklist: one row per deliverable D1 to D7 and per bullet: done or not, `file:symbol`,
   test name.
2. Verify outputs, trimmed.
3. Deviations from `docs/05-routines.md` and `docs/06-http-contract.md` with reasons;
   document lines changed; inventory lines you found wrong and corrected.
4. Items left for later prompts.

## House rules

- Shared tree: `git status` first; edit only under `apps/api-python/`; never revert or
  reformat others' changes; never kill processes you did not start; never bare `git stash`.
- No commits unless the user asks. No AI attribution anywhere.
- No comments unless needed; routine files carry the header the conventions require and
  nothing decorative; no plan or prompt identifiers anywhere.
- Never weaken a test to make it pass. If a document is wrong, fix the document and report
  it.
