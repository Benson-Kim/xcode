# Prompt 03: identity and tenancy routines

Paste everything below the line into a fresh Claude Code session running Sonnet, started in
the repository root. Requires prompts 00 to 02. May run beside prompt 04 only if the two
sessions touch disjoint files (this one owns `db/routines/**`, `db/routines/*.py` for
identity and ops, `cli/commands/users.py`, `tests/db/**`; prompt 04 owns `security/`,
`application/auth/`, `http/`, `tests/unit/**`, `tests/api/**`, `tests/support/fakes.py`).

---

You are writing the first routines of `apps/api-python`: the helper functions in the data
schemas, the composite types, the eleven `api.auth_*` routines, the operator routines for
users, their typed gateway in `db/routines/`, the CLI user commands that call the operator
routines, and the routine tests on PostgreSQL. Every business rule of sign-in, lockout,
codes, devices, tokens and provisioning lives in these SQL files.

## Read first, in this order

1. `CLAUDE.md`; `apps/api-python/README.md`.
2. `docs/00-principles.md` section 3; `docs/01-architecture.md` sections 3 (`application/`
   ports and repositories, `db/`), 4, 7; `docs/03-database.md` sections 3, 4, 5, 7;
   `docs/04-schema.md` sections 3, 4.1, 4.2, 4.6, 4.8; `docs/11-naming.md`.
3. `docs/05-routines.md` (all of sections 1, 2, 3, 5, 7, 8; skim 4 and 6 for the helpers
   they will need from you: `record_change`, `compose_reason`, `fmt_*`, `join_words`,
   `setting_word`).
4. `docs/07-auth.md` (all; section 3 is the check order of every auth routine, section 4
   the state machine, section 6 the revocation matrix, section 9 the operator commands).
5. `docs/06-http-contract.md` sections 1.3, 1.6 (A), 2.1 (the envelope outcomes your
   routines must make possible), 3 (cross-cutting codes).
6. `docs/inventory/inventory-auth.md` sections 2, 3, 4, 5, 9 (the .NET behaviour with
   `file:line`; the document above already decided the deviations) and
   `docs/inventory/inventory-domain.md` section 5 (permissions, resolver, scope modes).
7. `db/routines/README.md`, `db/README.md`, the code from prompts 00 to 02 (`db/session.py`,
   `db/pool.py`, `db/errors.py`, `db/types.py`, `db/routines/ops.py`,
   `application/repositories.py`, `domain/*`, `cli/main.py`, `tests/support/database.py`).

Do not read the C# sources; the inventories are the extract. If an inventory and a design
document disagree, the design document decides and you report the difference.

## Environment

PostgreSQL 18 as in prompt 01. `git status` first; write only under `apps/api-python/`.

## Deliverables

### D1 Composite types (`db/routines/00_types/`)

- `api.write_result`, `api.account_state`, `identity.policy`, `tenancy.scope` exactly as
  `docs/05-routines.md` sections 1.3, 2.1, 2.2, 3.1 (`CREATE TYPE` guarded so the file is
  re-runnable; a changed type is a versioned migration, say so in the file header).
- `db/types.py`: adapters from each composite row to its domain record.

### D2 Common helpers (`db/routines/10_common/`)

- `tenancy.refuse`, `tenancy.check_page`, `tenancy.check_money`,
  `tenancy.check_typed_reason`, `tenancy.compose_reason`, `tenancy.join_words`,
  `tenancy.fmt_money`, `tenancy.fmt_day`, `tenancy.fmt_iso`, `tenancy.setting_word`,
  `tenancy.setting_value`, `ops.record_operator_action` (prompt 01) as specified in
  `docs/05-routines.md` sections 2.1 and 6.1. `compose_reason` implements every branch of
  rule `OS-11` (`inventory-domain.md`): the `. Reason: ` join, no second full stop after
  `.`, `!` or `?`, the 500-character budget with the automatic part cut first to
  `greatest(500 - length(suffix), 100)` characters ending in `...`, and the final clip to
  497 plus `...`.
- Evidence: `tests/db/test_tenancy_helpers.py` with the examples of
  `AutomaticReasonTests` quoted in `inventory-tests.md` and `inventory-domain.md` (exact
  strings), `fmt_money` for `21000`, `1500.5`, `0.5`, `999999999999.99`, `fmt_day` for
  `2026-10-08` (`8 Oct 2026`), `join_words` for 1, 2, 3 and 4 parts.

### D3 Tenancy helpers (`db/routines/30_tenancy/`)

- `tenancy.enter_organization`, `tenancy.enter_organization_as_operator`,
  `tenancy.require_permission`, `tenancy.require_any_permission`, `tenancy.has_permission`,
  `tenancy.effective_permissions`, `tenancy.actor_scope`, `tenancy.scope_mode`,
  `tenancy.business_date`, `tenancy.calendar_date`, `tenancy.check_time_zone`,
  `tenancy.record_change`, `tenancy.seed_roles`, `tenancy.people_visible` per
  `docs/05-routines.md` section 2.1.
