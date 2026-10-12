# Routines (the callable surface and its helpers)

Applied every deploy, all files in one transaction, in lexical order of the full path:

| Folder | Contents |
|---|---|
| `00_types/` | composite row types (one per file): `api.write_result`, `api.account_state`, `identity.policy`, `identity.code_check`, `tenancy.scope` |
| `10_common/` | helpers in data schemas: `tenancy.refuse` (the only RAISE site), `tenancy.trim_text`, `tenancy.check_page`, `tenancy.check_money`, `tenancy.check_typed_reason`, `tenancy.compose_reason`, `tenancy.join_words`, `tenancy.fmt_money`, `tenancy.fmt_day`, `tenancy.fmt_iso`, `tenancy.fmt_instant`, `tenancy.compact_json`, `tenancy.setting_word`, `tenancy.setting_value`, `ops.record_operator_action`; `api.meta_contract_version` |
| `20_identity/` | identity helpers (`identity.normalize_phone`, `normalize_email`, `phone_digest`, `lock_user`, `lock_account`, `active_organization`, `policy_for`, `matching_code`, `supersede_codes`, `code_caps`, `mask_email`, `touch_version`, `revoke_devices`, `revoke_tokens`, `record_attempt`, `device_trusted`, `trust_device`, `issue_session`, `outcome`); the eleven `api.auth_*` routines; `api.ops_provision_user`, `api.ops_remove_user`, `api.ops_clear_pause`, `api.ops_revoke_sessions`, `api.ops_account_state` |
| `30_tenancy/` | tenancy helpers (`tenancy.enter_organization`, `enter_organization_as_operator`, `effective_permissions`, `has_permission`, `require_permission`, `require_any_permission`, `actor_scope`, `scope_mode`, `business_date`, `calendar_date`, `check_time_zone`, `record_change`, `seed_roles`, `people_visible`, `organization_ids`), the access helpers (`assigned_permissions`, `expand_permissions`, `role_permissions`, `person_scope`, `person_reach`, `person_in_view`, `role_of`, `check_person_grant`, `save_person`, `person_document`, `person_snapshot`, `redact_person_snapshot`) and the settings helpers (`settings_defaults`, `settings_document`, `settings_snapshot`, `logo_snapshot`, `settings_reason`, `check_localization`, `check_branding`, `check_security_policy`, `effective_settings`); `api.access_*`, `api.people_*`, `api.history_list`, `api.organization_*`, `api.preferences_*` |
| `40_setup/` | `setup.visible_vehicles`, `setup.visible_companies` and the other `setup.*` helpers of `docs/05-routines.md` section 2.3; `api.setup_company_*`, `api.setup_vehicle_*`, `api.setup_expense_category_*`, `api.setup_expense_item_*`, `api.setup_recurring_*`, `api.setup_investment_*` |
| `50_revenue/` | `api.revenue_*` |
| `55_pettycash/` | `pettycash.*` helpers, `api.pettycash_*` |
| `60_ops/` | `api.rate_limit_hit`, `api.meta_unassigned_user_count`, `api.ops_record_operator_action`, later `api.ops_seed_demo` |

Every file follows `docs/03-database.md` section 4 and has an entry in `docs/05-routines.md`.
A file header states, one line each: the name and signature, `Purpose:`, `Callers:`, `Reads:`
and `Writes:`, `Raises:` (every SQLSTATE and code in check order; `none` when it raises
nothing; a code raised by a called helper is written `XC422 code via schema.helper`), and
`Tests:`. `tests/db/test_routine_headers.py` parses every file and compares `Raises:` with
the `tenancy.refuse(` calls of the body.

`LANGUAGE sql` bodies are checked when they are created, so a SQL function may only call
functions of files that sort before it (or of migrations); `plpgsql` bodies resolve names
when they run. Helpers are granted to `xcode_api_executor` in their own file; the runner
grants every `api.*` routine to its caller by name.
