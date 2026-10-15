"""The ``api.auth_*`` routines as ``xcode_app``: every step of ``docs/07-auth.md`` section 3
under the lock of section 12.5, the state machine and resets of the lock, the revocation
matrix, and one attempt row per decision. Time comes only from ``p_now``."""

from __future__ import annotations

import threading
from datetime import timedelta
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from ..support.fakes import held_permissions, role_rights
from ..support.scenario import (
    CODE_HASH,
    NEW_CODE_HASH,
    NEW_PIN_HASH,
    NORMALIZED,
    PHONE,
    PIN_HASH,
    T0,
    TRUSTED,
    UNTRUSTED,
    WRONG_CODE_HASH,
    Account,
    Auth,
    Conn,
    attempt_count,
    attempts,
    call,
    codes,
    device_row,
    digest,
    last_attempt,
    live_tokens,
    make_account,
    new_token_hash,
    set_user,
    store_code,
    store_token,
    tokens,
    trust,
    user_row,
)

POLICY_PAUSE_SECONDS = 15 * 60
YEAR = timedelta(days=365)


def _counters(owner: Conn, user_id: UUID) -> tuple[int, int]:
    """The two lock scopes: wrong PINs from trusted devices, and from untrusted ones."""
    row = user_row(owner, user_id)
    return row["failed_attempts"], row["untrusted_failed_attempts"]


def _assert_attempt(
    owner: Conn, operation: str, outcome: str, refusal: str | None, user_id: UUID | None
) -> None:
    row = last_attempt(owner)
    assert (row["operation"], row["outcome"], row["refusal"], row["user_id"]) == (
        operation,
        outcome,
        refusal,
        user_id,
    )


def _session_alive(auth: Auth, account: Account, version: int, device: str = TRUSTED) -> bool:
    """Whether an access token issued at ``version`` for ``device`` still resolves."""
    try:
        auth.resolve(account.user_id, version, device=device)
    except psycopg.Error as error:
        assert error.sqlstate == "XC401"
        return False
    return True


# --- 3.1 statement one: the lookup ----------------------------------------------------------