- `effective_permissions` is the resolver of `inventory-domain.md` section 5 /
  `inventory-http-contract.md` section 3.2: inactive membership gives `{}`; role defaults
  plus granted overrides; dependencies expanded transitively; denied overrides removed;
  then every permission whose direct dependencies are not all present is removed until
  nothing changes. One SQL function, no loops over rows in Python anywhere.
- `record_change` is the only writer of `tenancy.change_log` and `tenancy.audit_events`
  and the only statement that moves `tenancy.organizations.settings_version`
  (`docs/04-schema.md` section 4.1); it uses the current actor and request id from the
  settings and refuses (`XC403 not_member`) when none is set.
- Evidence: `tests/db/test_tenancy_helpers.py`: GUCs are transaction-local; `not_member`
  and `permission_missing`; a table of resolver cases (each role's defaults expanded; a
  grant; a deny that prunes dependants; an inactive membership); `business_date` with a
  held date, without one, across the midnight boundary of `Africa/Nairobi` and of a
  negative-offset zone; `check_time_zone` accepts `Africa/Nairobi` and refuses `Nairobi`
  and `africa/nairobi`; `record_change` returns consecutive versions, writes both rows
  with the request id, and two concurrent callers on one organization get distinct
  versions (two connections).

### D4 Identity helpers (`db/routines/20_identity/`)

- `identity.normalize_phone`, `identity.lock_user`, `identity.policy_for`,
  `identity.matching_code`, `identity.withdraw_codes`, `identity.code_caps`,
  `identity.touch_version`, `identity.revoke_devices`, `identity.revoke_tokens`,
  `identity.record_attempt`, `identity.mask_email` per `docs/05-routines.md` section 2.2
  and the parameters of `docs/07-auth.md` section 1.
- Evidence: `tests/db/test_identity_helpers.py`: the phone table of `docs/07-auth.md`
  section 1 (12, 10 and 9 digit forms; `+` and spaces; a non-ASCII digit; a 9-digit number
  starting with `2`); `matching_code` picks the newest unconsumed code of the device and
  purpose, refuses expired (`now > expires_at`) and accepts `now = expires_at`, consumes on
  the fifth failure; `code_caps` cooldown (consumed codes count, withdrawn do not), 5 per
  hour, 10 per day, and the skip-cooldown flag; `policy_for` clamps a row outside the
  bounds (insert one with the constraints temporarily disabled as owner) and returns no row
  for a user without an active membership or role.

### D5 Authentication routines (`db/routines/20_identity/`)

- `api.auth_account_lookup`, `api.auth_sign_in`, `api.auth_verify_device`,
  `api.auth_request_code`, `api.auth_verify_code`, `api.auth_complete_pin`,
  `api.auth_refresh`, `api.auth_sign_out`, `api.auth_revoke_device`,
  `api.auth_withdraw_code`, `api.auth_resolve_session`, with the signatures of
  `docs/05-routines.md` section 3.2 and the check orders of `docs/07-auth.md` section 3,
  step by step, in that order. Business refusals are outcomes, never exceptions; the only
  exception is `XC401 session_invalid` from `api.auth_resolve_session`.
- Every routine locks the user row (`identity.lock_user`) before its first write, or takes
  `pg_advisory_xact_lock(hashtext('device:' || p_device_id))` when no account is involved,
  and writes exactly one `identity.sign_in_attempts` row.
- Token eligibility (active membership with a role) is checked before any state change
  (`docs/07-auth.md` section 2, deviation 1).
- Evidence: `tests/db/test_auth_routines.py`, one test per numbered step of
  `docs/07-auth.md` section 3 (name the test after the step), the state machine of
  section 4 as a table (every transition row), the resets table, the revocation matrix of
  section 6 (one test per row that a routine here causes), rotation and replay, the
  `silent` outcomes of `api.auth_request_code`, the policy-length branch of
  `api.auth_complete_pin` (code kept, nothing changed), `api.auth_withdraw_code`
  (withdrawn code starts no cooldown), and `api.auth_resolve_session` for each of the four
  failure causes. Use `p_now` for every time-dependent case; never sleep.

### D6 Operator routines (`db/routines/60_ops/` and `20_identity/`)

- `api.ops_provision_user`, `api.ops_remove_user`, `api.ops_clear_pause`,
  `api.ops_revoke_sessions`, `api.ops_account_state`, `api.meta_unassigned_user_count`
  (granted to `xcode_app`, no operator row) per `docs/05-routines.md`
  section 5 and `docs/07-auth.md` section 9 (provisioning steps 1 to 10 of
  `inventory-auth.md` section 9.1, with the organization created through
  `tenancy.enter_organization_as_operator` and `tenancy.seed_roles`, default localization,
  branding and security-policy rows inserted with the .NET defaults of
  `docs/04-schema.md` sections 4.3, 4.4, 4.6).
