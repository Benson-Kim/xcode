"""The ops and metadata routines, called as the roles the contract allows: the operator user
routines as ``xcode_operator`` (``docs/07-auth.md`` section 9), and the refusal of every
``api.ops_*`` routine to ``xcode_app`` and of every ``api.auth_*`` routine to the operator."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg.types.json import Jsonb

from xcode_api.db.contract import EXPECTED_CONTRACT_VERSION
from xcode_api.db.verify import run_checks

from ..support.rows import seed_organization
from ..support.scenario import (
    EMAIL,
    NEW_PIN_HASH,
    PHONE,
    PIN_HASH,
    TRUSTED,
    Conn,
    build_fleet,
    call,
    live_tokens,
    make_account,
    provision,
    seed_10x,
    set_user,
    store_token,
    trust,
    user_row,
)
from ..support.tenancy import set_scope

T0 = datetime(2026, 10, 7, 9, 0, 0, tzinfo=UTC)


def _hit(
    conn: psycopg.Connection[dict[str, object]],
    key: str,
    limit: int,
    window: int,
    now: datetime,
) -> dict[str, object]:
    row = conn.execute(
        "SELECT * FROM api.rate_limit_hit(%s, %s, %s, %s)", (key, limit, window, now)
    ).fetchone()
    assert row is not None
    return row


def test_rate_limit_allows_then_refuses_as_app(
    app_conn: psycopg.Connection[dict[str, object]],
) -> None:
    first = _hit(app_conn, "k", 2, 60, T0)
    assert first["allowed"] is True
    assert first["remaining"] == 1
    second = _hit(app_conn, "k", 2, 60, T0)
    assert second["allowed"] is True
    assert second["remaining"] == 0
    third = _hit(app_conn, "k", 2, 60, T0)
    assert third["allowed"] is False
    assert third["remaining"] == 0
    assert third["retry_after_seconds"] > 0


def test_rate_limit_resets_across_a_window_boundary(
    app_conn: psycopg.Connection[dict[str, object]],
) -> None:
    assert _hit(app_conn, "k", 1, 60, T0)["allowed"] is True
    assert _hit(app_conn, "k", 1, 60, T0)["allowed"] is False
    later = T0 + timedelta(seconds=60)
    assert _hit(app_conn, "k", 1, 60, later)["allowed"] is True


def test_two_connections_share_the_same_window(
    app_conn: psycopg.Connection[dict[str, object]],
    competing_writer: psycopg.Connection[dict[str, object]],
) -> None:
    assert _hit(app_conn, "shared", 2, 60, T0)["allowed"] is True
    assert _hit(competing_writer, "shared", 2, 60, T0)["allowed"] is True
    assert _hit(app_conn, "shared", 2, 60, T0)["allowed"] is False


def test_rate_limit_invalid_inputs_raise_xc422(
    app_conn: psycopg.Connection[dict[str, object]],
) -> None:
    for key, limit, window in [("k", 0, 60), ("k", 1, 0), ("x" * 257, 1, 60)]:
        with pytest.raises(psycopg.errors.Error) as exc:
            app_conn.execute(
                "SELECT * FROM api.rate_limit_hit(%s, %s, %s, %s)", (key, limit, window, T0)
            ).fetchone()
        assert exc.value.sqlstate == "XC422"
        assert exc.value.diag.message_primary == "rate_limit_invalid"


def test_contract_version_is_the_one_the_app_expects_as_app(
    app_conn: psycopg.Connection[dict[str, object]],
) -> None:
    row = app_conn.execute("SELECT api.meta_contract_version() AS v").fetchone()
    assert row is not None
    assert row["v"] == EXPECTED_CONTRACT_VERSION >= 3


def test_operator_records_an_action(
    operator_conn: psycopg.Connection[dict[str, object]],
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    operator_conn.execute(
        "SELECT api.ops_record_operator_action(%s, %s, %s, %s::jsonb, %s)",
        ("alice", "clear-pause", "user@example.com", '{"note":"support"}', T0),
    )
    rows = owner_conn.execute(
        "SELECT operator, action, target, detail FROM ops.operator_actions ORDER BY id DESC LIMIT 1"
    ).fetchall()
    assert rows[0]["operator"] == "alice"
    assert rows[0]["action"] == "clear-pause"
    assert rows[0]["target"] == "user@example.com"


def test_app_cannot_execute_an_ops_routine(
    app_conn: psycopg.Connection[dict[str, object]],
) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc:
        app_conn.execute(
            "SELECT api.ops_record_operator_action(%s, %s, %s, %s::jsonb, %s)",
            ("mallory", "x", "y", "{}", T0),
        )
    assert exc.value.sqlstate == "42501"


# --- operator user routines ---------------------------------------------------------------


def _refused(conn: Conn, routine: str, *args: Any) -> psycopg.Error:
    with pytest.raises(psycopg.Error) as caught:
        call(conn, routine, *args)
    return caught.value


def _one(conn: Conn, query: str, params: Any = ()) -> Any:
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return next(iter(row.values()))


ROLE_OF = (
    "SELECT r.name FROM tenancy.person_roles pr JOIN tenancy.roles r "
    "ON r.organization_id = pr.organization_id AND r.id = pr.role_id WHERE pr.user_id = %s"
)


def test_first_provision_creates_the_organization_with_defaults_and_the_person(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    result = provision(operator_conn, email="  Jane.Doe@Example.COM ", phone="+254 712 345 678")
    assert (result["created_user"], result["created_organization"], result["reactivated"]) == (
        True,
        True,
        False,
    )
    org = UUID(result["organization_id"])
    user_id = UUID(result["user_id"])
    organizations = owner_conn.execute(
        "SELECT slug, name, settings_version FROM tenancy.organizations"
    ).fetchall()
    assert organizations == [{"slug": "my-fleet", "name": "My fleet", "settings_version": 1}]
    roles = owner_conn.execute(
        "SELECT name FROM tenancy.roles WHERE organization_id = %s ORDER BY name", (org,)
    ).fetchall()
    assert [r["name"] for r in roles] == ["Fleet manager", "Office admin", "Owner", "Revenue clerk"]
    localization = owner_conn.execute(
        "SELECT locale, time_zone, currency, first_day_of_week "
        "FROM tenancy.organization_localizations"
    ).fetchone()
    assert localization == {
        "locale": "en-GB",
        "time_zone": "Africa/Nairobi",
        "currency": "KES",
        "first_day_of_week": 1,
    }
    branding = owner_conn.execute(
        "SELECT display_name, primary_color FROM tenancy.organization_brandings"
    ).fetchone()
    assert branding == {"display_name": "XCODE", "primary_color": "#1D5FD6"}
    policy = owner_conn.execute(
        "SELECT pin_length, lockout_threshold, lockout_minutes, access_token_minutes, "
        "refresh_token_days FROM tenancy.organization_security_policies"
    ).fetchone()
    assert policy == {
        "pin_length": 4,
        "lockout_threshold": 5,
        "lockout_minutes": 15,
        "access_token_minutes": 10,
        "refresh_token_days": 30,
    }
    user = user_row(owner_conn, user_id)
    assert (user["email"], user["phone_number"], user["status"], user["pin_hash"]) == (
        "jane.doe@example.com",
        "+254712345678",
        "active",
        None,
    )
    membership = owner_conn.execute(
        "SELECT first_name, last_name, active FROM tenancy.memberships WHERE user_id = %s",
        (user_id,),
    ).fetchone()
    assert membership == {"first_name": "Jane", "last_name": "Doe", "active": True}
    assert _one(owner_conn, ROLE_OF, (user_id,)) == "Owner"
    scope_query = "SELECT all_companies FROM tenancy.data_scopes WHERE user_id = %s"
    assert _one(owner_conn, scope_query, (user_id,)) is True
    assert _one(owner_conn, "SELECT count(*) FROM identity.trusted_devices") == 0
    action = owner_conn.execute(
        "SELECT operator, action, target, detail FROM ops.operator_actions "
        "WHERE action = 'provision-user'"
    ).fetchone()
    assert action == {
        "operator": "test-operator",
        "action": "provision-user",
        "target": "jane.doe@example.com",
        "detail": {"request_id": "req-provision"},
    }


@pytest.mark.parametrize(
    ("email", "first", "last", "expected"),
    [
        ("mary.wanjiku@example.com", None, None, ("Mary", "Wanjiku")),
        ("solo@example.com", None, None, ("Solo", "Member")),
        ("mary.wanjiku@example.com", "Grace", "Achieng", ("Grace", "Achieng")),
    ],
)
def test_provision_names_come_from_the_options_or_the_email(
    operator_conn: Conn,
    owner_conn: Conn,
    email: str,
    first: str | None,
    last: str | None,
    expected: tuple[str, str],
) -> None:
    result = provision(operator_conn, email=email, first_name=first, last_name=last)
    row = owner_conn.execute(
        "SELECT first_name, last_name FROM tenancy.memberships WHERE user_id = %s",
        (result["user_id"],),
    ).fetchone()
    assert row is not None
    assert (row["first_name"], row["last_name"]) == expected


def test_provision_with_a_named_organization_and_a_non_owner_role(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    result = provision(operator_conn, role="Fleet manager", organization_name="  North Star  ")
    assert _one(owner_conn, "SELECT name FROM tenancy.organizations") == "North Star"
    scope_count = "SELECT count(*) FROM tenancy.data_scopes WHERE user_id = %s"
    assert _one(owner_conn, scope_count, (result["user_id"],)) == 0


def test_reprovisioning_with_a_changed_phone_ends_every_session(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    account = make_account(operator_conn, owner_conn)
    store_token(owner_conn, account.user_id, TRUSTED)
    before = user_row(owner_conn, account.user_id)
    result = provision(operator_conn, phone="0722222222")
    assert (result["created_user"], result["created_organization"]) == (False, False)
    after = user_row(owner_conn, account.user_id)
    assert after["phone_number"] == "+254722222222"
    assert after["security_version"] == before["security_version"] + 1
    assert after["pin_hash"] == before["pin_hash"]
    assert live_tokens(owner_conn, account.user_id) == 0
    assert _one(owner_conn, "SELECT bool_and(revoked) FROM identity.trusted_devices") is True


def test_a_no_change_rerun_changes_nothing(operator_conn: Conn, owner_conn: Conn) -> None:
    account = make_account(operator_conn, owner_conn)
    store_token(owner_conn, account.user_id, TRUSTED)
    before = user_row(owner_conn, account.user_id)
    membership_query = "SELECT * FROM tenancy.memberships WHERE user_id = %s"
    membership = owner_conn.execute(membership_query, (account.user_id,)).fetchone()
    result = provision(operator_conn)
    assert (result["created_user"], result["reactivated"]) == (False, False)
    assert user_row(owner_conn, account.user_id) == before
    assert owner_conn.execute(membership_query, (account.user_id,)).fetchone() == membership
    assert live_tokens(owner_conn, account.user_id) == 1
    assert _one(owner_conn, "SELECT bool_or(revoked) FROM identity.trusted_devices") is False


def test_reprovisioning_keeps_the_role_unless_one_is_named(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    account = make_account(operator_conn, owner_conn, role="Revenue clerk")
    provision(operator_conn)
    assert _one(owner_conn, ROLE_OF, (account.user_id,)) == "Revenue clerk"
    version = user_row(owner_conn, account.user_id)["security_version"]
    provision(operator_conn, role="Office admin")
    assert _one(owner_conn, ROLE_OF, (account.user_id,)) == "Office admin"
    assert user_row(owner_conn, account.user_id)["security_version"] == version + 1


def test_provisioning_reactivates_a_removed_person(operator_conn: Conn, owner_conn: Conn) -> None:
    account = make_account(operator_conn, owner_conn)
    call(operator_conn, "ops_remove_user", "test-operator", "req", EMAIL, T0)
    owner_conn.execute(
        "UPDATE tenancy.memberships SET active = false WHERE user_id = %s", (account.user_id,)
    )
    result = provision(operator_conn, first_name="Janet")
    assert result["reactivated"] is True
    assert user_row(owner_conn, account.user_id)["status"] == "active"
    membership = owner_conn.execute(
        "SELECT active, first_name, last_name, version FROM tenancy.memberships WHERE user_id = %s",
        (account.user_id,),
    ).fetchone()
    assert membership == {"active": True, "first_name": "Janet", "last_name": "Doe", "version": 2}


def test_a_phone_belonging_to_another_email_is_refused(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    make_account(operator_conn, owner_conn)
    error = _refused(
        operator_conn,
        "ops_provision_user",
        "test-operator",
        "req",
        "someone.else@example.com",
        PHONE,
        None,
        None,
        None,
        None,
        T0,
    )
    assert (error.sqlstate, error.diag.message_primary) == ("XC409", "people_contact_taken")
    assert _one(owner_conn, "SELECT count(*) FROM identity.users") == 1


@pytest.mark.parametrize(
    ("email", "phone", "role", "code"),
    [
        ("not-an-email", PHONE, None, "people_email_invalid"),
        ("", PHONE, None, "people_email_invalid"),
        ("Name <a@b.c>", PHONE, None, "people_email_invalid"),
        (EMAIL, "12345", None, "people_phone_invalid"),
        (EMAIL, PHONE, "Driver", "people_role_unknown"),
        (EMAIL, PHONE, "Owners", "people_role_unknown"),
    ],
)
def test_provision_refuses_a_bad_email_phone_or_role(
    operator_conn: Conn, owner_conn: Conn, email: str, phone: str, role: str | None, code: str
) -> None:
    error = _refused(
        operator_conn,
        "ops_provision_user",
        "test-operator",
        "req",
        email,
        phone,
        role,
        None,
        None,
        None,
        T0,
    )
    assert (error.sqlstate, error.diag.message_primary) == ("XC422", code)
    assert _one(owner_conn, "SELECT count(*) FROM tenancy.organizations") == 0
    provisions = "SELECT count(*) FROM ops.operator_actions WHERE action = 'provision-user'"
    assert _one(owner_conn, provisions) == 0


@pytest.mark.parametrize(
    ("role", "stored", "all_companies"),
    [
        ("owner", "Owner", True),
        ("OFFICE ADMIN", "Office admin", True),
        ("revenue clerk", "Revenue clerk", None),
    ],
)
def test_provision_matches_the_role_name_ignoring_case(
    operator_conn: Conn, owner_conn: Conn, role: str, stored: str, all_companies: bool | None
) -> None:
    user_id = UUID(provision(operator_conn, role=role)["user_id"])
    assert _one(owner_conn, ROLE_OF, (user_id,)) == stored
    scope = owner_conn.execute(
        "SELECT all_companies FROM tenancy.data_scopes WHERE user_id = %s", (user_id,)
    ).fetchone()
    assert (None if scope is None else scope["all_companies"]) == all_companies


@pytest.mark.parametrize(
    ("first_name", "last_name", "organization_name", "code"),
    [
        ("f" * 101, None, None, "people_names_required"),
        (None, "l" * 101, None, "people_names_required"),
        (None, None, "o" * 201, "organization_name_slug"),
    ],
)
def test_provision_refuses_names_past_their_lengths(
    operator_conn: Conn,
    owner_conn: Conn,
    first_name: str | None,
    last_name: str | None,
    organization_name: str | None,
    code: str,
) -> None:
    error = _refused(
        operator_conn,
        "ops_provision_user",
        "test-operator",
        "req",
        EMAIL,
        PHONE,
        None,
        first_name,
        last_name,
        organization_name,
        T0,
    )
    assert (error.sqlstate, error.diag.message_primary) == ("XC422", code)
    assert _one(owner_conn, "SELECT count(*) FROM identity.users") == 0
    assert _one(owner_conn, "SELECT count(*) FROM tenancy.organizations") == 0


def test_provision_refuses_a_database_with_two_organizations(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    seed_organization(owner_conn)
    seed_organization(owner_conn)
    error = _refused(
        operator_conn,
        "ops_provision_user",
        "test-operator",
        "req",
        "new@example.com",
        "0733000000",
        None,
        None,
        None,
        None,
        T0,
    )
    assert (error.sqlstate, error.diag.message_primary) == ("XC409", "organization_not_single")


def test_remove_user_bumps_the_version_and_revokes_tokens_but_not_devices(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    account = make_account(operator_conn, owner_conn)
    store_token(owner_conn, account.user_id, TRUSTED)
    before = user_row(owner_conn, account.user_id)
    result = call(operator_conn, "ops_remove_user", "alice", "req", " JANE.DOE@example.com", T0)
    assert result == {"user_id": str(account.user_id), "removed": True, "tokens": 1}
    after = user_row(owner_conn, account.user_id)
    assert after["status"] == "removed"
    assert after["security_version"] == before["security_version"] + 1
    assert live_tokens(owner_conn, account.user_id) == 0
    assert _one(owner_conn, "SELECT bool_or(revoked) FROM identity.trusted_devices") is False
    active_query = "SELECT active FROM tenancy.memberships WHERE user_id = %s"
    assert _one(owner_conn, active_query, (account.user_id,)) is True
    again = call(operator_conn, "ops_remove_user", "alice", "req", EMAIL, T0)
    assert again["removed"] is False
    assert user_row(owner_conn, account.user_id)["security_version"] == after["security_version"]


@pytest.mark.parametrize(
    "routine", ["ops_remove_user", "ops_clear_pause", "ops_revoke_sessions", "ops_account_state"]
)
def test_operator_routines_refuse_an_unknown_email(operator_conn: Conn, routine: str) -> None:
    error = _refused(operator_conn, routine, "alice", "req", "nobody@example.com", T0)
    assert (error.sqlstate, error.diag.message_primary) == ("XC404", "not_found")


def test_clear_pause_clears_both_lock_scopes(operator_conn: Conn, owner_conn: Conn) -> None:
    account = make_account(operator_conn, owner_conn)
    set_user(owner_conn, account.user_id, failed_attempts=2, untrusted_failed_attempts=5)
    result = call(operator_conn, "ops_clear_pause", "alice", "req", EMAIL, T0)
    assert result == {"user_id": str(account.user_id), "was_locked": True}
    user = user_row(owner_conn, account.user_id)
    assert (user["failed_attempts"], user["untrusted_failed_attempts"]) == (0, 0)
    again = call(operator_conn, "ops_clear_pause", "alice", "req", EMAIL, T0)
    assert again == {"user_id": str(account.user_id), "was_locked": False}


def test_revoke_sessions_bumps_the_version_and_revokes_devices_and_tokens(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    account = make_account(operator_conn, owner_conn)
    trust(owner_conn, account.user_id, "second")
    store_token(owner_conn, account.user_id, TRUSTED)
    before = user_row(owner_conn, account.user_id)["security_version"]
    result = call(operator_conn, "ops_revoke_sessions", "alice", "req", EMAIL, T0)
    assert result == {"user_id": str(account.user_id), "devices": 2, "tokens": 1}
    assert user_row(owner_conn, account.user_id)["security_version"] == before + 1
    assert live_tokens(owner_conn, account.user_id) == 0


def test_account_state_reports_counts_and_never_a_hash(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    account = make_account(operator_conn, owner_conn)
    trust(owner_conn, account.user_id, "expired", expires_at=T0)
    store_token(owner_conn, account.user_id, TRUSTED)
    store_token(owner_conn, account.user_id, TRUSTED, expires_at=T0)
    set_user(owner_conn, account.user_id, failed_attempts=2, untrusted_failed_attempts=1)
    result = call(operator_conn, "ops_account_state", "alice", "req", EMAIL, T0)
    assert result == {
        "user_id": str(account.user_id),
        "status": "active",
        "has_pin": True,
        "pin_reset_required": False,
        "sign_in_status": "active",
        "last_signed_in_at": None,
        "failed_attempts": 2,
        "untrusted_failed_attempts": 1,
        "trusted_devices": 1,
        "live_refresh_tokens": 1,
        "active_membership": True,
    }
    action_count = "SELECT count(*) FROM ops.operator_actions WHERE action = 'account-state'"
    assert _one(owner_conn, action_count) == 1


@pytest.mark.parametrize("conn_name", ["app_conn", "operator_conn"])
def test_unassigned_user_count(
    request: pytest.FixtureRequest, operator_conn: Conn, owner_conn: Conn, conn_name: str
) -> None:
    account = make_account(operator_conn, owner_conn)
    conn: Conn = request.getfixturevalue(conn_name)
    assert _one(conn, "SELECT api.meta_unassigned_user_count()") == 0
    owner_conn.execute(
        "UPDATE tenancy.memberships SET active = false WHERE user_id = %s", (account.user_id,)
    )
    owner_conn.execute(
        "INSERT INTO identity.users (email, phone_number) "
        "VALUES ('lone@example.com', '+254733000001')"
    )
    owner_conn.execute(
        "INSERT INTO identity.users (email, phone_number, status) "
        "VALUES ('gone@example.com', '+254733000002', 'removed')"
    )
    assert _one(conn, "SELECT api.meta_unassigned_user_count()") == 2
    meta_actions = "SELECT count(*) FROM ops.operator_actions WHERE left(action, 4) = 'meta'"
    assert _one(owner_conn, meta_actions) == 0


OPS_CALLS = [
    ("ops_provision_user", ("x", "r", EMAIL, PHONE, None, None, None, None, T0)),
    ("ops_remove_user", ("x", "r", EMAIL, T0)),
    ("ops_clear_pause", ("x", "r", EMAIL, T0)),
    ("ops_revoke_sessions", ("x", "r", EMAIL, T0)),
    ("ops_account_state", ("x", "r", EMAIL, T0)),
]


@pytest.mark.parametrize(("routine", "args"), OPS_CALLS, ids=[c[0] for c in OPS_CALLS])
def test_app_cannot_execute_the_operator_user_routines(
    app_conn: Conn, routine: str, args: tuple[Any, ...]
) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege) as caught:
        call(app_conn, routine, *args)
    assert caught.value.sqlstate == "42501"


AUTH_CALLS = [
    ("auth_account_lookup", ("r", PHONE, "d", None, True, T0)),
    ("auth_account_lookup_user", ("r", None, "d", T0)),
    ("auth_start", ("r", PHONE, "d", None, None, False, T0)),
    ("auth_pin", ("r", PHONE, "d", None, False, None, None, None, False, T0)),
    (
        "auth_check_code",
        ("r", PHONE, "d", "pin_reset", None, None, None, True, None, None, None, T0),
    ),
    ("auth_resend_code", ("r", PHONE, "d", "pin_reset", None, False, T0)),
    ("auth_change_pin", ("r", None, "d", False, None, None, T0)),
    ("auth_device_list", (None, "d", T0)),
    ("auth_device_remove", ("r", None, None, T0)),
    ("auth_sign_in", ("r", None, "d", True, None, None, None, False, T0)),
    ("auth_verify_device", ("r", PHONE, "d", None, None, None, None, T0)),
    ("auth_request_code", ("r", PHONE, "d", "pin_reset", None, False, T0)),
    ("auth_verify_code", ("r", PHONE, "d", "pin_reset", None, None, T0)),
    (
        "auth_complete_pin",
        ("r", PHONE, "d", "pin_reset", None, False, None, None, None, True, None, None, None, T0),
    ),
    ("auth_refresh", ("r", "t", "d", "n", T0)),
    ("auth_sign_out", ("r", "t", "d", T0)),
    ("auth_revoke_device", ("r", None, "d", T0)),
    ("auth_withdraw_code", ("r", None, T0)),
    ("auth_resolve_session", (None, "d", 0, T0)),
]


@pytest.mark.parametrize(("routine", "args"), AUTH_CALLS, ids=[c[0] for c in AUTH_CALLS])
def test_operator_cannot_execute_the_auth_routines(
    operator_conn: Conn, routine: str, args: tuple[Any, ...]
) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege) as caught:
        call(operator_conn, routine, *args)
    assert caught.value.sqlstate == "42501"


# --- demo seed ----------------------------------------------------------------------------

SEED_NOW = datetime(2026, 10, 12, 9, 0, 0, tzinfo=UTC)
SEED_TODAY = date(2026, 10, 12)
ANTONY = "antony.maina@shamayah.co.ke"
PETER = "peter.otieno@zurigenesis.co.ke"
BRIAN = "brian.mwangi@metrotrans.co.ke"
WANJIRU = "wanjiru.kamau@zurigenesis.co.ke"
SEED_PINS = {ANTONY: PIN_HASH, PETER: PIN_HASH, WANJIRU: PIN_HASH}
SEED_TABLES = (
    "tenancy.organizations",
    "identity.users",
    "tenancy.memberships",
    "tenancy.person_roles",
    "tenancy.data_scopes",
    "tenancy.data_scope_companies",
    "setup.expense_main_categories",
    "setup.expense_categories",
    "setup.expense_items",
    "setup.psv_companies",
    "setup.fleet_vehicles",
    "setup.vehicle_target_sets",
    "setup.vehicle_away_periods",
    "setup.recurring_items",
    "setup.recurring_versions",
    "setup.recurring_allocations",
    "setup.vehicle_investments",
    "revenue.records",
    "pettycash.entries",
    "tenancy.change_log",
    "tenancy.audit_events",
)
SEED_HELPERS = {
    "seed_catalogue",
    "seed_companies",
    "seed_demo_user",
    "seed_fleet",
    "seed_fleet_setup",
    "seed_pettycash_day",
    "seed_revenue_day",
    "seed_vehicle_plan",
}
SEED_ACTIONS = "SELECT count(*) FROM ops.operator_actions WHERE action = 'seed-demo'"


def _seed(
    operator: Conn,
    *,
    environment: str | None = "development",
    pins: dict[str, str] | None = None,
    now: datetime = SEED_NOW,
) -> dict[str, Any]:
    # One routine call writes the whole history, longer than the operator role's 5 s limit.
    operator.execute("SET statement_timeout = '120s'")
    result: dict[str, Any] = call(
        operator,
        "ops_seed_demo",
        "test-operator",
        "req-seed",
        environment,
        Jsonb(SEED_PINS if pins is None else pins),
        now,
    )
    return result


def _counts(owner: Conn) -> dict[str, int]:
    return {table: _one(owner, f"SELECT count(*) FROM {table}") for table in SEED_TABLES}


def _rows(owner: Conn, query: str, params: Any = ()) -> list[dict[str, Any]]:
    return owner.execute(query, params).fetchall()


def test_seed_demo_twice_adds_nothing_the_second_time(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    first = _seed(operator_conn)
    assert set(first) == {"organization_id", "created"}
    assert first["created"] is True
    before = _counts(owner_conn)
    assert _one(owner_conn, SEED_ACTIONS) == 1
    assert all(count > 0 for count in before.values())

    second = _seed(operator_conn, pins={ANTONY: NEW_PIN_HASH})
    assert second == {"organization_id": first["organization_id"], "created": False}
    assert _counts(owner_conn) == before
    assert _one(owner_conn, SEED_ACTIONS) == 2
    users = _rows(owner_conn, "SELECT email, pin_hash FROM identity.users")
    assert {u["email"]: u["pin_hash"] for u in users} == {
        ANTONY: PIN_HASH,
        PETER: PIN_HASH,
        BRIAN: None,
        WANJIRU: PIN_HASH,
    }


def test_seed_demo_builds_the_people_catalogue_and_fleet(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    org = UUID(_seed(operator_conn)["organization_id"])
    organization = owner_conn.execute(
        "SELECT o.slug, o.name, l.time_zone, l.currency FROM tenancy.organizations AS o "
        "JOIN tenancy.organization_localizations AS l ON l.organization_id = o.id"
    ).fetchone()
    assert organization == {
        "slug": "demo-fleet",
        "name": "Demo Fleet",
        "time_zone": "Africa/Nairobi",
        "currency": "KES",
    }
    people = _rows(
        owner_conn,
        "SELECT u.email, u.phone_number, u.status, m.first_name, m.last_name, r.name AS role, "
        "(SELECT s.all_companies FROM tenancy.data_scopes AS s WHERE s.user_id = u.id) "
        "AS everything, "
        "(SELECT array_agg(c.name) FROM tenancy.data_scope_companies AS sc "
        "JOIN setup.psv_companies AS c ON c.id = sc.company_id WHERE sc.user_id = u.id) "
        "AS companies "
        "FROM identity.users AS u JOIN tenancy.memberships AS m ON m.user_id = u.id "
        "JOIN tenancy.person_roles AS pr ON pr.user_id = u.id "
        "JOIN tenancy.roles AS r ON r.id = pr.role_id "
        "WHERE m.organization_id = %s ORDER BY u.email",
        (org,),
    )
    assert [
        (p["email"], p["phone_number"], p["first_name"], p["last_name"], p["role"], p["status"])
        for p in people
    ] == [
        (ANTONY, "+254733520614", "Antony", "Maina", "Owner", "active"),
        (BRIAN, "+254700111222", "Brian", "Mwangi", "Fleet manager", "active"),
        (PETER, "+254722410355", "Peter", "Otieno", "Office admin", "active"),
        (WANJIRU, "+254712345678", "Wanjiru", "Kamau", "Revenue clerk", "active"),
    ]
    assert [(p["everything"], p["companies"]) for p in people] == [
        (True, None),
        (True, None),
        (True, None),
        (None, ["Zuri Genesis"]),
    ]

    catalogue = _rows(
        owner_conn,
        "SELECT m.name AS main, c.name AS category, count(i.id) AS items "
        "FROM setup.expense_categories AS c "
        "JOIN setup.expense_main_categories AS m ON m.id = c.main_category_id "
        "LEFT JOIN setup.expense_items AS i ON i.category_id = c.id GROUP BY 1, 2 ORDER BY 2",
    )
    assert [(c["category"], c["items"]) for c in catalogue] == [
        ("Charges", 6),
        ("Garage and repairs", 6),
        ("Loans", 1),
    ]
    assert len({c["main"] for c in catalogue}) == 3

    assert _one(owner_conn, "SELECT count(*) FROM setup.psv_companies") == 2
    vehicles = _rows(owner_conn, "SELECT registration, joined_on FROM setup.fleet_vehicles")
    assert len(vehicles) == 6
    assert max(v["joined_on"] for v in vehicles) == SEED_TODAY - timedelta(days=14)
    assert _one(owner_conn, "SELECT count(*) FROM setup.vehicle_away_periods") == 1
    sets = _rows(owner_conn, "SELECT vehicle_id, starts_on FROM setup.vehicle_target_sets")
    assert len(sets) > 6
    assert any(s["starts_on"] == SEED_TODAY for s in sets)
    assert len({s["vehicle_id"] for s in sets}) == 6
    invested = "SELECT count(DISTINCT vehicle_id) FROM setup.vehicle_investments"
    assert _one(owner_conn, invested) >= 2
    schedule = _rows(
        owner_conn, "SELECT DISTINCT frequency, last_day, kind FROM setup.recurring_versions"
    )
    assert {s["frequency"] for s in schedule} == {2, 3, 4}
    assert any(s["last_day"] for s in schedule)
    assert {s["kind"] for s in schedule} == {1, 2}


def test_seed_demo_revenue_has_gaps_reasons_and_corrections(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    _seed(operator_conn)
    span = owner_conn.execute(
        "SELECT min(business_date) AS first, max(business_date) AS last, count(*) AS n "
        "FROM revenue.records"
    ).fetchone()
    assert span is not None
    assert span["first"] == SEED_TODAY - timedelta(days=42)
    assert span["last"] == SEED_TODAY - timedelta(days=1)
    assert span["n"] > 100
    gaps = _one(
        owner_conn,
        "SELECT count(*) FROM setup.fleet_vehicles AS f "
        "CROSS JOIN LATERAL generate_series(f.joined_on, %s::date, interval '1 day') AS g (d) "
        "WHERE NOT EXISTS (SELECT 1 FROM setup.vehicle_away_periods AS a "
        "WHERE a.vehicle_id = f.id AND g.d::date >= a.left_on AND g.d::date < a.returned_on) "
        "AND NOT EXISTS (SELECT 1 FROM revenue.records AS r "
        "WHERE r.vehicle_id = f.id AND r.business_date = g.d::date)",
        (SEED_TODAY - timedelta(days=1),),
    )
    assert gaps > 0
    assert _one(owner_conn, "SELECT count(*) FROM revenue.records WHERE amount IS NULL") > 0
    low = "SELECT count(*) FROM revenue.records WHERE amount IS NOT NULL AND reason IS NOT NULL"
    assert _one(owner_conn, low) > 0
    corrected = _one(owner_conn, "SELECT count(*) FROM revenue.records WHERE version = 2")
    assert corrected > 0
    flagged = "SELECT count(*) FROM revenue.records WHERE version = 2 AND corrected_after_date"
    assert _one(owner_conn, flagged) == corrected
    captured_by = _rows(
        owner_conn,
        "SELECT DISTINCT u.email FROM revenue.records AS r JOIN identity.users AS u "
        "ON u.id = r.captured_by ORDER BY 1",
    )
    assert [r["email"] for r in captured_by] == [BRIAN, WANJIRU]


def test_seed_demo_petty_cash_has_every_entry_state(operator_conn: Conn, owner_conn: Conn) -> None:
    _seed(operator_conn)
    states = _rows(
        owner_conn,
        "SELECT k.name AS kind, s.name AS status, (e.removed_at IS NOT NULL) AS removed, "
        "(e.sent_back_note IS NOT NULL) AS sent_back "
        "FROM pettycash.entries AS e JOIN pettycash.kinds AS k ON k.code = e.kind "
        "LEFT JOIN pettycash.statuses AS s ON s.code = e.status",
    )
    seen = {(s["kind"], s["status"], s["removed"], s["sent_back"]) for s in states}
    assert {
        ("cash", None, False, False),
        ("credit", None, False, False),
        ("expense", "waiting", False, False),
        ("expense", "waiting", False, True),
        ("expense", "approved", False, False),
        ("expense", "rejected", False, False),
        ("expense", "waiting", True, False),
    } <= seen
    holders = _rows(
        owner_conn,
        "SELECT DISTINCT u.email FROM pettycash.entries AS e JOIN identity.users AS u "
        "ON u.id = e.holder_id",
    )
    assert [h["email"] for h in holders] == [BRIAN]
    negative = _rows(
        owner_conn,
        "SELECT holder_id FROM pettycash.entries WHERE removed_at IS NULL GROUP BY holder_id "
        "HAVING sum(CASE WHEN kind = 1 THEN total WHEN status = 4 THEN 0 ELSE -total END) < 0",
    )
    assert negative == []


def test_seed_demo_keeps_a_consistent_change_log_and_passes_the_checks(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    _seed(operator_conn)
    log = owner_conn.execute(
        "SELECT min(version) AS first, max(version) AS last, count(*) AS n, "
        "min(occurred_at) AS earliest FROM tenancy.change_log"
    ).fetchone()
    assert log is not None
    assert log["first"] == 2
    assert log["n"] == log["last"] - 1
    assert _one(owner_conn, "SELECT settings_version FROM tenancy.organizations") == log["last"]
    assert log["earliest"] < SEED_NOW - timedelta(days=40)
    assert _one(owner_conn, "SELECT count(*) FROM tenancy.audit_events") == log["n"]
    sections = {
        r["section"] for r in _rows(owner_conn, "SELECT DISTINCT section FROM tenancy.change_log")
    }
    assert {
        "people",
        "companies",
        "vehicles",
        "investment",
        "expenses",
        "recurring",
        "revenue",
        "pettycash",
    } <= sections
    stray = _one(
        owner_conn,
        "SELECT count(*) FROM revenue.records AS r "
        "JOIN setup.fleet_vehicles AS f ON f.id = r.vehicle_id "
        "WHERE r.business_date < f.joined_on OR EXISTS (SELECT 1 FROM setup.vehicle_away_periods "
        "AS a WHERE a.vehicle_id = f.id AND r.business_date >= a.left_on "
        "AND r.business_date < a.returned_on)",
    )
    assert stray == 0
    failed = [result for result in run_checks(owner_conn) if not result.ok]
    assert failed == []


def test_seed_demo_keeps_what_was_changed_after_the_first_run(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    org = UUID(_seed(operator_conn)["organization_id"])
    ids = {r["email"]: r["id"] for r in _rows(owner_conn, "SELECT id, email FROM identity.users")}
    owner_conn.execute(
        "UPDATE identity.users SET pin_hash = %s WHERE id = %s", (NEW_PIN_HASH, ids[ANTONY])
    )
    owner_conn.execute(
        "UPDATE setup.expense_main_categories SET name = 'Workshop' WHERE name = 'Loan repayments'"
    )
    owner_conn.execute("UPDATE setup.expense_categories SET name = 'Credit' WHERE name = 'Loans'")
    company = _one(owner_conn, "SELECT id FROM setup.psv_companies WHERE name = 'Metro Trans'")
    set_scope(owner_conn, ids[BRIAN], org, companies=[company])
    call(operator_conn, "ops_remove_user", "alice", "req", PETER, SEED_NOW)
    removed = user_row(owner_conn, ids[PETER])
    assert removed["status"] == "removed"
    before = _counts(owner_conn)

    again = _seed(operator_conn, pins={ANTONY: PIN_HASH, BRIAN: PIN_HASH})
    assert again == {"organization_id": str(org), "created": False}
    assert _counts(owner_conn) == before
    assert user_row(owner_conn, ids[ANTONY])["pin_hash"] == NEW_PIN_HASH
    assert user_row(owner_conn, ids[BRIAN])["pin_hash"] is None
    names = {r["name"] for r in _rows(owner_conn, "SELECT name FROM setup.expense_main_categories")}
    assert "Workshop" in names
    assert "Loan repayments" not in names
    renamed = "SELECT count(*) FROM setup.expense_categories WHERE name = 'Credit'"
    assert _one(owner_conn, renamed) == 1
    scope = owner_conn.execute(
        "SELECT (SELECT count(*) FROM tenancy.data_scopes WHERE user_id = %(u)s) AS everything, "
        "(SELECT array_agg(company_id) FROM tenancy.data_scope_companies "
        "WHERE user_id = %(u)s) AS companies",
        {"u": ids[BRIAN]},
    ).fetchone()
    assert scope == {"everything": 0, "companies": [company]}
    revived = user_row(owner_conn, ids[PETER])
    assert revived["status"] == "active"
    assert revived["security_version"] == removed["security_version"] + 1
    assert revived["pin_hash"] == PIN_HASH


@pytest.mark.parametrize("environment", ["production", "testing", "Development", "", None])
def test_seed_demo_refuses_outside_development_and_writes_nothing(
    operator_conn: Conn, owner_conn: Conn, environment: str | None
) -> None:
    error = _refused(
        operator_conn,
        "ops_seed_demo",
        "test-operator",
        "req-seed",
        environment,
        Jsonb(SEED_PINS),
        SEED_NOW,
    )
    assert (error.sqlstate, error.diag.message_primary) == ("XC403", "seed_development_only")
    assert _counts(owner_conn) == dict.fromkeys(SEED_TABLES, 0)
    assert _one(owner_conn, SEED_ACTIONS) == 0


def test_seed_demo_never_seeds_a_database_holding_other_data(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    seed_organization(owner_conn, slug="other-fleet")
    before = _counts(owner_conn)
    error = _refused(
        operator_conn,
        "ops_seed_demo",
        "test-operator",
        "req-seed",
        "development",
        Jsonb({}),
        SEED_NOW,
    )
    assert (error.sqlstate, error.diag.message_primary) == ("XC409", "seed_exists")
    assert _counts(owner_conn) == before
    assert _one(owner_conn, SEED_ACTIONS) == 0


def test_seed_demo_refuses_a_database_with_two_organizations(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    seed_organization(owner_conn)
    seed_organization(owner_conn)
    error = _refused(
        operator_conn,
        "ops_seed_demo",
        "test-operator",
        "req-seed",
        "development",
        Jsonb({}),
        SEED_NOW,
    )
    assert (error.sqlstate, error.diag.message_primary) == ("XC409", "organization_not_single")


def test_the_seed_is_for_the_operator_alone(app_conn: Conn, owner_conn: Conn) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege) as caught:
        call(app_conn, "ops_seed_demo", "x", "r", "development", Jsonb({}), SEED_NOW)
    assert caught.value.sqlstate == "42501"
    helpers = _rows(
        owner_conn,
        "SELECT p.proname, has_function_privilege('xcode_app', p.oid, 'EXECUTE') AS app, "
        "has_function_privilege('xcode_operator', p.oid, 'EXECUTE') AS operator, "
        "has_function_privilege('xcode_api_executor', p.oid, 'EXECUTE') AS executor "
        "FROM pg_proc AS p JOIN pg_namespace AS n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'ops' AND p.proname LIKE 'seed\\_%%'",
    )
    assert {h["proname"] for h in helpers} == SEED_HELPERS
    assert all((h["app"], h["operator"], h["executor"]) == (False, False, True) for h in helpers)


def test_the_fleet_scenario_is_written_through_the_routines(
    operator_conn: Conn, owner_conn: Conn, app_conn: Conn
) -> None:
    fleet = build_fleet(operator_conn, owner_conn, app_conn)
    assert (len(fleet.companies), len(fleet.vehicles), len(fleet.items)) == (2, 6, 2)
    log = _rows(owner_conn, "SELECT section, count(*) AS n FROM tenancy.change_log GROUP BY 1")
    sections = {r["section"]: r["n"] for r in log}
    assert sections["companies"] == 2
    assert sections["vehicles"] >= 8
    assert sections["revenue"] > 20
    assert _one(owner_conn, "SELECT count(*) FROM setup.vehicle_away_periods") == 1
    assert _one(owner_conn, "SELECT count(*) FROM revenue.records") == sections["revenue"]


def test_seed_10x_gives_ten_times_the_vehicles_and_their_rows(
    operator_conn: Conn, owner_conn: Conn, app_conn: Conn
) -> None:
    fleet = build_fleet(operator_conn, owner_conn, app_conn)
    tables = (
        "setup.fleet_vehicles",
        "setup.vehicle_target_sets",
        "setup.vehicle_away_periods",
        "revenue.records",
    )
    before = {table: _one(owner_conn, f"SELECT count(*) FROM {table}") for table in tables}
    assert before["setup.fleet_vehicles"] == 6
    assert seed_10x(owner_conn, fleet.owner.organization_id) == 60
    after = {table: _one(owner_conn, f"SELECT count(*) FROM {table}") for table in tables}
    assert after == {table: count * 10 for table, count in before.items()}
    registrations = "SELECT count(DISTINCT registration) FROM setup.fleet_vehicles"
    assert _one(owner_conn, registrations) == 60
