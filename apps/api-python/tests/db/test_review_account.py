"""The App Review login: ``api.ops_review_account_create``, for the operator only, makes the
login an Owner of the one organization flagged as demo, first creating that organization with
its sample fleet beside any real one, which it leaves alone; its code is a digest no routine but
that one writes, and ``identity.matching_code`` takes it for a new device only while the code
the PIN step issued to that device is live; a sign-in with it is in the sign-in history like any
other."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg.types.json import Jsonb

from xcode_api.db.migrate import find_db_dir

from ..support.rows import seed_organization
from ..support.scenario import (
    EMAIL,
    NEW_CODE_HASH,
    NEW_PIN_HASH,
    PIN_HASH,
    T0,
    Account,
    Auth,
    Conn,
    attempts,
    call,
    digest,
    live_tokens,
    make_account,
    store_code,
    store_token,
    trust,
    user_row,
)

REVIEW_EMAIL = "app.review@example.com"
REVIEW_PHONE = "0798765432"
REVIEW_NORMALIZED = "+254798765432"
REVIEW_CODE_HASH = digest("code:424242")
DEVICE = "review-phone"
ROLE_OF = (
    "SELECT r.name FROM tenancy.person_roles pr JOIN tenancy.roles r "
    "ON r.organization_id = pr.organization_id AND r.id = pr.role_id WHERE pr.user_id = %s"
)
REVIEW_ACTIONS = "SELECT count(*) FROM ops.operator_actions WHERE action = 'review-account'"
REVIEW_ROWS = "SELECT count(*) FROM identity.review_accounts"
RESULT_KEYS = {"user_id", "organization_id", "created_user", "created_organization"}
ORGANIZATION_STATE = (
    "SELECT to_jsonb(o) AS organization, "
    "(SELECT count(*) FROM tenancy.memberships AS m WHERE m.organization_id = o.id) AS members, "
    "(SELECT count(*) FROM setup.expense_categories AS c WHERE c.organization_id = o.id) "
    "AS categories, "
    "(SELECT count(*) FROM setup.psv_companies AS p WHERE p.organization_id = o.id) AS companies, "
    "(SELECT count(*) FROM setup.fleet_vehicles AS v WHERE v.organization_id = o.id) AS vehicles, "
    "(SELECT count(*) FROM revenue.records AS r WHERE r.organization_id = o.id) AS revenue "
    "FROM tenancy.organizations AS o WHERE o.id = %s"
)


def _create(
    operator: Conn,
    *,
    email: str = REVIEW_EMAIL,
    phone: str = REVIEW_PHONE,
    pin_hash: str = PIN_HASH,
    code_hash: str = REVIEW_CODE_HASH,
) -> dict[str, Any]:
    result: dict[str, Any] = call(
        operator,
        "ops_review_account_create",
        "test-operator",
        "req-review",
        email,
        phone,
        pin_hash,
        code_hash,
        T0,
    )
    return result


def _refused(operator: Conn, **values: Any) -> tuple[str | None, str | None]:
    with pytest.raises(psycopg.Error) as caught:
        _create(operator, **values)
    return caught.value.sqlstate, caught.value.diag.message_primary


def _one(conn: Conn, query: str, params: Any = ()) -> Any:
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return next(iter(row.values()))


def _demo(operator: Conn, owner: Conn) -> Account:
    account = make_account(operator, owner)
    owner.execute("UPDATE tenancy.organizations SET demo = true")
    return account


def _seeding(operator: Conn) -> None:
    # Creating the demo organization writes six weeks of history in one call, as the CLI allows.
    operator.execute("SET statement_timeout = '120s'")


def _state(owner: Conn, organization_id: UUID) -> dict[str, Any]:
    row = owner.execute(ORGANIZATION_STATE, (organization_id,)).fetchone()
    assert row is not None
    return dict(row)


def _nothing_created(owner: Conn, review_rows: int = 0) -> None:
    assert _one(owner, REVIEW_ROWS) == review_rows
    assert _one(owner, "SELECT count(*) FROM identity.users WHERE email = %s", (REVIEW_EMAIL,)) == 0
    assert _one(owner, REVIEW_ACTIONS) == 0


def _review_hash(owner: Conn, user_id: UUID) -> str | None:
    row = owner.execute(
        "SELECT code_hash FROM identity.review_accounts WHERE user_id = %s", (user_id,)
    ).fetchone()
    return None if row is None else str(row["code_hash"])


def test_an_organization_is_not_demo_unless_the_seed_says_so(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    make_account(operator_conn, owner_conn)
    assert _one(owner_conn, "SELECT bool_or(demo) FROM tenancy.organizations") is False


def test_without_a_demo_organization_one_is_made_beside_the_real_one(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    real = make_account(operator_conn, owner_conn)
    before = _state(owner_conn, real.organization_id)
    _seeding(operator_conn)
    result = _create(operator_conn)
    assert set(result) == RESULT_KEYS
    assert (result["created_user"], result["created_organization"]) == (True, True)
    demo_id, user_id = UUID(result["organization_id"]), UUID(result["user_id"])
    assert demo_id != real.organization_id
    assert _state(owner_conn, real.organization_id) == before
    demo = _state(owner_conn, demo_id)
    assert (demo["organization"]["slug"], demo["organization"]["demo"]) == ("demo-fleet", True)
    assert min(demo["categories"], demo["companies"], demo["vehicles"], demo["revenue"]) > 0
    assert _one(owner_conn, ROLE_OF, (user_id,)) == "Owner"
    memberships = "SELECT array_agg(organization_id) FROM tenancy.memberships WHERE user_id = %s"
    assert _one(owner_conn, memberships, (user_id,)) == [demo_id]
    assert _review_hash(owner_conn, user_id) == REVIEW_CODE_HASH

    again = _create(operator_conn, pin_hash=NEW_PIN_HASH, code_hash=NEW_CODE_HASH)
    assert (UUID(again["organization_id"]), again["created_organization"]) == (demo_id, False)
    assert _state(owner_conn, demo_id)["vehicles"] == demo["vehicles"]
    assert _one(owner_conn, "SELECT count(*) FROM tenancy.organizations WHERE demo") == 1


def test_an_empty_database_gets_only_the_demo_organization(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    _seeding(operator_conn)
    result = _create(operator_conn)
    assert result["created_organization"] is True
    assert _one(owner_conn, "SELECT array_agg(demo) FROM tenancy.organizations") == [True]


def test_two_demo_organizations_are_refused_and_nothing_is_created(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    seed_organization(owner_conn)
    seed_organization(owner_conn)
    owner_conn.execute("UPDATE tenancy.organizations SET demo = true")
    review_rows = _one(owner_conn, REVIEW_ROWS)
    assert _refused(operator_conn) == ("XC409", "organization_not_single")
    _nothing_created(owner_conn, review_rows)


def test_a_demo_organization_gets_an_owner_login_holding_the_digest(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    owner = _demo(operator_conn, owner_conn)
    result = _create(operator_conn)
    assert set(result) == RESULT_KEYS
    assert (result["created_user"], result["created_organization"]) == (True, False)
    assert UUID(result["organization_id"]) == owner.organization_id
    user_id = UUID(result["user_id"])
    row = user_row(owner_conn, user_id)
    assert (row["email"], row["phone_number"], row["status"], row["pin_hash"]) == (
        REVIEW_EMAIL,
        REVIEW_NORMALIZED,
        "active",
        PIN_HASH,
    )
    assert _one(owner_conn, ROLE_OF, (user_id,)) == "Owner"
    assert _review_hash(owner_conn, user_id) == REVIEW_CODE_HASH
    assert (
        _one(
            owner_conn,
            "SELECT active FROM tenancy.memberships WHERE user_id = %s",
            (user_id,),
        )
        is True
    )
    assert _one(owner_conn, REVIEW_ACTIONS) == 1


def test_a_second_run_replaces_both_and_ends_every_session(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    _demo(operator_conn, owner_conn)
    user_id = UUID(_create(operator_conn)["user_id"])
    trust(owner_conn, user_id, DEVICE)
    store_token(owner_conn, user_id, DEVICE)
    owner_conn.execute(
        "UPDATE identity.users SET failed_attempts = 3, untrusted_failed_attempts = 2 "
        "WHERE id = %s",
        (user_id,),
    )
    before = user_row(owner_conn, user_id)
    again = _create(operator_conn, pin_hash=NEW_PIN_HASH, code_hash=NEW_CODE_HASH)
    assert (UUID(again["user_id"]), again["created_user"]) == (user_id, False)
    after = user_row(owner_conn, user_id)
    assert after["pin_hash"] == NEW_PIN_HASH
    assert after["security_version"] == before["security_version"] + 1
    assert (after["failed_attempts"], after["untrusted_failed_attempts"]) == (0, 0)
    assert _review_hash(owner_conn, user_id) == NEW_CODE_HASH
    assert live_tokens(owner_conn, user_id) == 0
    assert (
        _one(
            owner_conn,
            "SELECT count(*) FROM identity.trusted_devices WHERE user_id = %s AND NOT revoked",
            (user_id,),
        )
        == 0
    )
    assert _one(owner_conn, REVIEW_ACTIONS) == 2


def test_the_email_of_a_person_who_is_not_a_review_login_is_refused(
    operator_conn: Conn, owner_conn: Conn
) -> None:
    owner = _demo(operator_conn, owner_conn)
    assert _refused(operator_conn, email=EMAIL) == ("XC409", "people_contact_taken")
    assert user_row(owner_conn, owner.user_id)["pin_hash"] == PIN_HASH
    assert _review_hash(owner_conn, owner.user_id) is None


def test_another_persons_phone_is_refused(operator_conn: Conn, owner_conn: Conn) -> None:
    owner = _demo(operator_conn, owner_conn)
    assert _refused(operator_conn, phone=owner.phone) == ("XC409", "people_contact_taken")
    _nothing_created(owner_conn)


def test_a_renewal_with_another_phone_is_refused(operator_conn: Conn, owner_conn: Conn) -> None:
    _demo(operator_conn, owner_conn)
    user_id = UUID(_create(operator_conn)["user_id"])
    assert _refused(operator_conn, phone="0798765433", code_hash=NEW_CODE_HASH) == (
        "XC409",
        "review_phone_differs",
    )
    assert _review_hash(owner_conn, user_id) == REVIEW_CODE_HASH


@pytest.mark.parametrize(
    ("values", "code"),
    [
        ({"email": "not-an-email"}, "people_email_invalid"),
        ({"phone": "12345"}, "people_phone_invalid"),
    ],
)
def test_a_bad_email_or_phone_is_refused(
    operator_conn: Conn, owner_conn: Conn, values: dict[str, str], code: str
) -> None:
    _demo(operator_conn, owner_conn)
    assert _refused(operator_conn, **values) == ("XC422", code)


def test_only_the_operator_may_create_a_review_login(
    app_conn: Conn, operator_conn: Conn, owner_conn: Conn
) -> None:
    _demo(operator_conn, owner_conn)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _create(app_conn)


def test_the_fixed_code_signs_in_a_new_device_after_the_pin_and_is_in_the_history(
    app_conn: Conn, operator_conn: Conn, owner_conn: Conn
) -> None:
    _demo(operator_conn, owner_conn)
    user_id = UUID(_create(operator_conn)["user_id"])
    auth = Auth(app_conn)
    assert auth.pin(phone=REVIEW_PHONE, device=DEVICE)["outcome"] == "verification_required"
    signed_in = auth.check_code(
        "new_device", phone=REVIEW_PHONE, device=DEVICE, code_hash=REVIEW_CODE_HASH
    )
    assert signed_in["outcome"] == "authenticated"
    trail = [a for a in attempts(owner_conn) if a["user_id"] == user_id]
    assert [a["outcome"] for a in trail][-1] == "authenticated"
    assert trail[-1]["device_id"] == DEVICE


def test_without_the_pin_step_the_fixed_code_is_refused(
    app_conn: Conn, operator_conn: Conn, owner_conn: Conn
) -> None:
    _demo(operator_conn, owner_conn)
    _create(operator_conn)
    refused = Auth(app_conn).check_code(
        "new_device", phone=REVIEW_PHONE, device=DEVICE, code_hash=REVIEW_CODE_HASH
    )
    assert (refused["outcome"], refused["refusal"]) == ("refused", "code_expired")


def test_the_fixed_code_answers_no_other_purpose(
    app_conn: Conn, operator_conn: Conn, owner_conn: Conn
) -> None:
    _demo(operator_conn, owner_conn)
    user_id = UUID(_create(operator_conn)["user_id"])
    store_code(owner_conn, user_id, "pin_reset", DEVICE)
    refused = Auth(app_conn).check_code(
        "pin_reset", phone=REVIEW_PHONE, device=DEVICE, code_hash=REVIEW_CODE_HASH
    )
    assert (refused["outcome"], refused["refusal"]) == ("refused", "wrong_code")


def test_the_fixed_code_belongs_to_the_review_login_alone(
    app_conn: Conn, operator_conn: Conn, owner_conn: Conn
) -> None:
    owner = _demo(operator_conn, owner_conn)
    _create(operator_conn)
    auth = Auth(app_conn)
    assert auth.pin(phone=owner.phone, device=DEVICE)["outcome"] == "verification_required"
    refused = auth.check_code(
        "new_device", phone=owner.phone, device=DEVICE, code_hash=REVIEW_CODE_HASH
    )
    assert (refused["outcome"], refused["refusal"]) == ("refused", "wrong_code")


def test_the_demo_seed_flags_its_organization(operator_conn: Conn, owner_conn: Conn) -> None:
    operator_conn.execute("SET statement_timeout = '120s'")
    call(operator_conn, "ops_seed_demo", "test-operator", "req-seed", "development", Jsonb({}), T0)
    assert _one(owner_conn, "SELECT bool_and(demo) FROM tenancy.organizations") is True


_ROUTINES = find_db_dir() / "routines"
_WRITES_REVIEW = re.compile(r"(INSERT\s+INTO|UPDATE)\s+identity\.review_accounts\b", re.IGNORECASE)
_WRITES_DEMO = re.compile(
    r"\bdemo\s*=\s*true\b|INSERT\s+INTO\s+tenancy\.organizations\s*\([^)]*\bdemo\b",
    re.IGNORECASE,
)
_CALLS_DEMO_ORGANIZATION = re.compile(r"(?<!FUNCTION )\bops\.seed_demo_organization\s*\(")


def _writers(pattern: re.Pattern[str]) -> set[str]:
    found: set[str] = set()
    for path in _ROUTINES.rglob("*.sql"):
        text = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))
        if pattern.search(text):
            found.add(path.name)
    return found


def test_only_the_operator_routine_writes_a_review_code() -> None:
    assert _writers(_WRITES_REVIEW) == {"ops_review_account_create.sql"}


def test_only_the_demo_seeds_set_the_demo_flag() -> None:
    assert _writers(_WRITES_DEMO) == {"seed_demo_organization.sql", "ops_seed_demo.sql"}


def test_only_the_seed_and_the_review_login_create_the_demo_organization() -> None:
    assert _writers(_CALLS_DEMO_ORGANIZATION) == {
        "ops_seed_demo.sql",
        "ops_review_account_create.sql",
    }