- `db routines` grants: confirm the runner from prompt 01 grants `api.ops_*` to
  `xcode_operator` only and `api.auth_*` to `xcode_app` only (fix the runner if it does
  not; it is yours in this prompt).
- Evidence: `tests/db/test_ops_routines.py` as `xcode_operator`: first provision creates
  the organization, roles, defaults, user, membership, scope; re-provision with a changed
  phone bumps the security version and revokes devices and tokens; a no-change re-run
  changes nothing; a phone belonging to another email is `people_contact_taken`; remove;
  clear pause leaves `untrusted_failed_attempts`; revoke sessions; unassigned count; and
  as `xcode_app` every `api.ops_*` call fails with `42501`.

### D7 Gateway and ports

- `application/repositories.py`: `IdentityRepository` Protocol with one typed async method
  per routine of D5 and D6 (commands and outcomes as frozen dataclasses in
  `domain/identity.py`; the `jsonb` outcome of `docs/05-routines.md` section 3.1 becomes
  `AuthOutcome`), and `OpsRepository` extended with the user routines.
- `db/routines/identity.py` (`IdentityRoutines`) and `db/routines/ops.py` (`OpsRoutines`)
  implementing them through `db/session.py`, one routine per method, idempotent flag set
  only for `api.auth_resolve_session` and `api.auth_account_lookup`.
- Evidence: `tests/db/test_gateway.py` extended: each method maps its routine's outcome
  and translates `XC401` to `SessionInvalid`; the statement counter reads 1 per call.

### D8 CLI user commands (`cli/commands/users.py`)

- `provision-user`, `remove-user`, `clear-pause`, `revoke-sessions`, `account-state` per
  `docs/08-operability.md` section 8: they open a pool on `XCODE_DATABASE_OPERATOR_URL`
  (exit 2 with a clear message when unset), pass `XCODE_OPERATOR` and a generated request
  id, print ids and counts only, exit 1 on a refusal with the code, and never print
  personal data beyond what the operator typed.
- Evidence: `tests/unit/test_cli.py` (argument parsing, unset URL) and
  `tests/api/test_cli.py` (against the database: each command's effect and its
  `ops.operator_actions` row with the operator name, as `docs/12-security.md` section 2
  requires).

### D9 Routine headers and documentation

- Every routine file carries the header lines of `docs/05-routines.md` section 1.1;
  `tests/db/test_routine_headers.py` parses them and compares `Raises:` with the `refuse(`
  calls in the body (auth routines list `none` except `api.auth_resolve_session`).
- `docs/05-routines.md`: any signature or behaviour you had to change is changed in the
  document in the same commit and listed in the report; `db/routines/README.md` lists the
  files.

## Invariants at the end

- Every `api.*` routine is `SECURITY DEFINER`, owned by `xcode_api_executor`, with
  `search_path` set and no `PUBLIC` execute (`db verify`); `xcode_app` cannot call
  `api.ops_*`; `xcode_operator` cannot call `api.auth_*`.
- No routine body calls `now()`; every time-dependent decision uses `p_now`.
- Each auth routine writes exactly one attempt row per call (a test counts them).
- No PIN, code or token in clear text ever reaches the database: the routines take
  digests only (grep the routine files for `pin text`, `code text`, `token text`
  parameters: none).
- Lint, types, all tests green; `db verify` exit 0; no TODO/FIXME; no plan or prompt ids.

## Verify (paste the outputs into the report)

```
cd apps/api-python
docker compose up -d postgres
ruff check . && ruff format --check . && mypy
pytest -n auto -q
xcode-api db migrate && xcode-api db routines && xcode-api db verify ; echo "exit=$?"
psql "$XCODE_MIGRATION_DATABASE_URL" -c "select proname from pg_proc where pronamespace = 'api'::regnamespace order by 1"
XCODE_DATABASE_OPERATOR_URL=... xcode-api provision-user --email owner@example.com --phone 0712345678 ; echo "exit=$?"
```

## Report format

1. Checklist: one row per deliverable D1 to D9 and per bullet: done or not, `file:symbol`,
   test name.
2. Verify outputs, trimmed, including the routine list.
3. Deviations from `docs/05-routines.md` and `docs/07-auth.md` with reasons; document
   lines changed.
4. Items left for prompt 04 (expected: the Python side of auth, mail, HTTP).

## House rules

- Shared tree: `git status` first; edit only under `apps/api-python/`; never revert or
  reformat others' changes; never kill processes you did not start; never bare `git stash`.
- No commits unless the user asks. No AI attribution anywhere.
- No comments unless needed; routine files carry the header the conventions require and
  nothing decorative; no plan or prompt identifiers anywhere.
- Never weaken a test to make it pass. If a document is wrong, fix the document and report
  it.
