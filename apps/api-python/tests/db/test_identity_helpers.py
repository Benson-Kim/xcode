"""The identity helpers, called as ``xcode_api_executor`` (``docs/05-routines.md`` section 2.2,
``docs/07-auth.md`` section 1)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest

from xcode_api.domain.policies import PIN_TRIES, TRUSTED_DEVICE_IDLE_DAYS

from ..support.fakes import held_permissions, role_rights
from ..support.scenario import (
    CODE_HASH,
    T0,
    TRUSTED,
    UNTRUSTED,
    WRONG_CODE_HASH,
    Account,
    Conn,
    codes,
    digest,
    make_account,
    provision,
    store_code,
    store_token,
    trust,
    user_row,
)


def _scalar(conn: Conn, query: str, params: Any = ()) -> Any:
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return next(iter(row.values()))


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("254712345678", "+254712345678"),
        ("+254712345678", "+254712345678"),
        ("0712345678", "+254712345678"),
        ("712345678", "+254712345678"),
        ("+254 712 345 678", "+254712345678"),
        ("0712-345-678", "+254712345678"),
        ("254112345678", "+254112345678"),
        ("0112345678", "+254112345678"),
        ("112345678", "+254112345678"),
        ("254712345", None),  # nine digits starting with 2
        ("0812345678", None),
        ("07123456789", None),
        ("25471234567", None),
        ("\u0660712345678", None),  # an Arabic-Indic zero is not an ASCII digit
        ("0712\u00a0345678", "+254712345678"),  # every non-digit is stripped, as .NET
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalize_phone(executor: Conn, raw: str | None, normalized: str | None) -> None:
    assert _scalar(executor, "SELECT identity.normalize_phone(%s)", (raw,)) == normalized


@pytest.mark.parametrize(
    ("email", "masked"),
    [
        ("jane.doe@example.com", "j***@example.com"),
        ("b@example.com", "b***@example.com"),
        ("@example.com", "***"),
        ("no-at-sign", "***"),
        (None, "***"),
    ],
)
def test_mask_email(executor: Conn, email: str | None, masked: str) -> None:
    assert _scalar(executor, "SELECT identity.mask_email(%s)", (email,)) == masked


def test_phone_digest_is_sha256_hex(executor: Conn) -> None:
    import hashlib

    expected = hashlib.sha256(b"+254712345678").hexdigest()
    assert _scalar(executor, "SELECT identity.phone_digest('+254712345678')") == expected
    assert (
        _scalar(executor, "SELECT identity.phone_digest(NULL)") == hashlib.sha256(b"").hexdigest()
    )


# --- matching_code ------------------------------------------------------------------------


def _match(
    executor: Conn, user_id: UUID, code_hash: str, *, device: str = UNTRUSTED, now: Any = T0
) -> dict[str, Any]:
    row = executor.execute(
        "SELECT (c).code_id, (c).refusal FROM (SELECT identity.matching_code(%s, 'pin_reset', %s, "
        "%s, %s) AS c) AS checked",
        (user_id, device, code_hash, now),
    ).fetchone()
    assert row is not None
    return row


def test_matching_code_picks_the_newest_unconsumed_code_of_the_device_and_purpose(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED, code_hash=CODE_HASH)
    newest = store_code(
        owner_conn,
        account.user_id,
        "pin_reset",
        UNTRUSTED,
        code_hash=digest("newest"),
        created_at=T0 + timedelta(seconds=30),
    )
    store_code(owner_conn, account.user_id, "pin_reset", "another-device", code_hash=digest("x"))
    store_code(owner_conn, account.user_id, "first_setup", UNTRUSTED, code_hash=digest("y"))
    now = T0 + timedelta(minutes=1)
    # The older code of this device is never tried, and other devices and purposes do not count.
    assert _match(executor, account.user_id, CODE_HASH, now=now)["refusal"] == "wrong_code"
    assert _match(executor, account.user_id, digest("x"), now=now)["refusal"] == "wrong_code"
    assert _match(executor, account.user_id, digest("newest"), now=now) == {
        "code_id": newest,
        "refusal": None,
    }
    newest_row = next(c for c in codes(owner_conn, account.user_id) if c["id"] == newest)
    assert newest_row["consumed"] is False
    assert newest_row["failed_attempts"] == 2


def test_matching_code_accepts_now_equal_to_expiry_and_refuses_after(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    code_id = store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED)
    expiry = T0 + timedelta(minutes=10)
    assert _match(executor, account.user_id, CODE_HASH, now=expiry)["code_id"] == code_id
    later = expiry + timedelta(microseconds=1)
    assert _match(executor, account.user_id, CODE_HASH, now=later) == {
        "code_id": None,
        "refusal": "code_expired",
    }


def test_matching_code_without_a_code_is_code_expired(executor: Conn, account: Account) -> None:
    assert _match(executor, account.user_id, CODE_HASH)["refusal"] == "code_expired"


def test_matching_code_voids_on_the_third_failure(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED)
    for attempt in range(1, 4):
        row = executor.execute(
            "SELECT (c).refusal, (c).voided, (c).tries_left FROM (SELECT "
            "identity.matching_code(%s, 'pin_reset', %s, %s, %s) AS c) AS checked",
            (account.user_id, UNTRUSTED, WRONG_CODE_HASH, T0),
        ).fetchone()
        assert row == {"refusal": "wrong_code", "voided": attempt == 3, "tries_left": 3 - attempt}
        stored = codes(owner_conn, account.user_id)[0]
        assert (stored["failed_attempts"], stored["consumed"]) == (attempt, attempt == 3)
    assert _match(executor, account.user_id, CODE_HASH)["refusal"] == "code_expired"


# --- code_caps ----------------------------------------------------------------------------


def _caps(
    executor: Conn,
    user_id: UUID,
    *,
    skip: bool = False,
    replacement: bool = False,
    now: Any = T0,
) -> bool:
    return bool(
        _scalar(
            executor,
            "SELECT identity.code_caps(%s, %s, %s, %s)",
            (user_id, skip, replacement, now),
        )
    )


def test_codes_are_capped_at_one_a_minute_and_five_an_hour_per_person(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    created = T0 - timedelta(seconds=30)
    store_code(
        owner_conn, account.user_id, "pin_reset", TRUSTED, created_at=created, withdrawn=True
    )
    assert _caps(executor, account.user_id) is True
    # A superseded code of another purpose and device still starts the minute.
    store_code(
        owner_conn, account.user_id, "new_device", "other", created_at=created, consumed=True
    )
    assert _caps(executor, account.user_id) is False
    assert _caps(executor, account.user_id, skip=True) is True
    assert _caps(executor, account.user_id, replacement=True) is True
    assert _caps(executor, account.user_id, now=created + timedelta(minutes=1)) is True
    assert (
        _caps(executor, account.user_id, now=created + timedelta(minutes=1, microseconds=-1))
        is False
    )
    for minutes in range(4):
        store_code(
            owner_conn,
            account.user_id,
            "first_setup",
            f"device-{minutes}",
            created_at=T0 - timedelta(minutes=10 + minutes),
            consumed=True,
        )
    # Five in the hour: a replacement passes the minute but not the hour.
    assert (
        _caps(executor, account.user_id, replacement=True, now=T0 + timedelta(minutes=2)) is False
    )


def test_code_caps_allow_five_codes_an_hour(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    for minutes in range(5):
        store_code(
            owner_conn,
            account.user_id,
            "new_device" if minutes % 2 else "pin_reset",
            f"device-{minutes}",
            created_at=T0 - timedelta(minutes=50 - minutes * 5),
            consumed=True,
        )
    store_code(
        owner_conn,
        account.user_id,
        "pin_reset",
        "withdrawn",
        created_at=T0 - timedelta(minutes=5),
        withdrawn=True,
    )
    assert _caps(executor, account.user_id, skip=True) is False
    # The oldest of the five leaves the rolling hour.
    assert _caps(executor, account.user_id, skip=True, now=T0 + timedelta(minutes=11)) is True


def test_code_caps_allow_ten_codes_a_day(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    for hours in range(10):
        store_code(
            owner_conn,
            account.user_id,
            "pin_reset",
            "device",
            created_at=T0 - timedelta(hours=23 - hours * 2),
            consumed=True,
        )
    assert _caps(executor, account.user_id, skip=True) is False
    assert _caps(executor, account.user_id, skip=True, now=T0 + timedelta(hours=2)) is True


# --- policy_for ---------------------------------------------------------------------------


def _policy(executor: Conn, user_id: UUID) -> dict[str, Any] | None:
    with executor.transaction():
        value = _scalar(executor, "SELECT to_jsonb(identity.policy_for(%s))", (user_id,))
    return value  # type: ignore[no-any-return]


def test_policy_for_returns_the_defaults_names_role_and_permissions(
    executor: Conn, account: Account
) -> None:
    policy = _policy(executor, account.user_id)
    assert policy is not None
    assert policy["organization_id"] == str(account.organization_id)
    assert (policy["pin_length"], policy["lockout_threshold"], policy["lockout_minutes"]) == (
        4,
        5,
        15,
    )
    assert (policy["access_token_minutes"], policy["refresh_token_days"]) == (10, 30)
    assert (policy["role_name"], policy["first_name"], policy["last_name"]) == (
        "Owner",
        "Jane",
        "Doe",
    )
    assert len(policy["permissions"]) == len(held_permissions(role_rights("Owner"), "Owner"))


def test_policy_for_clamps_a_row_outside_the_bounds(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    checks = [
        "pin_length", "lockout_threshold", "lockout_minutes", "access_token_minutes",
        "refresh_token_days",
    ]  # fmt: skip
    for column in checks:
        owner_conn.execute(
            "ALTER TABLE tenancy.organization_security_policies "
            f"DROP CONSTRAINT ck_security_policies_{column}"
        )
    owner_conn.execute(
        "UPDATE tenancy.organization_security_policies SET pin_length = 2, lockout_threshold = 50, "
        "lockout_minutes = 0, access_token_minutes = 99, refresh_token_days = 0 "
        "WHERE organization_id = %s",
        (account.organization_id,),
    )
    policy = _policy(executor, account.user_id)
    assert policy is not None
    assert (
        policy["pin_length"],
        policy["lockout_threshold"],
        policy["lockout_minutes"],
        policy["access_token_minutes"],
        policy["refresh_token_days"],
    ) == (4, 10, 1, 15, 1)
    owner_conn.execute(
        "UPDATE tenancy.organization_security_policies SET pin_length = 12, lockout_threshold = 1, "
        "lockout_minutes = 90, access_token_minutes = 0, refresh_token_days = 365 "
        "WHERE organization_id = %s",
        (account.organization_id,),
    )
    policy = _policy(executor, account.user_id)
    assert policy is not None
    assert (
        policy["pin_length"],
        policy["lockout_threshold"],
        policy["lockout_minutes"],
        policy["access_token_minutes"],
        policy["refresh_token_days"],
    ) == (8, 3, 60, 1, 90)


def test_policy_for_has_no_row_without_an_active_membership_or_a_role(
    executor: Conn, owner_conn: Conn, operator_conn: Conn
) -> None:
    inactive = make_account(operator_conn, owner_conn, email="gone@example.com", phone="0722000001")
    owner_conn.execute(
        "UPDATE tenancy.memberships SET active = false WHERE user_id = %s", (inactive.user_id,)
    )
    roleless = provision(operator_conn, email="nobody@example.com", phone="0722000002")
    owner_conn.execute(
        "DELETE FROM tenancy.person_roles WHERE user_id = %s", (roleless["user_id"],)
    )
    owner_conn.execute(
        "INSERT INTO identity.users (email, phone_number) "
        "VALUES ('lone@example.com', '+254722000003')"
    )
    lone = _scalar(owner_conn, "SELECT id FROM identity.users WHERE email = 'lone@example.com'")
    for user_id in (inactive.user_id, roleless["user_id"], lone):
        assert _policy(executor, user_id) is None


# --- revocation, version, attempts --------------------------------------------------------


def test_revoke_devices_and_tokens_count_what_they_revoke(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    trust(owner_conn, account.user_id, "second")
    trust(owner_conn, account.user_id, "revoked", revoked=True)
    store_token(owner_conn, account.user_id, TRUSTED)
    store_token(owner_conn, account.user_id, "second")
    store_token(owner_conn, account.user_id, "second", revoked=True)
    with executor.transaction():
        one_device = _scalar(
            executor, "SELECT identity.revoke_devices(%s, 'second')", (account.user_id,)
        )
        one_token = _scalar(
            executor, "SELECT identity.revoke_tokens(%s, 'second')", (account.user_id,)
        )
        all_devices = _scalar(executor, "SELECT identity.revoke_devices(%s)", (account.user_id,))
        all_tokens = _scalar(executor, "SELECT identity.revoke_tokens(%s)", (account.user_id,))
    assert (one_device, one_token, all_devices, all_tokens) == (1, 1, 1, 1)
    versions = owner_conn.execute(
        "SELECT revoked, version FROM identity.refresh_tokens WHERE user_id = %s",
        (account.user_id,),
    ).fetchall()
    assert all(r["revoked"] for r in versions)
    assert sorted(r["version"] for r in versions) == [0, 1, 1]


def test_supersede_codes_consumes_every_device_of_the_purpose_only(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    store_code(owner_conn, account.user_id, "pin_reset", "a")
    store_code(owner_conn, account.user_id, "pin_reset", "b")
    keep = store_code(owner_conn, account.user_id, "first_setup", "a")
    with executor.transaction():
        count = _scalar(
            executor, "SELECT identity.supersede_codes(%s, 'pin_reset')", (account.user_id,)
        )
    assert count == 2
    rows = codes(owner_conn, account.user_id)
    assert {r["id"]: r["consumed"] for r in rows}[keep] is False
    superseded = [r for r in rows if r["purpose"] == "pin_reset"]
    # Superseded, not withdrawn: the expiry stays, so the codes still count toward the caps.
    assert all(r["consumed"] and r["expires_at"] > r["created_at"] for r in superseded)


def test_touch_version_and_record_attempt(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    before = user_row(owner_conn, account.user_id)["version"]
    with executor.transaction():
        executor.execute("SELECT set_config('xcode.request_id', 'req-attempt', true)")
        bumped = _scalar(executor, "SELECT identity.touch_version(%s)", (account.user_id,))
        executor.execute(
            "SELECT identity.record_attempt('sign_in', 'refused', 'wrong_pin', %s, %s, %s, %s)",
            (account.user_id, digest("phone").lower(), TRUSTED, T0),
        )
    assert bumped == before + 1
    row = owner_conn.execute(
        "SELECT * FROM identity.sign_in_attempts ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert (row["operation"], row["outcome"], row["refusal"]) == ("sign_in", "refused", "wrong_pin")
    assert (row["user_id"], row["device_id"], row["request_id"]) == (
        account.user_id,
        TRUSTED,
        "req-attempt",
    )
    assert row["occurred_at"] == T0


def test_active_organization_reads_past_row_level_security(
    executor: Conn, account: Account
) -> None:
    # No organization is entered: a plain read of memberships sees nothing.
    assert _scalar(executor, "SELECT count(*) FROM tenancy.memberships") == 0
    assert (
        _scalar(executor, "SELECT identity.active_organization(%s)", (account.user_id,))
        == account.organization_id
    )


# --- the v2.33 helpers ----------------------------------------------------------------------


def test_the_lock_and_idle_limits_equal_their_python_twins(executor: Conn) -> None:
    assert _scalar(executor, "SELECT identity.pin_tries()") == PIN_TRIES == 5
    assert _scalar(executor, "SELECT identity.device_idle_days()") == TRUSTED_DEVICE_IDLE_DAYS == 90


def _device(owner_conn: Conn, user_id: UUID, device: str) -> dict[str, Any]:
    row = owner_conn.execute(
        "SELECT * FROM identity.trusted_devices WHERE user_id = %s AND device_id = %s",
        (user_id, device),
    ).fetchone()
    assert row is not None
    return row


@pytest.mark.parametrize(
    ("change", "now", "live"),
    [
        ({}, T0 + timedelta(days=90, microseconds=-1), True),
        ({}, T0 + timedelta(days=90), False),
        ({"revoked": True}, T0, False),
        ({"expires_at": T0 + timedelta(days=1)}, T0 + timedelta(days=1), False),
        ({"remembered": False}, T0, True),
    ],
)
def test_device_live(
    executor: Conn,
    owner_conn: Conn,
    account: Account,
    change: dict[str, Any],
    now: Any,
    live: bool,
) -> None:
    trust(owner_conn, account.user_id, "device", **change)
    with executor.transaction():
        result = _scalar(
            executor,
            "SELECT identity.device_live(d, %s) FROM identity.trusted_devices AS d "
            "WHERE d.user_id = %s AND d.device_id = 'device'",
            (now, account.user_id),
        )
    assert result is live


def test_device_trusted_by_token_or_by_id(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    token = digest("token")
    trust(owner_conn, account.user_id, "with-token", token_hash=token)

    def trusted(device: str, token_hash: str | None) -> bool:
        return bool(
            _scalar(
                executor,
                "SELECT identity.device_trusted(%s, %s, %s, %s)",
                (account.user_id, device, token_hash, T0),
            )
        )

    assert (trusted(TRUSTED, None), trusted(TRUSTED, ""), trusted(TRUSTED, token)) == (
        True,
        False,
        False,
    )
    assert (trusted("with-token", None), trusted("with-token", token)) == (False, True)
    assert trusted("with-token", digest("other")) is False


@pytest.mark.parametrize(
    ("change", "member", "status"),
    [
        ({}, True, "active"),
        ({"status": "removed"}, True, "blocked"),
        ({}, False, "blocked"),
        ({"pin_hash": None, "failed_attempts": 5}, True, "not_signed_in"),
        ({"pin_reset_required": True, "failed_attempts": 5}, True, "pin_reset_due"),
        ({"failed_attempts": 5}, True, "locked"),
        ({"untrusted_failed_attempts": 5}, True, "locked"),
        ({"failed_attempts": 4, "untrusted_failed_attempts": 4}, True, "active"),
    ],
)
def test_sign_in_status_in_precedence_order(
    executor: Conn,
    owner_conn: Conn,
    account: Account,
    change: dict[str, Any],
    member: bool,
    status: str,
) -> None:
    if change:
        assignments = ", ".join(f"{name} = %s" for name in change)
        owner_conn.execute(
            f"UPDATE identity.users SET {assignments} WHERE id = %s",
            (*change.values(), account.user_id),
        )
    assert (
        _scalar(
            executor,
            "SELECT identity.sign_in_status(u, %s) FROM identity.users AS u WHERE u.id = %s",
            (member, account.user_id),
        )
        == status
    )


def test_remove_devices_ends_rows_tokens_and_codes_and_names_the_live_remembered_ones(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    trust(owner_conn, account.user_id, "named", name="Jane phone")
    trust(owner_conn, account.user_id, "session", remembered=False)
    trust(owner_conn, account.user_id, "stale", last_used_at=T0 - timedelta(days=100))
    store_token(owner_conn, account.user_id, "named")
    store_token(owner_conn, account.user_id, TRUSTED)
    store_code(owner_conn, account.user_id, "new_device", "named")
    store_code(owner_conn, account.user_id, "pin_reset", "nowhere")
    named = _device(owner_conn, account.user_id, "named")["id"]
    with executor.transaction():
        one = _scalar(
            executor, "SELECT identity.remove_devices(%s, %s, %s)", (account.user_id, T0, named)
        )
    assert one == ["Jane phone"]
    live = owner_conn.execute(
        "SELECT device_id, revoked FROM identity.refresh_tokens WHERE user_id = %s "
        "ORDER BY device_id",
        (account.user_id,),
    ).fetchall()
    assert [(t["device_id"], t["revoked"]) for t in live] == [("named", True), (TRUSTED, False)]
    with executor.transaction():
        rest = _scalar(executor, "SELECT identity.remove_devices(%s, %s)", (account.user_id, T0))
    assert rest == [None]
    assert all(c["consumed"] for c in codes(owner_conn, account.user_id))
    assert not owner_conn.execute(
        "SELECT 1 FROM identity.trusted_devices WHERE user_id = %s AND NOT revoked",
        (account.user_id,),
    ).fetchall()


def test_unknown_pin_tries_count_only_the_lookups_rows_of_the_digest(
    executor: Conn, owner_conn: Conn
) -> None:
    number = digest("unknown number").lower()
    with executor.transaction():
        executor.execute("SELECT set_config('xcode.request_id', 'req', true)")
        for operation in ("sign_in", "pin", "start", "sign_in"):
            executor.execute(
                "SELECT identity.record_attempt(%s, 'refused', 'unknown_number', NULL, %s, "
                "'d', %s)",
                (operation, number, T0),
            )
        executor.execute(
            "SELECT identity.record_attempt('sign_in', 'refused', 'unknown_number', NULL, %s, "
            "'d', %s)",
            (digest("someone else").lower(), T0),
        )
        assert _scalar(executor, "SELECT identity.unknown_pin_tries(%s)", (number,)) == 2
        for _ in range(9):
            executor.execute(
                "SELECT identity.record_attempt('sign_in', 'refused', 'unknown_number', NULL, %s, "
                "'d', %s)",
                (number, T0),
            )
        assert _scalar(executor, "SELECT identity.unknown_pin_tries(%s)", (number,)) == 6


def test_unknown_code_tries_follow_the_newest_reset_request(executor: Conn) -> None:
    number = digest("unknown number").lower()

    def record(operation: str, outcome: str, refusal: str | None, at: Any) -> None:
        executor.execute(
            "SELECT identity.record_attempt(%s, %s, %s, NULL, %s, 'd', %s)",
            (operation, outcome, refusal, number, at),
        )

    def tries(at: Any, device: str = "d") -> Any:
        return _scalar(
            executor, "SELECT identity.unknown_code_tries(%s, %s, %s)", (number, device, at)
        )

    with executor.transaction():
        executor.execute("SELECT set_config('xcode.request_id', 'req', true)")
        assert tries(T0) is None
        record("request_code", "check_email", "unknown_number", T0)
        assert tries(T0) is None
        record("forgot_pin", "check_email", "unknown_number", T0)
        record("code", "refused", "wrong_code", T0)
        assert tries(T0) == 1
        assert tries(T0, device="another device") is None
        record("code", "code_resent", "wrong_code", T0)
        assert tries(T0) == 0
        assert tries(T0 + timedelta(minutes=10)) == 0
        assert tries(T0 + timedelta(minutes=10, microseconds=1)) is None