def test_lookup_returns_the_account_state_with_its_policy(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    before = attempt_count(owner_conn)
    state = auth.lookup("+254 712 345 678", TRUSTED)
    assert state is not None
    assert state["user_id"] == account.user_id
    assert (state["status"], state["pin_hash"], state["device_trusted"]) == (
        "active",
        PIN_HASH,
        True,
    )
    assert state["policy"]["role_name"] == "Owner"
    assert (state["phone_number"], state["pin_reset_required"]) == (NORMALIZED, False)
    assert attempt_count(owner_conn) == before
    other = auth.lookup(PHONE, UNTRUSTED)
    assert other is not None
    assert other["device_trusted"] is False


@pytest.mark.parametrize(("phone", "hashed"), [("0799999999", "+254799999999"), ("12345", "12345")])
def test_lookup_of_an_unknown_or_non_normalising_number_records_unknown_number(
    auth: Auth, owner_conn: Conn, account: Account, phone: str, hashed: str
) -> None:
    import hashlib

    assert auth.lookup(phone, UNTRUSTED) is None
    row = last_attempt(owner_conn)
    assert (row["operation"], row["outcome"], row["refusal"], row["user_id"]) == (
        "sign_in",
        "refused",
        "unknown_number",
        None,
    )
    assert row["phone_digest"] == hashlib.sha256(hashed.encode()).hexdigest()
    assert row["request_id"] == "req-lookup"


# --- 3.1 statement two: sign-in, step by step ----------------------------------------------


def test_step_1_no_account_is_refused(auth: Auth, owner_conn: Conn) -> None:
    result = auth.sign_in(None)
    assert (result["outcome"], result["refusal"]) == ("refused", "unknown_number")
    _assert_attempt(owner_conn, "sign_in", "refused", "unknown_number", None)


def test_step_1_a_removed_account_is_refused(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, status="removed")
    result = auth.sign_in(account.user_id, pin_ok=True)
    assert (result["outcome"], result["refusal"]) == ("refused", "inactive")
    assert live_tokens(owner_conn, account.user_id) == 0


def test_step_1_an_account_without_a_pin_is_refused(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, pin_hash=None)
    result = auth.sign_in(account.user_id, pin_ok=True)
    assert (result["outcome"], result["refusal"]) == ("refused", "no_pin")
    _assert_attempt(owner_conn, "sign_in", "refused", "no_pin", account.user_id)


def test_a_pending_forced_reset_is_refused_with_nothing_counted(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, pin_reset_required=True)
    for device, pin_ok in ((TRUSTED, True), (UNTRUSTED, False)):
        result = auth.sign_in(account.user_id, device=device, pin_ok=pin_ok)
        assert (result["outcome"], result["refusal"]) == ("refused", "reset_required")
    assert _counters(owner_conn, account.user_id) == (0, 0)
    assert codes(owner_conn, account.user_id) == []
    _assert_attempt(owner_conn, "sign_in", "refused", "reset_required", account.user_id)


def test_a_lock_never_lapses(auth: Auth, owner_conn: Conn, account: Account) -> None:
    set_user(owner_conn, account.user_id, failed_attempts=5)
    trust(owner_conn, account.user_id, TRUSTED, last_used_at=T0 + YEAR - timedelta(days=1))
    result = auth.sign_in(account.user_id, pin_ok=True, now=T0 + YEAR)
    assert (result["outcome"], result["refusal"]) == ("paused", "locked")
    assert _counters(owner_conn, account.user_id) == (5, 0)


def test_locked_on_every_device_a_trusted_device_shows_the_policy_pause_and_counts_nothing(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, failed_attempts=5)
    for pin_ok in (True, False):
        result = auth.sign_in(account.user_id, pin_ok=pin_ok)
        assert (result["outcome"], result["refusal"], result["retry_after_seconds"]) == (
            "paused",
            "locked",
            POLICY_PAUSE_SECONDS,
        )
    assert _counters(owner_conn, account.user_id) == (5, 0)
    assert tokens(owner_conn, account.user_id) == []
    _assert_attempt(owner_conn, "sign_in", "paused", "locked", account.user_id)


def test_locked_on_every_device_an_untrusted_device_is_refused_whatever_the_pin(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, failed_attempts=5)
    for pin_ok in (True, False):
        result = auth.sign_in(account.user_id, device=UNTRUSTED, pin_ok=pin_ok)
        assert (result["outcome"], result["refusal"]) == ("refused", "locked")
    assert _counters(owner_conn, account.user_id) == (5, 0)
    assert codes(owner_conn, account.user_id) == []


@pytest.mark.parametrize("state", ["revoked", "expired", "missing", "unused", "token", "session"])
def test_step_4_a_revoked_expired_missing_or_unused_device_is_untrusted(
    auth: Auth, owner_conn: Conn, account: Account, state: str
) -> None:
    device = "device-under-test"
    if state == "revoked":
        trust(owner_conn, account.user_id, device, revoked=True)
    elif state == "expired":
        trust(owner_conn, account.user_id, device, expires_at=T0)
    elif state == "unused":
        trust(owner_conn, account.user_id, device, last_used_at=T0 - timedelta(days=90))
    elif state == "token":
        trust(owner_conn, account.user_id, device, token_hash=digest("device-token"))
    elif state == "session":
        trust(owner_conn, account.user_id, device, remembered=False)
    result = auth.sign_in(account.user_id, device=device, pin_ok=True)
    assert result["outcome"] == "verification_required"
    trust(owner_conn, account.user_id, "valid", expires_at=T0 + timedelta(microseconds=1))
    assert auth.sign_in(account.user_id, device="valid", pin_ok=True)["outcome"] == "authenticated"


def test_locked_for_new_devices_an_untrusted_device_is_refused_and_a_trusted_one_signs_in(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, untrusted_failed_attempts=5)
    for pin_ok in (True, False):
        result = auth.sign_in(account.user_id, device=UNTRUSTED, pin_ok=pin_ok)
        assert (result["outcome"], result["refusal"]) == ("refused", "locked")
    assert _counters(owner_conn, account.user_id) == (0, 5)
    assert codes(owner_conn, account.user_id) == []
    assert auth.sign_in(account.user_id, pin_ok=True)["outcome"] == "authenticated"


def test_wrong_pins_on_a_trusted_device_count_and_the_fifth_locks_every_device(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    for expected in range(1, 5):
        result = auth.sign_in(account.user_id, pin_ok=False)
        assert (result["outcome"], result["refusal"]) == ("refused", "wrong_pin")
        assert _counters(owner_conn, account.user_id) == (expected, 0)
    result = auth.sign_in(account.user_id, pin_ok=False)
    assert (result["outcome"], result["retry_after_seconds"]) == ("paused", POLICY_PAUSE_SECONDS)
    assert _counters(owner_conn, account.user_id) == (5, 0)
    _assert_attempt(owner_conn, "sign_in", "paused", "wrong_pin", account.user_id)
    refused = auth.sign_in(account.user_id, device=UNTRUSTED, pin_ok=True)
    assert (refused["outcome"], refused["refusal"]) == ("refused", "locked")


def test_the_policy_minutes_set_the_paused_timer_and_the_lock_is_always_five(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    owner_conn.execute(
        "UPDATE tenancy.organization_security_policies SET lockout_threshold = 3, "
        "lockout_minutes = 2 WHERE organization_id = %s",
        (account.organization_id,),
    )
    for _ in range(4):
        assert auth.sign_in(account.user_id, pin_ok=False)["outcome"] == "refused"
    result = auth.sign_in(account.user_id, pin_ok=False)
    assert (result["outcome"], result["retry_after_seconds"]) == ("paused", 120)
    assert _counters(owner_conn, account.user_id) == (5, 0)


def test_wrong_pins_on_an_untrusted_device_count_and_the_fifth_locks_new_devices(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    for expected in range(1, 6):
        result = auth.sign_in(account.user_id, device=UNTRUSTED, pin_ok=False)
        assert (result["outcome"], result["refusal"]) == ("refused", "wrong_pin")
        assert _counters(owner_conn, account.user_id) == (0, expected)
    result = auth.sign_in(account.user_id, device=UNTRUSTED, pin_ok=False)
    assert result["refusal"] == "locked"
    assert _counters(owner_conn, account.user_id) == (0, 5)


def test_steps_6_and_7_a_verdict_on_a_hash_replaced_since_the_lookup_is_a_wrong_pin(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, pin_hash=NEW_PIN_HASH)
    result = auth.sign_in(account.user_id, pin_ok=True, checked_hash=PIN_HASH)
    assert (result["outcome"], result["refusal"]) == ("refused", "wrong_pin")
    result = auth.sign_in(account.user_id, device=UNTRUSTED, pin_ok=True, checked_hash=PIN_HASH)
    assert (result["outcome"], result["refusal"]) == ("refused", "wrong_pin")
    result = auth.sign_in(account.user_id, pin_ok=True, checked_hash=None)
    assert (result["outcome"], result["refusal"]) == ("refused", "wrong_pin")
    assert _counters(owner_conn, account.user_id) == (2, 1)
    assert tokens(owner_conn, account.user_id) == []
    assert codes(owner_conn, account.user_id) == []
    result = auth.sign_in(account.user_id, pin_ok=True, checked_hash=NEW_PIN_HASH)
    assert result["outcome"] == "authenticated"


def test_step_8_the_right_pin_on_an_untrusted_device_issues_a_new_device_code(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, failed_attempts=2, untrusted_failed_attempts=3)
    older = store_code(
        owner_conn, account.user_id, "new_device", "elsewhere", created_at=T0 - timedelta(hours=2)
    )
    result = auth.sign_in(account.user_id, device=UNTRUSTED, pin_ok=True)
    assert result["outcome"] == "verification_required"
    assert (result["masked_email"], result["purpose"]) == ("j***@example.com", "new_device")
    assert (result["code_issued"], result["email"]) == (True, account.email)
    stored = codes(owner_conn, account.user_id)
    issued = next(c for c in stored if c["id"] == UUID(result["code_id"]))
    assert (issued["purpose"], issued["device_id"], issued["code_hash"]) == (
        "new_device",
        UNTRUSTED,
        CODE_HASH,
    )
    assert (issued["created_at"], issued["expires_at"]) == (T0, T0 + timedelta(minutes=10))
    assert next(c for c in stored if c["id"] == older)["consumed"] is True
    assert _counters(owner_conn, account.user_id) == (2, 3)
    assert live_tokens(owner_conn, account.user_id) == 0
    _assert_attempt(owner_conn, "sign_in", "verification_required", None, account.user_id)


def test_step_8_inside_the_cooldown_no_code_is_issued_but_the_answer_is_the_same(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    store_code(
        owner_conn,
        account.user_id,
        "new_device",
        "elsewhere",
        created_at=T0 - timedelta(seconds=59),
    )
    result = auth.sign_in(account.user_id, device=UNTRUSTED, pin_ok=True)
    assert (result["outcome"], result["code_issued"], result["code_id"]) == (
        "verification_required",
        False,
        None,
    )
    assert result["email"] is None
    assert len(codes(owner_conn, account.user_id)) == 1
    skipped = auth.sign_in(account.user_id, device=UNTRUSTED, pin_ok=True, skip_cooldown=True)
    assert skipped["code_issued"] is True


def test_step_8_without_a_membership_is_refused_with_nothing_changed(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    owner_conn.execute(
        "UPDATE tenancy.memberships SET active = false WHERE user_id = %s", (account.user_id,)
    )
    set_user(owner_conn, account.user_id, failed_attempts=2)
    version = user_row(owner_conn, account.user_id)["version"]
    result = auth.sign_in(account.user_id, device=UNTRUSTED, pin_ok=True)
    assert (result["outcome"], result["refusal"]) == ("refused", "inactive")
    assert codes(owner_conn, account.user_id) == []
    row = user_row(owner_conn, account.user_id)
    assert (row["failed_attempts"], row["version"]) == (2, version)


def test_step_9_the_right_pin_on_a_trusted_device_clears_its_scope_and_issues_tokens(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, failed_attempts=3, untrusted_failed_attempts=4)
    version = user_row(owner_conn, account.user_id)["version"]
    refresh_hash = new_token_hash()
    result = auth.sign_in(account.user_id, pin_ok=True, refresh_hash=refresh_hash)
    assert result["outcome"] == "authenticated"
    assert (result["user_id"], result["organization_id"]) == (
        str(account.user_id),
        str(account.organization_id),
    )
    assert (result["role"], result["first_name"], result["last_name"]) == ("Owner", "Jane", "Doe")
    assert len(result["permissions"]) == len(held_permissions(role_rights("Owner"), "Owner"))
    assert (result["security_version"], result["access_token_minutes"]) == (0, 10)
    stored = tokens(owner_conn, account.user_id)
    assert [(t["token_hash"], t["device_id"], t["revoked"]) for t in stored] == [
        (refresh_hash, TRUSTED, False)
    ]
    assert stored[0]["expires_at"] == T0 + timedelta(days=30)
    row = user_row(owner_conn, account.user_id)
    assert (row["failed_attempts"], row["untrusted_failed_attempts"]) == (0, 4)
    assert row["last_signed_in_at"] == T0
    assert row["version"] == version + 1
    _assert_attempt(owner_conn, "sign_in", "authenticated", None, account.user_id)


def test_step_9_without_a_role_is_refused_with_nothing_changed(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    owner_conn.execute("DELETE FROM tenancy.person_roles WHERE user_id = %s", (account.user_id,))
    set_user(owner_conn, account.user_id, failed_attempts=3)
    version = user_row(owner_conn, account.user_id)["version"]
    result = auth.sign_in(account.user_id, pin_ok=True)
    assert (result["outcome"], result["refusal"]) == ("refused", "inactive")
    assert tokens(owner_conn, account.user_id) == []
    row = user_row(owner_conn, account.user_id)
    assert (row["failed_attempts"], row["version"]) == (3, version)


def test_concurrent_wrong_pins_on_one_account_are_both_counted(
    app_url: str, owner_conn: Conn, account: Account
) -> None:
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as first,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as second,
    ):
        started = threading.Event()

        def second_attempt() -> None:
            started.set()
            Auth(second).sign_in(account.user_id, pin_ok=False)

        with first.transaction():
            Auth(first).sign_in(account.user_id, pin_ok=False)
            worker = threading.Thread(target=second_attempt)
            worker.start()
            assert started.wait(10)
            worker.join(0.5)
            # The second attempt waits on the user row lock until the first commits.
            assert worker.is_alive()
        worker.join(10)
    assert _counters(owner_conn, account.user_id)[0] == 2


def test_revoking_a_device_waits_for_the_accounts_other_auth_work(
    app_url: str, owner_conn: Conn, account: Account
) -> None:
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as first,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as second,
    ):
        started = threading.Event()
        order: list[str] = []

        def revoke() -> None:
            started.set()
            Auth(second).revoke_device(account.user_id)
            order.append("revoked")

        with first.transaction():
            Auth(first).sign_in(account.user_id, pin_ok=False)
            worker = threading.Thread(target=revoke)
            worker.start()
            assert started.wait(10)
            worker.join(0.5)
            # The revoke waits on the user row lock until the sign-in attempt commits.
            assert worker.is_alive()
            order.append("committing")
        worker.join(10)
    assert order == ["committing", "revoked"]
    device = device_row(owner_conn, account.user_id, TRUSTED)
    assert device is not None and device["revoked"] is True
    assert _counters(owner_conn, account.user_id)[0] == 1


# --- 3.2 verify-device --------------------------------------------------------------------


def test_verify_device_refuses_an_unknown_number(auth: Auth, owner_conn: Conn) -> None:
    result = auth.verify_device(phone="0799999999")
    assert (result["outcome"], result["refusal"]) == ("refused", "unknown_number")
    _assert_attempt(owner_conn, "verify_device", "refused", "unknown_number", None)


@pytest.mark.parametrize(
    ("change", "refusal"),
    [
        ({"status": "removed"}, "inactive"),
        ({"pin_hash": None}, "no_pin"),
        ({"pin_reset_required": True}, "reset_required"),
    ],
)
def test_verify_device_refuses_removed_pinless_or_reset_due_accounts(
    auth: Auth, owner_conn: Conn, account: Account, change: dict[str, Any], refusal: str
) -> None:
    store_code(owner_conn, account.user_id, "new_device", UNTRUSTED)
    set_user(owner_conn, account.user_id, **change)
    result = auth.verify_device()
    assert (result["outcome"], result["refusal"]) == ("refused", refusal)
    assert codes(owner_conn, account.user_id)[0]["consumed"] is False
    assert device_row(owner_conn, account.user_id, UNTRUSTED) is None


def test_verify_device_without_a_code_is_refused(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    result = auth.verify_device()
    assert (result["outcome"], result["refusal"]) == ("refused", "code_expired")


def test_verify_device_counts_a_wrong_code_and_leaves_the_lock_alone(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, failed_attempts=5)
    store_code(owner_conn, account.user_id, "new_device", UNTRUSTED)
    result = auth.verify_device(code_hash=WRONG_CODE_HASH)
    assert (result["outcome"], result["refusal"], result["code_issued"]) == (
        "refused",
        "wrong_code",
        None,
    )
    assert codes(owner_conn, account.user_id)[0]["failed_attempts"] == 1
    assert _counters(owner_conn, account.user_id) == (5, 0)


def test_verify_device_cannot_trust_another_device_with_a_code(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    store_code(owner_conn, account.user_id, "new_device", "device-x")
    result = auth.verify_device(device="device-y")
    assert result["refusal"] == "code_expired"
    assert device_row(owner_conn, account.user_id, "device-y") is None


def test_verify_device_trusts_the_device_clears_both_counters_and_issues_tokens(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, failed_attempts=5, untrusted_failed_attempts=5)
    trust(owner_conn, account.user_id, UNTRUSTED, revoked=True)
    code_id = store_code(owner_conn, account.user_id, "new_device", UNTRUSTED)
    version = user_row(owner_conn, account.user_id)["version"]
    result = auth.verify_device(trust_days=30)
    assert result["outcome"] == "authenticated"
    assert next(c for c in codes(owner_conn, account.user_id) if c["id"] == code_id)["consumed"]
    assert _counters(owner_conn, account.user_id) == (0, 0)
    device = device_row(owner_conn, account.user_id, UNTRUSTED)
    assert device is not None
    assert (device["revoked"], device["trust_expires_at"]) == (False, T0 + timedelta(days=30))
    assert (device["token_hash"], device["remembered"], device["last_used_at"]) == (None, True, T0)
    assert live_tokens(owner_conn, account.user_id, UNTRUSTED) == 1
    assert user_row(owner_conn, account.user_id)["version"] == version + 1
    _assert_attempt(owner_conn, "verify_device", "authenticated", None, account.user_id)


def test_verify_device_without_trust_days_trusts_forever(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    store_code(owner_conn, account.user_id, "new_device", UNTRUSTED)
    assert auth.verify_device()["outcome"] == "authenticated"
    device = device_row(owner_conn, account.user_id, UNTRUSTED)
    assert device is not None
    assert device["trust_expires_at"] is None


def test_verify_device_without_a_membership_is_refused_and_keeps_the_code(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    owner_conn.execute(
        "UPDATE tenancy.memberships SET active = false WHERE user_id = %s", (account.user_id,)
    )
    set_user(owner_conn, account.user_id, untrusted_failed_attempts=4)
    store_code(owner_conn, account.user_id, "new_device", UNTRUSTED)
    result = auth.verify_device()
    assert (result["outcome"], result["refusal"]) == ("refused", "inactive")
    assert codes(owner_conn, account.user_id)[0]["consumed"] is False
    assert device_row(owner_conn, account.user_id, UNTRUSTED) is None
    assert _counters(owner_conn, account.user_id) == (0, 4)


# --- 3.3 request a code ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("purpose", "change", "refusal"),
    [
        ("first_setup", {}, None),  # Jane already has a PIN
        ("pin_reset", {"pin_hash": None}, "no_pin"),
        ("pin_reset", {"status": "removed"}, "inactive"),
        ("new_device", {}, None),
    ],
)
def test_request_code_is_silent_for_an_account_that_is_not_ready(
    auth: Auth,
    owner_conn: Conn,
    account: Account,
    purpose: str,
    change: dict[str, Any],
    refusal: str | None,
) -> None:
    if change:
        set_user(owner_conn, account.user_id, **change)
    result = auth.request_code(purpose)
    assert (result["outcome"], result["refusal"], result["code_id"]) == ("silent", refusal, None)
    assert codes(owner_conn, account.user_id) == []
    operation = "forgot_pin" if purpose == "pin_reset" else "request_code"
    _assert_attempt(owner_conn, operation, "check_email", refusal, account.user_id)


def test_request_code_is_silent_for_an_unknown_number(auth: Auth, owner_conn: Conn) -> None:
    result = auth.request_code("pin_reset", phone="0799999999")
    assert (result["outcome"], result["refusal"]) == ("silent", "unknown_number")
    _assert_attempt(owner_conn, "forgot_pin", "check_email", "unknown_number", None)


def test_request_code_issues_a_code_and_supersedes_older_ones_on_every_device(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    older = store_code(
        owner_conn, account.user_id, "pin_reset", "elsewhere", created_at=T0 - timedelta(minutes=5)
    )
    other_purpose = store_code(
        owner_conn, account.user_id, "new_device", "elsewhere", created_at=T0 - timedelta(minutes=5)
    )
    result = auth.request_code("pin_reset")
    assert (result["outcome"], result["email"], result["code_issued"]) == (
        "check_email",
        account.email,
        True,
    )
    stored = {c["id"]: c for c in codes(owner_conn, account.user_id)}
    issued = stored[UUID(result["code_id"])]
    assert (issued["purpose"], issued["device_id"], issued["consumed"]) == (
        "pin_reset",
        UNTRUSTED,
        False,
    )
    assert stored[older]["consumed"] is True
    assert stored[other_purpose]["consumed"] is False
    _assert_attempt(owner_conn, "forgot_pin", "check_email", None, account.user_id)


def test_request_code_for_a_first_pin(auth: Auth, owner_conn: Conn, account: Account) -> None:
    set_user(owner_conn, account.user_id, pin_hash=None)
    assert auth.request_code("first_setup")["outcome"] == "check_email"


def test_request_code_inside_the_cooldown_is_silent_unless_skipped(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    assert auth.request_code("pin_reset")["outcome"] == "check_email"
    later = T0 + timedelta(seconds=59)
    assert auth.request_code("pin_reset", now=later)["outcome"] == "silent"
    assert auth.request_code("pin_reset", now=later, skip_cooldown=True)["outcome"] == "check_email"
    assert auth.request_code("pin_reset", now=T0 + timedelta(minutes=3))["outcome"] == "check_email"


def test_request_code_past_the_hourly_cap_is_silent(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    for minute in range(5):
        store_code(
            owner_conn,
            account.user_id,
            "new_device",
            f"device-{minute}",
            created_at=T0 - timedelta(minutes=30 + minute),
            consumed=True,
        )
    assert auth.request_code("pin_reset")["outcome"] == "silent"


def test_a_locked_account_may_request_a_reset(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, failed_attempts=5, untrusted_failed_attempts=5)
    assert auth.request_code("pin_reset")["outcome"] == "check_email"


# --- withdrawal after a failed send ---------------------------------------------------------


def test_a_withdrawn_code_starts_no_cooldown_and_counts_toward_no_cap(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    before = attempt_count(owner_conn)
    issued = auth.request_code("pin_reset")
    auth.withdraw(UUID(issued["code_id"]))
    row = codes(owner_conn, account.user_id)[0]
    assert (row["consumed"], row["expires_at"]) == (True, row["created_at"])
    assert attempt_count(owner_conn) == before + 1
    again = auth.request_code("pin_reset", now=T0 + timedelta(seconds=1))
    assert again["outcome"] == "check_email"


def test_withdraw_leaves_a_used_code_alone(auth: Auth, owner_conn: Conn, account: Account) -> None:
    code_id = store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED, consumed=True)
    auth.withdraw(code_id)
    row = codes(owner_conn, account.user_id)[0]
    assert row["expires_at"] == T0 + timedelta(minutes=10)


# --- 3.4 verify a code ----------------------------------------------------------------------


def test_verify_code_refuses_an_account_that_is_not_ready(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    store_code(owner_conn, account.user_id, "first_setup", UNTRUSTED)
    result = auth.verify_code("first_setup")
    assert (result["outcome"], result["refusal"]) == ("refused", None)
    assert codes(owner_conn, account.user_id)[0]["failed_attempts"] == 0


def test_verify_code_counts_a_wrong_code(auth: Auth, owner_conn: Conn, account: Account) -> None:
    store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED)
    result = auth.verify_code("pin_reset", code_hash=WRONG_CODE_HASH)
    assert (result["outcome"], result["refusal"]) == ("refused", "wrong_code")
    assert codes(owner_conn, account.user_id)[0]["failed_attempts"] == 1
    _assert_attempt(owner_conn, "verify_code", "refused", "wrong_code", account.user_id)


def test_verify_code_matches_and_keeps_the_code_for_completion(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED)
    assert auth.verify_code("pin_reset")["outcome"] == "code_verified"
    assert codes(owner_conn, account.user_id)[0]["consumed"] is False
    assert auth.verify_code("pin_reset")["outcome"] == "code_verified"
    _assert_attempt(owner_conn, "verify_code", "code_verified", None, account.user_id)


# --- 3.5 complete a PIN -------------------------------------------------------------------


def test_complete_pin_refuses_an_account_that_is_not_ready(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED)
    set_user(owner_conn, account.user_id, status="removed")
    result = auth.complete_pin("pin_reset")
    assert (result["outcome"], result["refusal"]) == ("refused", "inactive")
    assert user_row(owner_conn, account.user_id)["pin_hash"] == PIN_HASH


def test_complete_pin_counts_a_wrong_code(auth: Auth, owner_conn: Conn, account: Account) -> None:
    store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED)
    result = auth.complete_pin("pin_reset", code_hash=WRONG_CODE_HASH)
    assert (result["outcome"], result["refusal"]) == ("refused", "wrong_code")
    assert codes(owner_conn, account.user_id)[0]["failed_attempts"] == 1
    assert user_row(owner_conn, account.user_id)["pin_hash"] == PIN_HASH


def test_a_reset_refuses_the_pin_being_replaced(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED)
    before = user_row(owner_conn, account.user_id)
    result = auth.complete_pin("pin_reset", new_pin_is_current=True)
    assert (result["outcome"], result["pin_problem"], result["minimum_pin_length"]) == (
        "invalid_pin",
        "unchanged",
        4,
    )
    assert codes(owner_conn, account.user_id)[0]["consumed"] is False
    assert user_row(owner_conn, account.user_id) == before
    _assert_attempt(owner_conn, "complete_pin", "refused", "pin_rule", account.user_id)
    assert auth.complete_pin("pin_reset")["outcome"] == "authenticated"


def test_without_a_valid_code_the_pin_being_replaced_is_not_disclosed(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    result = auth.complete_pin("pin_reset", new_pin_is_current=True)
    assert (result["outcome"], result["pin_problem"]) == ("refused", None)


def test_a_reset_whose_verdict_is_for_a_replaced_hash_changes_nothing(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED)
    set_user(owner_conn, account.user_id, pin_hash=NEW_PIN_HASH)
    before = user_row(owner_conn, account.user_id)
    result = auth.complete_pin("pin_reset", checked_hash=PIN_HASH)
    assert (result["outcome"], result["refusal"]) == ("refused", "verdict_void")
    assert user_row(owner_conn, account.user_id) == before
    assert codes(owner_conn, account.user_id)[0]["consumed"] is False


def test_the_organization_pin_length_is_no_longer_read(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    owner_conn.execute(
        "UPDATE tenancy.organization_security_policies SET pin_length = 6 "
        "WHERE organization_id = %s",
        (account.organization_id,),
    )
    store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED)
    assert auth.complete_pin("pin_reset")["outcome"] == "authenticated"


def test_complete_pin_without_a_membership_is_refused_with_nothing_changed(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    owner_conn.execute(
        "UPDATE tenancy.memberships SET active = false WHERE user_id = %s", (account.user_id,)
    )
    store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED)
    token = store_token(owner_conn, account.user_id, TRUSTED)
    before = user_row(owner_conn, account.user_id)
    result = auth.complete_pin("pin_reset")
    assert (result["outcome"], result["refusal"]) == ("refused", "inactive")
    assert user_row(owner_conn, account.user_id) == before
    assert codes(owner_conn, account.user_id)[0]["consumed"] is False
    assert [
        t["revoked"] for t in tokens(owner_conn, account.user_id) if t["token_hash"] == token
    ] == [False]
    assert device_row(owner_conn, account.user_id, UNTRUSTED) is None


@pytest.mark.parametrize("purpose", ["pin_reset", "first_setup"])
def test_complete_pin_sets_the_pin_ends_every_session_and_trusts_the_device(
    auth: Auth, owner_conn: Conn, account: Account, purpose: str
) -> None:
    if purpose == "first_setup":
        set_user(owner_conn, account.user_id, pin_hash=None)
    set_user(owner_conn, account.user_id, failed_attempts=5, untrusted_failed_attempts=5)
    store_code(owner_conn, account.user_id, purpose, UNTRUSTED)
    other_code = store_code(owner_conn, account.user_id, "new_device", "elsewhere")
    store_token(owner_conn, account.user_id, TRUSTED)
    store_token(owner_conn, account.user_id, "elsewhere")
    before = user_row(owner_conn, account.user_id)
    refresh_hash = new_token_hash()
    result = auth.complete_pin(purpose, refresh_hash=refresh_hash, trust_days=7)
    assert result["outcome"] == "authenticated"
    after = user_row(owner_conn, account.user_id)
    assert after["pin_hash"] == NEW_PIN_HASH
    assert after["security_version"] == before["security_version"] + 1
    assert result["security_version"] == after["security_version"]
    assert (after["failed_attempts"], after["untrusted_failed_attempts"]) == (0, 0)
    assert (after["pin_reset_required"], after["last_signed_in_at"]) == (False, T0)
    assert after["version"] == before["version"] + 1
    live = [t for t in tokens(owner_conn, account.user_id) if not t["revoked"]]
    assert [(t["token_hash"], t["device_id"]) for t in live] == [(refresh_hash, UNTRUSTED)]
    assert all(c["consumed"] for c in codes(owner_conn, account.user_id))
    assert next(c for c in codes(owner_conn, account.user_id) if c["id"] == other_code)["consumed"]
    device = device_row(owner_conn, account.user_id, UNTRUSTED)
    assert device is not None
    assert (device["revoked"], device["trust_expires_at"]) == (False, T0 + timedelta(days=7))
    assert (device["token_hash"], device["remembered"]) == (None, True)
    # A reset removes every other device; a first PIN leaves them (a PIN-less person has none
    # but a stale row), and their access tokens die with the security version either way.
    old = device_row(owner_conn, account.user_id, TRUSTED)
    assert old is not None and old["revoked"] is (purpose == "pin_reset")
    _assert_attempt(owner_conn, "complete_pin", "authenticated", None, account.user_id)


# --- 3.6 refresh --------------------------------------------------------------------------


def test_refresh_refuses_an_unknown_token_and_writes_nothing(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    store_token(owner_conn, account.user_id, TRUSTED)
    result = auth.refresh(digest("unknown"))
    assert (result["outcome"], result["refusal"]) == ("refused", "token_unknown")
    assert live_tokens(owner_conn, account.user_id) == 1
    _assert_attempt(owner_conn, "refresh", "refused", "token_unknown", None)


def test_refresh_refuses_a_token_from_another_device_and_writes_nothing(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED)
    result = auth.refresh(token, device="another")
    assert (result["outcome"], result["refusal"]) == ("refused", "token_unknown")
    assert live_tokens(owner_conn, account.user_id) == 1


def test_refresh_for_an_inactive_user_revokes_every_token(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED)
    store_token(owner_conn, account.user_id, "elsewhere")
    set_user(owner_conn, account.user_id, status="removed")
    result = auth.refresh(token)
    assert (result["outcome"], result["refusal"]) == ("refused", "inactive")
    assert live_tokens(owner_conn, account.user_id) == 0


def test_rotation_then_replay_revokes_the_devices_live_tokens(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    first = store_token(owner_conn, account.user_id, TRUSTED)
    other_device = store_token(owner_conn, account.user_id, "elsewhere")
    trust(owner_conn, account.user_id, "elsewhere")
    second = new_token_hash()
    rotated = auth.refresh(first, new_hash=second)
    assert rotated["outcome"] == "authenticated"
    by_hash = {t["token_hash"]: t for t in tokens(owner_conn, account.user_id)}
    assert (by_hash[first]["revoked"], by_hash[first]["version"]) == (True, 1)
    assert by_hash[second]["revoked"] is False
    replayed = auth.refresh(first)
    assert (replayed["outcome"], replayed["refusal"]) == ("refused", "token_replayed")
    by_hash = {t["token_hash"]: t for t in tokens(owner_conn, account.user_id)}
    assert by_hash[second]["revoked"] is True
    assert by_hash[other_device]["revoked"] is False
    device = device_row(owner_conn, account.user_id, TRUSTED)
    assert device is not None
    assert device["revoked"] is False


def test_refresh_refuses_an_expired_token_and_writes_nothing(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED, expires_at=T0)
    result = auth.refresh(token)
    assert (result["outcome"], result["refusal"]) == ("refused", "token_expired")
    assert live_tokens(owner_conn, account.user_id) == 1


def test_refresh_refuses_while_locked_on_every_device(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED)
    set_user(owner_conn, account.user_id, failed_attempts=5)
    result = auth.refresh(token)
    assert (result["outcome"], result["refusal"]) == ("refused", "locked")
    assert live_tokens(owner_conn, account.user_id) == 1
    set_user(owner_conn, account.user_id, failed_attempts=0, untrusted_failed_attempts=5)
    assert auth.refresh(token)["outcome"] == "authenticated"


def test_a_refresh_moves_the_last_use_and_not_the_last_sign_in(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED)
    later = T0 + timedelta(days=29)
    assert auth.refresh(token, now=later)["outcome"] == "authenticated"
    device = device_row(owner_conn, account.user_id, TRUSTED)
    assert device is not None and device["last_used_at"] == later
    assert user_row(owner_conn, account.user_id)["last_signed_in_at"] is None


@pytest.mark.parametrize("state", ["revoked", "expired", "unused"])
def test_refresh_refuses_an_untrusted_device(
    auth: Auth, owner_conn: Conn, account: Account, state: str
) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED)
    trust(
        owner_conn,
        account.user_id,
        TRUSTED,
        revoked=state == "revoked",
        expires_at=T0 if state == "expired" else None,
        last_used_at=T0 - timedelta(days=90) if state == "unused" else T0,
    )
    result = auth.refresh(token)
    assert (result["outcome"], result["refusal"]) == ("refused", "device_untrusted")
    assert live_tokens(owner_conn, account.user_id) == 1


def test_refresh_without_a_membership_keeps_the_token(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED)
    owner_conn.execute("DELETE FROM tenancy.person_roles WHERE user_id = %s", (account.user_id,))
    result = auth.refresh(token)
    assert (result["outcome"], result["refusal"]) == ("refused", "inactive")
    assert live_tokens(owner_conn, account.user_id) == 1


def test_refresh_reads_fresh_claims(auth: Auth, owner_conn: Conn, account: Account) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED)
    owner_conn.execute(
        "UPDATE tenancy.person_roles SET role_id = r.id FROM tenancy.roles AS r "
        "WHERE r.organization_id = person_roles.organization_id AND r.name = 'Revenue clerk' "
        "AND person_roles.user_id = %s",
        (account.user_id,),
    )
    owner_conn.execute(
        "UPDATE tenancy.memberships SET first_name = 'Janet' WHERE user_id = %s",
        (account.user_id,),
    )
    result = auth.refresh(token)
    assert result["outcome"] == "authenticated"
    assert (result["role"], result["first_name"]) == ("Revenue clerk", "Janet")
    assert result["permissions"] == [
        "dash.gaps",
        "revenue.view",
        "revenue.capture",
        "dash.capture",
        "revenue.no_earnings",
    ]
    assert result["security_version"] == user_row(owner_conn, account.user_id)["security_version"]


# --- 3.7 sign-out and 3.8 device revoke -----------------------------------------------------


def test_sign_out_revokes_the_devices_live_tokens_only(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED)
    store_token(owner_conn, account.user_id, TRUSTED)
    store_token(owner_conn, account.user_id, "elsewhere")
    assert auth.sign_out(token)["outcome"] == "signed_out"
    assert live_tokens(owner_conn, account.user_id, TRUSTED) == 0
    assert live_tokens(owner_conn, account.user_id, "elsewhere") == 1
    assert device_row(owner_conn, account.user_id, TRUSTED)["revoked"] is False  # type: ignore[index]
    _assert_attempt(owner_conn, "sign_out", "signed_out", None, account.user_id)


def test_signing_out_of_a_device_trusted_for_one_session_ends_its_row(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    trust(owner_conn, account.user_id, "borrowed", remembered=False)
    token = store_token(owner_conn, account.user_id, "borrowed")
    assert auth.sign_out(token, device="borrowed")["outcome"] == "signed_out"
    assert device_row(owner_conn, account.user_id, "borrowed")["revoked"] is True  # type: ignore[index]


def test_sign_out_with_an_unmatched_token_changes_nothing(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED)
    assert auth.sign_out(token, device="elsewhere")["outcome"] == "signed_out"
    assert auth.sign_out(digest("nothing"))["outcome"] == "signed_out"
    assert live_tokens(owner_conn, account.user_id) == 1
    _assert_attempt(owner_conn, "sign_out", "signed_out", "token_unknown", None)


def test_revoke_device_revokes_trust_tokens_and_codes_of_that_device(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    store_token(owner_conn, account.user_id, TRUSTED)
    store_token(owner_conn, account.user_id, "elsewhere")
    trust(owner_conn, account.user_id, "elsewhere")
    store_code(owner_conn, account.user_id, "pin_reset", TRUSTED)
    elsewhere_code = store_code(owner_conn, account.user_id, "new_device", "elsewhere")
    version = user_row(owner_conn, account.user_id)
    assert auth.revoke_device(account.user_id)["outcome"] == "device_revoked"
    assert device_row(owner_conn, account.user_id, TRUSTED)["revoked"] is True  # type: ignore[index]
    assert device_row(owner_conn, account.user_id, "elsewhere")["revoked"] is False  # type: ignore[index]
    assert live_tokens(owner_conn, account.user_id, TRUSTED) == 0
    assert live_tokens(owner_conn, account.user_id, "elsewhere") == 1
    states = {c["id"]: c["consumed"] for c in codes(owner_conn, account.user_id)}
    assert states[elsewhere_code] is False
    assert sum(states.values()) == 1
    after = user_row(owner_conn, account.user_id)
    assert (after["version"], after["security_version"]) == (
        version["version"],
        version["security_version"],
    )
    _assert_attempt(owner_conn, "revoke_device", "device_revoked", None, account.user_id)


def test_revoke_device_of_an_unknown_device_still_answers(auth: Auth, account: Account) -> None:
    assert auth.revoke_device(account.user_id, device="never-seen")["outcome"] == "device_revoked"


# --- 3.10 session resolution --------------------------------------------------------------


def test_resolve_session_returns_the_organization_and_role(auth: Auth, account: Account) -> None:
    assert auth.resolve(account.user_id, 0) == {
        "organization_id": str(account.organization_id),
        "role": "Owner",
    }


@pytest.mark.parametrize("cause", ["unknown user", "removed", "version moved", "device untrusted"])
def test_resolve_session_refuses_each_failure_cause(
    auth: Auth, owner_conn: Conn, account: Account, cause: str
) -> None:
    user_id, version, device = account.user_id, 0, TRUSTED
    if cause == "unknown user":
        user_id = UUID(int=1)
    elif cause == "removed":
        set_user(owner_conn, account.user_id, status="removed")
    elif cause == "version moved":
        version = 1
    else:
        device = UNTRUSTED
    with pytest.raises(psycopg.Error) as caught:
        auth.resolve(user_id, version, device=device)
    assert (caught.value.sqlstate, caught.value.diag.message_primary) == (
        "XC401",
        "session_invalid",
    )


@pytest.mark.parametrize("state", ["revoked", "expired"])
def test_resolve_session_refuses_a_revoked_or_expired_device(
    auth: Auth, owner_conn: Conn, account: Account, state: str
) -> None:
    trust(
        owner_conn,
        account.user_id,
        TRUSTED,
        revoked=state == "revoked",
        expires_at=T0 if state == "expired" else None,
    )
    with pytest.raises(psycopg.Error) as caught:
        auth.resolve(account.user_id, 0)
    assert caught.value.sqlstate == "XC401"


def test_resolve_session_does_not_check_the_lock(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, failed_attempts=5)
    assert auth.resolve(account.user_id, 0)["role"] == "Owner"


@pytest.mark.parametrize("remembered", [True, False])
def test_a_session_needs_a_live_device_row_remembered_or_not(
    auth: Auth, owner_conn: Conn, account: Account, remembered: bool
) -> None:
    trust(owner_conn, account.user_id, TRUSTED, remembered=remembered)
    assert auth.resolve(account.user_id, 0, now=T0 + timedelta(days=89))["role"] == "Owner"
    with pytest.raises(psycopg.Error) as caught:
        auth.resolve(account.user_id, 0, now=T0 + timedelta(days=90))
    assert caught.value.sqlstate == "XC401"


# --- one attempt row per decision ---------------------------------------------------------


def test_each_decision_routine_writes_exactly_one_attempt_row(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED)
    calls = [
        lambda: auth.sign_in(account.user_id),
        lambda: auth.sign_in(None),
        auth.verify_device,
        lambda: auth.request_code("pin_reset"),
        lambda: auth.verify_code("pin_reset"),
        lambda: auth.complete_pin("pin_reset", code_hash=WRONG_CODE_HASH),
        lambda: auth.refresh(token),
        lambda: auth.sign_out(digest("nothing")),
        lambda: auth.revoke_device(account.user_id, device="elsewhere"),
        lambda: auth.start(phone=PHONE),
        lambda: auth.start(phone="0799999999"),
        lambda: call(
            auth.conn,
            "auth_pin",
            "req-pin",
            PHONE,
            UNTRUSTED,
            None,
            False,
            PIN_HASH,
            CODE_HASH,
            new_token_hash(),
            False,
            T0,
        ),
        lambda: auth.check_code("pin_reset"),
        lambda: auth.resend_code("pin_reset"),
        lambda: auth.change_pin(account.user_id, current_ok=False),
    ]
    for decide in calls:
        before = attempt_count(owner_conn)
        decide()
        assert attempt_count(owner_conn) == before + 1
    before = attempt_count(owner_conn)
    assert auth.lookup() is not None
    assert auth.lookup("0799999999", pin_try=False) is None
    assert auth.lookup_user(account.user_id) is not None
    assert [d["this_device"] for d in auth.device_list(account.user_id)] == [True]
    auth.resolve(account.user_id, user_row(owner_conn, account.user_id)["security_version"])
    assert attempt_count(owner_conn) == before
    assert all(row["request_id"].startswith("req-") for row in attempts(owner_conn))


# --- section 4: the state machine as a table ------------------------------------------------

STATE_MACHINE = [
    # (name, start: failed, untrusted; device; pin_ok; outcome, refusal, end)
    ("wrong pin counts on a trusted device", (0, 0), TRUSTED, False,
     "refused", "wrong_pin", (1, 0)),
    ("the fifth wrong pin on a trusted device locks every device", (4, 0), TRUSTED, False,
     "paused", "wrong_pin", (5, 0)),
    ("wrong pin counts on an untrusted device", (0, 3), UNTRUSTED, False,
     "refused", "wrong_pin", (0, 4)),
    ("the fifth wrong pin on an untrusted device locks new devices", (0, 4), UNTRUSTED, False,
     "refused", "wrong_pin", (0, 5)),
    ("locked for new devices: an untrusted device changes nothing", (0, 5), UNTRUSTED, True,
     "refused", "locked", (0, 5)),
    ("locked for new devices: a trusted device signs in", (0, 5), TRUSTED, True,
     "authenticated", None, (0, 5)),
    ("locked on every device: a trusted device is paused", (5, 0), TRUSTED, True,
     "paused", "locked", (5, 0)),
    ("locked on every device: an untrusted device is refused", (5, 0), UNTRUSTED, True,
     "refused", "locked", (5, 0)),
    ("right pin on a trusted device clears the trusted counter only", (3, 4), TRUSTED, True,
     "authenticated", None, (0, 4)),
    ("right pin on an untrusted device asks for a code", (3, 4), UNTRUSTED, True,
     "verification_required", None, (3, 4)),
]  # fmt: skip


@pytest.mark.parametrize(
    ("start", "device", "pin_ok", "outcome", "refusal", "end"),
    [row[1:] for row in STATE_MACHINE],
    ids=[row[0] for row in STATE_MACHINE],
)
def test_state_machine_transition(
    auth: Auth,
    owner_conn: Conn,
    account: Account,
    start: tuple[int, int],
    device: str,
    pin_ok: bool,
    outcome: str,
    refusal: str | None,
    end: tuple[int, int],
) -> None:
    set_user(
        owner_conn, account.user_id, failed_attempts=start[0], untrusted_failed_attempts=start[1]
    )
    result = auth.sign_in(account.user_id, device=device, pin_ok=pin_ok)
    assert (result["outcome"], result["refusal"]) == (outcome, refusal)
    assert _counters(owner_conn, account.user_id) == end


# --- section 4: what resets the counters, and what never does --------------------------------


def _reset_by(event: str, auth: Auth, owner: Conn, operator: Conn, account: Account) -> None:
    if event == "right pin on a trusted device":
        auth.sign_in(account.user_id, pin_ok=True)
    elif event == "verified new device":
        store_code(owner, account.user_id, "new_device", UNTRUSTED)
        auth.verify_device()
    elif event == "pin reset":
        store_code(owner, account.user_id, "pin_reset", UNTRUSTED)
        auth.complete_pin("pin_reset")
    elif event == "operator clear pause":
        call(operator, "ops_clear_pause", "test-operator", "req", account.email, T0)
    elif event == "refresh":
        auth.refresh(store_token(owner, account.user_id, TRUSTED))
    elif event == "sign-out":
        auth.sign_out(store_token(owner, account.user_id, TRUSTED))
    elif event == "device revoke":
        auth.revoke_device(account.user_id)


RESETS = [
    # (event, trusted-device counter reset?, untrusted-device counter reset?)
    ("right pin on a trusted device", True, False),
    ("verified new device", True, True),
    ("pin reset", True, True),
    ("operator clear pause", True, True),
    ("refresh", False, False),
    ("sign-out", False, False),
    ("device revoke", False, False),
]


@pytest.mark.parametrize(("event", "trusted_reset", "untrusted_reset"), RESETS)
def test_counter_resets(
    auth: Auth,
    owner_conn: Conn,
    operator_conn: Conn,
    account: Account,
    event: str,
    trusted_reset: bool,
    untrusted_reset: bool,
) -> None:
    set_user(owner_conn, account.user_id, failed_attempts=3, untrusted_failed_attempts=4)
    _reset_by(event, auth, owner_conn, operator_conn, account)
    failed, untrusted = _counters(owner_conn, account.user_id)
    assert failed == (0 if trusted_reset else 3)
    assert untrusted == (0 if untrusted_reset else 4)


# --- section 6: the revocation matrix (rows caused by these routines) -----------------------


def _state(auth: Auth, owner: Conn, account: Account, version: int) -> tuple[bool, int, bool]:
    device = device_row(owner, account.user_id, TRUSTED)
    trusted = device is not None and not device["revoked"]
    return _session_alive(auth, account, version), live_tokens(owner, account.user_id), trusted


def _version(owner: Conn, account: Account) -> int:
    return int(user_row(owner, account.user_id)["security_version"])


def test_matrix_sign_out(auth: Auth, owner_conn: Conn, account: Account) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED)
    version = _version(owner_conn, account)
    auth.sign_out(token)
    assert _state(auth, owner_conn, account, version) == (True, 0, True)


def test_matrix_device_revoke(auth: Auth, owner_conn: Conn, account: Account) -> None:
    store_token(owner_conn, account.user_id, TRUSTED)
    version = _version(owner_conn, account)
    auth.revoke_device(account.user_id)
    assert _state(auth, owner_conn, account, version) == (False, 0, False)


def test_matrix_pin_set_or_reset(auth: Auth, owner_conn: Conn, account: Account) -> None:
    store_token(owner_conn, account.user_id, TRUSTED)
    store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED)
    version = _version(owner_conn, account)
    auth.complete_pin("pin_reset")
    # A reset removes the old device; the new pair is the completing device's.
    assert _state(auth, owner_conn, account, version) == (False, 1, False)
    assert live_tokens(owner_conn, account.user_id, UNTRUSTED) == 1
    assert _session_alive(auth, account, version + 1, UNTRUSTED)


def test_matrix_operator_remove(
    auth: Auth, owner_conn: Conn, operator_conn: Conn, account: Account
) -> None:
    store_token(owner_conn, account.user_id, TRUSTED)
    version = _version(owner_conn, account)
    call(operator_conn, "ops_remove_user", "test-operator", "req", account.email, T0)
    assert _state(auth, owner_conn, account, version) == (False, 0, True)
    assert _version(owner_conn, account) == version + 1


def test_matrix_operator_revoke_sessions(
    auth: Auth, owner_conn: Conn, operator_conn: Conn, account: Account
) -> None:
    store_token(owner_conn, account.user_id, TRUSTED)
    version = _version(owner_conn, account)
    call(operator_conn, "ops_revoke_sessions", "test-operator", "req", account.email, T0)
    assert _state(auth, owner_conn, account, version) == (False, 0, False)
    assert _version(owner_conn, account) == version + 1


def test_matrix_trust_expiry(auth: Auth, owner_conn: Conn, account: Account) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED)
    trust(owner_conn, account.user_id, TRUSTED, expires_at=T0 + timedelta(days=1))
    later = T0 + timedelta(days=1)
    with pytest.raises(psycopg.Error):
        auth.resolve(account.user_id, 0, now=later)
    assert auth.refresh(token, now=later)["refusal"] == "device_untrusted"
    assert (
        auth.resolve(account.user_id, 0, now=later - timedelta(microseconds=1))["role"] == "Owner"
    )


def test_matrix_lock(auth: Auth, owner_conn: Conn, account: Account) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED)
    set_user(owner_conn, account.user_id, failed_attempts=5)
    assert auth.refresh(token)["outcome"] == "refused"
    assert _state(auth, owner_conn, account, _version(owner_conn, account)) == (True, 1, True)


def test_matrix_reprovisioning_a_changed_account(
    auth: Auth, owner_conn: Conn, operator_conn: Conn, account: Account
) -> None:
    store_token(owner_conn, account.user_id, TRUSTED)
    version = _version(owner_conn, account)
    call(
        operator_conn,
        "ops_provision_user",
        "test-operator",
        "req",
        account.email,
        "0722222222",
        None,
        None,
        None,
        None,
        T0,
    )
    assert _state(auth, owner_conn, account, version) == (False, 0, False)
    assert _version(owner_conn, account) == version + 1
    assert user_row(owner_conn, account.user_id)["phone_number"] == "+254722222222"


# --- an end-to-end first sign-in ------------------------------------------------------------


def test_a_provisioned_person_sets_a_pin_and_signs_in(
    auth: Auth, owner_conn: Conn, operator_conn: Conn
) -> None:
    person = make_account(operator_conn, owner_conn, pin=False, trusted=())
    issued = auth.request_code("first_setup", device="phone")
    assert issued["outcome"] == "check_email"
    assert auth.verify_code("first_setup", device="phone")["outcome"] == "code_verified"
    completed = auth.complete_pin("first_setup", device="phone")
    assert completed["outcome"] == "authenticated"
    state = auth.lookup(NORMALIZED, "phone")
    assert state is not None
    assert (state["pin_hash"], state["device_trusted"]) == (NEW_PIN_HASH, True)
    signed_in = auth.sign_in(
        person.user_id, device="phone", pin_ok=True, checked_hash=state["pin_hash"]
    )
    assert signed_in["outcome"] == "authenticated"


# --- the v2.33 sign-in (docs/07-auth.md section 12) ----------------------------------------

TOKEN_HASH = digest("device-token")
PHONE_DEVICE = "phone-with-token"
UNKNOWN = "0799999999"


def _sign_in_log(owner: Conn, user_id: UUID) -> list[dict[str, Any]]:
    return owner.execute(
        "SELECT reason, before, after, actor_id FROM tenancy.change_log "
        "WHERE section = 'signIn' AND entity_id = %s ORDER BY version",
        (user_id,),
    ).fetchall()


def _change_log_count(owner: Conn) -> int:
    row = owner.execute("SELECT count(*) AS n FROM tenancy.change_log").fetchone()
    assert row is not None
    return int(row["n"])


def _with_token(owner: Conn, account: Account) -> None:
    trust(owner, account.user_id, PHONE_DEVICE, token_hash=TOKEN_HASH, name="Jane phone")


def _no_name(result: dict[str, Any]) -> None:
    assert (result["first_name"], result["last_name"], result["role"], result["user_id"]) == (
        None,
        None,
        None,
        None,
    )


def test_the_number_step_routes_by_account_state(
    auth: Auth, owner_conn: Conn, operator_conn: Conn, account: Account
) -> None:
    answers = [auth.start(), auth.start(phone=UNKNOWN)]
    assert [(a["outcome"], a["purpose"]) for a in answers] == [
        ("pin_required", None),
        ("pin_required", None),
    ]
    _assert_attempt(owner_conn, "start", "pin_required", "unknown_number", None)
    newcomer = make_account(
        operator_conn, owner_conn, email="new@example.com", phone="0722000001", pin=False
    )
    first = auth.start(phone="0722000001")
    assert (first["outcome"], first["purpose"], first["masked_email"]) == (
        "verification_required",
        "first_setup",
        "n***@example.com",
    )
    set_user(owner_conn, account.user_id, pin_reset_required=True)
    reset = auth.start()
    assert (reset["outcome"], reset["purpose"]) == ("verification_required", "pin_reset")
    set_user(owner_conn, account.user_id, pin_reset_required=False, failed_attempts=5)
    assert auth.start()["outcome"] == "pin_locked"
    set_user(owner_conn, account.user_id, failed_attempts=0, untrusted_failed_attempts=5)
    assert auth.start()["outcome"] == "pin_locked"
    _with_token(owner_conn, account)
    trusted = auth.start(device=PHONE_DEVICE, token_hash=TOKEN_HASH)
    assert trusted["outcome"] == "pin_required"
    set_user(owner_conn, newcomer.user_id, status="removed")
    assert auth.start(phone="0722000001")["outcome"] == "blocked"
    owner_conn.execute(
        "UPDATE tenancy.memberships SET active = false WHERE user_id = %s", (account.user_id,)
    )
    assert auth.start()["outcome"] == "blocked"
    for answer in (*answers, first, reset, trusted):
        _no_name(answer)


def test_the_number_step_sends_a_first_sign_in_or_reset_code(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, pin_reset_required=True)
    issued = auth.start()
    assert (issued["outcome"], issued["code_issued"], issued["email"]) == (
        "verification_required",
        True,
        account.email,
    )
    stored = codes(owner_conn, account.user_id)
    assert [(c["purpose"], c["device_id"], c["code_hash"]) for c in stored] == [
        ("pin_reset", UNTRUSTED, CODE_HASH)
    ]
    silent = auth.start(now=T0 + timedelta(seconds=30))
    assert (silent["outcome"], silent["purpose"], silent["code_issued"], silent["email"]) == (
        "verification_required",
        "pin_reset",
        False,
        None,
    )
    assert len(codes(owner_conn, account.user_id)) == 1
    assert _counters(owner_conn, account.user_id) == (0, 0)


def test_an_unknown_number_counts_down_and_locks_like_a_real_one(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    for left in (4, 3, 2, 1):
        real = auth.pin(pin_ok=False)
        unknown = auth.pin(phone=UNKNOWN, pin_ok=False, checked_hash=None)
        assert (real["outcome"], real["tries_left"]) == ("refused", left)
        assert (unknown["outcome"], unknown["tries_left"]) == ("refused", left)
    assert auth.pin(pin_ok=False)["outcome"] == "pin_locked"
    assert auth.pin(phone=UNKNOWN, pin_ok=False, checked_hash=None)["outcome"] == "pin_locked"
    assert auth.pin(phone=UNKNOWN, pin_ok=True, checked_hash=None)["outcome"] == "pin_locked"
    assert auth.start()["outcome"] == auth.start(phone=UNKNOWN)["outcome"] == "pin_locked"
    assert _counters(owner_conn, account.user_id) == (0, 5)


def test_an_unknown_number_has_the_reset_code_a_stranger_could_ask_for(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    for phone in (PHONE, UNKNOWN):
        assert auth.check_code("pin_reset", phone=phone)["refusal"] == "code_expired"
        auth.request_code("pin_reset", phone=phone)
    for left in (2, 1):
        for phone in (PHONE, UNKNOWN):
            wrong = auth.check_code("pin_reset", phone=phone, code_hash=WRONG_CODE_HASH)
            assert (wrong["outcome"], wrong["tries_left"]) == ("refused", left)
    for phone in (PHONE, UNKNOWN):
        third = auth.check_code("pin_reset", phone=phone, code_hash=WRONG_CODE_HASH)
        assert (third["outcome"], third["purpose"]) == ("code_resent", "pin_reset")
    assert auth.check_code("new_device", phone=UNKNOWN)["refusal"] == "code_expired"


def test_the_simulated_reset_code_belongs_to_the_device_that_asked_for_it(
    auth: Auth, account: Account
) -> None:
    for phone in (PHONE, UNKNOWN):
        auth.request_code("pin_reset", phone=phone, device="stranger-a")
        elsewhere = auth.check_code(
            "pin_reset", phone=phone, device="stranger-b", code_hash=WRONG_CODE_HASH
        )
        assert (elsewhere["refusal"], elsewhere.get("tries_left")) == ("code_expired", None)
        here = auth.check_code(
            "pin_reset", phone=phone, device="stranger-a", code_hash=WRONG_CODE_HASH
        )
        assert (here["outcome"], here["tries_left"]) == ("refused", 2)


def test_five_wrong_pins_on_a_trusted_device_lock_every_device(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    _with_token(owner_conn, account)
    token = store_token(owner_conn, account.user_id, PHONE_DEVICE)
    for left in (4, 3, 2, 1):
        result = auth.pin(device=PHONE_DEVICE, token_hash=TOKEN_HASH, pin_ok=False)
        assert (result["outcome"], result["tries_left"]) == ("refused", left)
    assert auth.pin(device=PHONE_DEVICE, token_hash=TOKEN_HASH, pin_ok=False)["outcome"] == (
        "pin_locked"
    )
    assert _counters(owner_conn, account.user_id) == (5, 0)
    for device, token_hash in ((PHONE_DEVICE, TOKEN_HASH), (UNTRUSTED, None)):
        result = auth.pin(device=device, token_hash=token_hash, pin_ok=True)
        assert result["outcome"] == "pin_locked"
    assert _counters(owner_conn, account.user_id) == (5, 0)
    assert auth.refresh(token, device=PHONE_DEVICE)["refusal"] == "locked"


def test_five_wrong_pins_from_untrusted_devices_leave_trusted_devices_working(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    _with_token(owner_conn, account)
    for attempt in range(5):
        auth.pin(device=f"stranger-{attempt}", pin_ok=False)
    assert auth.pin(device="stranger-9", pin_ok=True)["outcome"] == "pin_locked"
    signed_in = auth.pin(device=PHONE_DEVICE, token_hash=TOKEN_HASH, pin_ok=True)
    assert signed_in["outcome"] == "authenticated"
    assert _counters(owner_conn, account.user_id) == (0, 5)


def test_a_right_pin_on_a_trusted_device_does_not_clear_the_untrusted_count(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    _with_token(owner_conn, account)
    for _ in range(4):
        auth.pin(pin_ok=False)
    assert auth.pin(device=PHONE_DEVICE, token_hash=TOKEN_HASH)["outcome"] == "authenticated"
    assert auth.pin(pin_ok=False)["outcome"] == "pin_locked"


def test_two_wrong_pins_at_once_both_count_toward_the_lock(
    app_url: str, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, failed_attempts=3)
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as first,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as second,
    ):
        started = threading.Event()
        answers: list[dict[str, Any]] = []

        def second_attempt() -> None:
            started.set()
            answers.append(Auth(second).sign_in(account.user_id, pin_ok=False))

        with first.transaction():
            answers.append(Auth(first).sign_in(account.user_id, pin_ok=False))
            worker = threading.Thread(target=second_attempt)
            worker.start()
            assert started.wait(10)
            worker.join(0.5)
            assert worker.is_alive()
        worker.join(10)
    assert [(a["outcome"], a["refusal"]) for a in answers] == [
        ("refused", "wrong_pin"),
        ("paused", "wrong_pin"),
    ]
    assert _counters(owner_conn, account.user_id) == (5, 0)
    locks = [r for r in _sign_in_log(owner_conn, account.user_id) if "locked" in r["reason"]]
    assert len(locks) == 1


def test_only_a_reset_with_a_code_or_clear_pause_unlocks(
    auth: Auth, owner_conn: Conn, operator_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, failed_attempts=5, untrusted_failed_attempts=5)
    much_later = T0 + YEAR
    trust(owner_conn, account.user_id, TRUSTED, last_used_at=much_later)
    assert auth.sign_in(account.user_id, pin_ok=True, now=much_later)["refusal"] == "locked"
    cleared = call(operator_conn, "ops_clear_pause", "test-operator", "req", account.email, T0)
    assert cleared == {"user_id": str(account.user_id), "was_locked": True}
    assert _counters(owner_conn, account.user_id) == (0, 0)
    set_user(owner_conn, account.user_id, failed_attempts=5, untrusted_failed_attempts=5)
    store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED)
    assert auth.complete_pin("pin_reset")["outcome"] == "authenticated"
    assert _counters(owner_conn, account.user_id) == (0, 0)


def test_the_lock_is_written_to_the_change_log(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    for _ in range(5):
        auth.sign_in(account.user_id, pin_ok=False)
    rows = _sign_in_log(owner_conn, account.user_id)
    assert [r["reason"] for r in rows] == ["PIN locked after 5 wrong tries"]
    assert rows[0]["actor_id"] == account.user_id
    assert (rows[0]["before"], rows[0]["after"]) == (
        '{"Status":"Active","Devices":[null]}',
        '{"Status":"Locked","Devices":[null]}',
    )


def test_ordinary_sign_ins_go_to_the_history_not_the_change_log(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    before = (_change_log_count(owner_conn), attempt_count(owner_conn))
    assert auth.sign_in(account.user_id, pin_ok=True)["outcome"] == "authenticated"
    assert (_change_log_count(owner_conn), attempt_count(owner_conn)) == (before[0], before[1] + 1)
    assert user_row(owner_conn, account.user_id)["last_signed_in_at"] == T0


def test_the_third_wrong_code_voids_it_and_issues_a_replacement(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    old = store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED)
    for left in (2, 1):
        wrong = auth.check_code("pin_reset", code_hash=WRONG_CODE_HASH)
        assert (wrong["outcome"], wrong["tries_left"]) == ("refused", left)
    third = auth.check_code("pin_reset", code_hash=WRONG_CODE_HASH, now=T0 + timedelta(seconds=20))
    assert (third["outcome"], third["code_issued"], third["email"]) == (
        "code_resent",
        True,
        account.email,
    )
    stored = {c["id"]: c for c in codes(owner_conn, account.user_id)}
    assert stored[old]["consumed"] is True
    new = stored[UUID(third["code_id"])]
    assert (new["code_hash"], new["consumed"], new["purpose"]) == (
        NEW_CODE_HASH,
        False,
        "pin_reset",
    )
    assert auth.check_code("pin_reset", code_hash=NEW_CODE_HASH)["outcome"] == "code_verified"
    store_code(owner_conn, account.user_id, "new_device", UNTRUSTED)
    for _ in range(2):
        auth.verify_device(code_hash=WRONG_CODE_HASH)
    released = auth.verify_device(code_hash=WRONG_CODE_HASH, now=T0 + timedelta(minutes=2))
    assert (released["outcome"], released["refusal"], released["code_issued"]) == (
        "refused",
        "wrong_code",
        True,
    )


def test_a_new_device_code_is_resent_only_after_a_right_pin(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    nothing = auth.resend_code("new_device")
    assert (nothing["outcome"], nothing["code_issued"]) == ("verification_required", False)
    assert codes(owner_conn, account.user_id) == []
    asked = auth.sign_in(account.user_id, device=UNTRUSTED, pin_ok=True)
    assert asked["code_issued"] is True
    again = auth.resend_code("new_device", now=T0 + timedelta(minutes=2))
    assert (again["outcome"], again["code_issued"]) == ("verification_required", True)
    elsewhere = auth.resend_code("new_device", device="elsewhere", now=T0 + timedelta(minutes=4))
    assert elsewhere["code_issued"] is False


def test_device_token_is_stored_only_as_its_digest(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    store_code(owner_conn, account.user_id, "new_device", PHONE_DEVICE)
    result = auth.check_code(
        "new_device", device=PHONE_DEVICE, token_hash=TOKEN_HASH, name="Jane phone"
    )
    assert (result["outcome"], result["device_token_issued"]) == ("authenticated", True)
    device = device_row(owner_conn, account.user_id, PHONE_DEVICE)
    assert device is not None
    assert (device["token_hash"], device["name"], device["remembered"]) == (
        TOKEN_HASH,
        "Jane phone",
        True,
    )
    assert [r["reason"] for r in _sign_in_log(owner_conn, account.user_id)] == ["Device trusted"]


def test_a_device_trusted_with_a_token_is_not_trusted_by_its_id_on_the_old_routes(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    _with_token(owner_conn, account)
    old_route = auth.sign_in(account.user_id, device=PHONE_DEVICE, pin_ok=True)
    assert old_route["outcome"] == "verification_required"
    new_route = auth.pin(device=PHONE_DEVICE, token_hash=TOKEN_HASH, pin_ok=True)
    assert new_route["outcome"] == "authenticated"


def test_a_new_route_with_no_token_does_not_trust_a_legacy_row_by_device_id(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    no_token = auth.pin(device=TRUSTED, token_hash=None, pin_ok=True)
    assert (no_token["outcome"], no_token["purpose"]) == ("verification_required", "new_device")
    wrong_token = auth.pin(device=TRUSTED, token_hash=digest("guess"), pin_ok=True)
    assert wrong_token["outcome"] == "verification_required"
    assert auth.sign_in(account.user_id, device=TRUSTED, pin_ok=True)["outcome"] == "authenticated"


def test_a_device_unused_for_90_days_needs_a_code(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    _with_token(owner_conn, account)
    edge = T0 + timedelta(days=90)
    inside = auth.pin(device=PHONE_DEVICE, token_hash=TOKEN_HASH, now=edge - timedelta(seconds=1))
    assert inside["outcome"] == "authenticated"
    assert auth.pin(device=PHONE_DEVICE, token_hash=TOKEN_HASH, now=edge)["outcome"] == (
        "authenticated"
    )
    unused = edge + timedelta(days=90)
    stale = auth.pin(device=PHONE_DEVICE, token_hash=TOKEN_HASH, now=unused)
    assert stale["outcome"] == "verification_required"
    with pytest.raises(psycopg.Error):
        auth.resolve(account.user_id, 0, device=PHONE_DEVICE, now=unused)


def test_a_pin_reset_removes_every_other_device(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    _with_token(owner_conn, account)
    store_token(owner_conn, account.user_id, PHONE_DEVICE)
    store_code(owner_conn, account.user_id, "pin_reset", "new-phone")
    result = auth.complete_pin(
        "pin_reset", device="new-phone", name="New phone", token_hash=digest("new-token")
    )
    assert (result["outcome"], result["device_token_issued"]) == ("authenticated", True)
    live = owner_conn.execute(
        "SELECT device_id, token_hash, name FROM identity.trusted_devices "
        "WHERE user_id = %s AND NOT revoked",
        (account.user_id,),
    ).fetchall()
    assert [(d["device_id"], d["token_hash"], d["name"]) for d in live] == [
        ("new-phone", digest("new-token"), "New phone")
    ]
    assert live_tokens(owner_conn, account.user_id) == 1
    assert [r["reason"] for r in _sign_in_log(owner_conn, account.user_id)] == [
        "PIN reset with a code; Device trusted"
    ]


def test_an_untrusted_sign_in_gives_a_session_but_not_a_remembered_device(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    store_code(owner_conn, account.user_id, "new_device", "borrowed")
    result = auth.check_code("new_device", device="borrowed", trust=False, token_hash=TOKEN_HASH)
    assert (result["outcome"], result["device_token_issued"]) == ("authenticated", False)
    device = device_row(owner_conn, account.user_id, "borrowed")
    assert device is not None
    assert (device["remembered"], device["token_hash"], device["revoked"]) == (False, None, False)
    assert auth.resolve(account.user_id, 0, device="borrowed")["role"] == "Owner"
    assert auth.pin(device="borrowed", pin_ok=True)["outcome"] == "verification_required"
    assert [d["this_device"] for d in auth.device_list(account.user_id, device="borrowed")] == [
        False
    ]
    assert _sign_in_log(owner_conn, account.user_id) == []


def test_change_pin(auth: Auth, owner_conn: Conn, account: Account) -> None:
    token = store_token(owner_conn, account.user_id, TRUSTED)
    before = user_row(owner_conn, account.user_id)
    changed = auth.change_pin(account.user_id)
    assert changed["outcome"] == "pin_changed"
    after = user_row(owner_conn, account.user_id)
    assert (after["pin_hash"], after["security_version"]) == (
        NEW_PIN_HASH,
        before["security_version"],
    )
    assert [t["token_hash"] for t in tokens(owner_conn, account.user_id) if not t["revoked"]] == [
        token
    ]
    assert [r["reason"] for r in _sign_in_log(owner_conn, account.user_id)] == ["PIN changed"]
    for left in (4, 3, 2, 1):
        wrong = auth.change_pin(account.user_id, current_ok=False, checked_hash=NEW_PIN_HASH)
        assert (wrong["outcome"], wrong["tries_left"]) == ("refused", left)
    assert auth.change_pin(account.user_id, current_ok=False)["outcome"] == "pin_locked"
    assert auth.change_pin(account.user_id, checked_hash=NEW_PIN_HASH)["outcome"] == "pin_locked"
    assert _counters(owner_conn, account.user_id) == (5, 0)


def test_change_pin_with_a_verdict_on_a_replaced_hash_counts_a_wrong_pin(
    auth: Auth, owner_conn: Conn, account: Account
) -> None:
    set_user(owner_conn, account.user_id, pin_hash=NEW_PIN_HASH)
    result = auth.change_pin(account.user_id, current_ok=True, checked_hash=PIN_HASH)
    assert (result["outcome"], result["tries_left"]) == ("refused", 4)
    assert user_row(owner_conn, account.user_id)["pin_hash"] == NEW_PIN_HASH


def test_own_devices_are_listed_and_removed(
    auth: Auth, owner_conn: Conn, operator_conn: Conn, account: Account
) -> None:
    _with_token(owner_conn, account)
    trust(owner_conn, account.user_id, TRUSTED, last_used_at=T0 - timedelta(days=1))
    trust(owner_conn, account.user_id, "session-only", remembered=False)
    store_token(owner_conn, account.user_id, PHONE_DEVICE)
    listed = auth.device_list(account.user_id, device=PHONE_DEVICE)
    assert [(d["name"], d["this_device"]) for d in listed] == [("Jane phone", True), (None, False)]
    other = make_account(
        operator_conn, owner_conn, email="other@example.com", phone="0722000002", role="Owner"
    )
    for user_id, row_id in ((other.user_id, UUID(listed[0]["id"])), (account.user_id, UUID(int=7))):
        with pytest.raises(psycopg.Error) as caught:
            auth.device_remove(user_id, row_id)
        assert (caught.value.sqlstate, caught.value.diag.message_primary) == ("XC404", "not_found")
    removed = auth.device_remove(account.user_id, UUID(listed[0]["id"]))
    assert removed["outcome"] == "device_revoked"
    assert live_tokens(owner_conn, account.user_id, PHONE_DEVICE) == 0
    with pytest.raises(psycopg.Error):
        auth.resolve(account.user_id, 0, device=PHONE_DEVICE)
    assert [r["reason"] for r in _sign_in_log(owner_conn, account.user_id)] == [
        "Trusted device removed"
    ]
    with pytest.raises(psycopg.Error) as again:
        auth.device_remove(account.user_id, UUID(listed[0]["id"]))
    assert again.value.sqlstate == "XC404"


def test_a_person_write_and_a_sign_in_event_do_not_deadlock(
    app_url: str, owner_conn: Conn, operator_conn: Conn, account: Account
) -> None:
    clerk = make_account(
        operator_conn,
        owner_conn,
        email="clerk@example.com",
        phone="0722000003",
        role="Revenue clerk",
    )
    set_user(owner_conn, clerk.user_id, failed_attempts=3)
    version = owner_conn.execute(
        "SELECT version FROM tenancy.memberships WHERE user_id = %s", (clerk.user_id,)
    ).fetchone()
    assert version is not None
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as signing,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as admin,
    ):
        outcome: list[Any] = []

        def block() -> None:
            try:
                outcome.append(
                    call(
                        admin,
                        "people_set_active",
                        account.user_id,
                        account.organization_id,
                        "req-block",
                        clerk.user_id,
                        False,
                        version["version"],
                        "Left the company",
                        T0,
                    )
                )
            except psycopg.Error as error:
                outcome.append(error)

        with signing.transaction():
            # The fourth wrong PIN holds the clerk's user row for the rest of the transaction.
            Auth(signing).sign_in(clerk.user_id, pin_ok=False)
            worker = threading.Thread(target=block)
            worker.start()
            worker.join(1.0)
            # The block took the membership and now waits for the user row.
            assert worker.is_alive()
            # The fifth writes "PIN locked" to the change log: its actor key check needs the
            # membership the block holds, which FOR NO KEY UPDATE leaves open.
            fifth = Auth(signing).sign_in(clerk.user_id, pin_ok=False)
            assert fifth["outcome"] == "paused"
        worker.join(10)
    assert not isinstance(outcome[0], psycopg.Error), outcome[0]
    assert user_row(owner_conn, clerk.user_id)["status"] == "removed"


def test_a_code_voided_while_a_new_one_is_asked_for_leaves_one_live_code(
    app_url: str, owner_conn: Conn, account: Account
) -> None:
    store_code(owner_conn, account.user_id, "pin_reset", UNTRUSTED, failed_attempts=2)
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as voiding,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as asking,
    ):
        answers: list[dict[str, Any]] = []

        def ask() -> None:
            answers.append(
                Auth(asking).request_code(
                    "pin_reset", code_hash=digest("code:999999"), now=T0 + timedelta(minutes=2)
                )
            )

        with voiding.transaction():
            resent = Auth(voiding).check_code(
                "pin_reset", code_hash=WRONG_CODE_HASH, now=T0 + timedelta(minutes=2)
            )
            assert (resent["outcome"], resent["code_issued"]) == ("code_resent", True)
            worker = threading.Thread(target=ask)
            worker.start()
            worker.join(0.5)
            # The request waits for the account row the voiding try holds.
            assert worker.is_alive()
        worker.join(10)
    # The request saw the replacement: inside its minute it issues nothing and supersedes
    # nothing, so exactly the replacement is live; a minute later it would supersede it.
    assert (answers[0]["outcome"], answers[0]["code_issued"]) == ("silent", None)
    live = [c for c in codes(owner_conn, account.user_id) if not c["consumed"]]
    assert [c["code_hash"] for c in live] == [NEW_CODE_HASH]
