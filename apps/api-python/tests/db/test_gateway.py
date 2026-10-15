"""The routine-call gateway (``db/session.py``): one transaction per call, retry policy,
SQLSTATE translation, statement counter (``docs/09-testing.md`` section 3)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import psycopg
import pytest
import structlog
from psycopg_pool import AsyncConnectionPool

from xcode_api.application.errors import IntegrityBug, TransientFailure
from xcode_api.db.pool import open_operator_pool
from xcode_api.db.routines.identity import IdentityRoutines
from xcode_api.db.routines.ops import OpsRoutines
from xcode_api.db.session import call
from xcode_api.db.types import write_result
from xcode_api.domain.errors import (
    CapExceeded,
    Conflict,
    Forbidden,
    NotFound,
    RuleViolation,
    SessionInvalid,
)
from xcode_api.domain.identity import (
    AccountLookup,
    AuthOutcomeKind,
    CodeCheck,
    CodePurpose,
    CodeRequest,
    CodeWithdrawal,
    DeviceRevocation,
    DeviceVerification,
    OperatorRequest,
    PinCompletion,
    PinProblem,
    PinVerdict,
    SessionCheck,
    SessionContext,
    SignInRefusal,
    TokenRefresh,
    TokenSignOut,
    UserProvisioning,
    UserStatus,
)
from xcode_api.domain.values import WriteOutcome, WriteResult

from ..support.fakes import held_permissions, role_rights
from ..support.scenario import (
    CODE_HASH,
    EMAIL,
    NEW_CODE_HASH,
    NEW_PIN_HASH,
    PHONE,
    PIN_HASH,
    TRUSTED,
    UNTRUSTED,
    Conn,
    make_account,
    new_token_hash,
    set_user,
    store_code,
)
from ..support.scenario import T0 as AUTH_T0

T0 = datetime(2026, 10, 7, 9, 0, 0, tzinfo=UTC)


async def test_unreachable_database_is_a_transient_failure() -> None:
    # No server listens on port 1: the pool cannot hand out a connection within its
    # timeout, which must surface as TransientFailure (503), never as a 500 bug.
    pool: AsyncConnectionPool[object] = AsyncConnectionPool(
        "postgresql://xcode_app:xcode_app@127.0.0.1:1/xcode",
        min_size=1,
        max_size=1,
        timeout=0.5,
        kwargs={"connect_timeout": 1},
        open=False,
    )
    await pool.open(wait=False)
    try:
        with pytest.raises(TransientFailure):
            await call(pool, "meta_contract_version")
    finally:
        await pool.close()


@pytest.fixture
def gateway_routines(owner_conn: psycopg.Connection[dict[str, object]]) -> Iterator[None]:
    # A sequence (not a table row): nextval is non-transactional, so the counter survives
    # the rollback of a failed attempt and the gateway's retry can observe progress.
    owner_conn.execute("CREATE SEQUENCE ops.test_seq")
    owner_conn.execute("CREATE TABLE ops.test_side_effect (id int)")
    owner_conn.execute(
        """
        CREATE FUNCTION api.test_raise(p_sqlstate text, p_message text, p_detail text)
        RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp AS $$
        BEGIN
          RAISE EXCEPTION USING ERRCODE = p_sqlstate, MESSAGE = p_message, DETAIL = p_detail;
        END;
        $$
        """
    )
    owner_conn.execute(
        """
        CREATE FUNCTION api.test_insert_then_fail()
        RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp AS $$
        BEGIN
          INSERT INTO ops.test_side_effect (id) VALUES (1);
          RAISE EXCEPTION USING ERRCODE = 'XC422', MESSAGE = 'boom';
        END;
        $$
        """
    )
    owner_conn.execute(
        """
        CREATE FUNCTION api.test_fail_then_succeed(p_name text, p_fails int, p_sqlstate text)
        RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp AS $$
        DECLARE v int;
        BEGIN
          v := nextval('ops.test_seq');
          IF v <= p_fails THEN
            RAISE EXCEPTION USING ERRCODE = p_sqlstate, MESSAGE = 'transient';
          END IF;
          RETURN v;
        END;
        $$
        """
    )
    for name, args in [
        ("test_raise", "text, text, text"),
        ("test_insert_then_fail", ""),
        ("test_fail_then_succeed", "text, int, text"),
    ]:
        owner_conn.execute(f"ALTER FUNCTION api.{name}({args}) OWNER TO xcode_api_executor")
        owner_conn.execute(f"GRANT EXECUTE ON FUNCTION api.{name}({args}) TO xcode_app")
    try:
        yield
    finally:
        owner_conn.execute("DROP FUNCTION api.test_raise(text, text, text)")
        owner_conn.execute("DROP FUNCTION api.test_insert_then_fail()")
        owner_conn.execute("DROP FUNCTION api.test_fail_then_succeed(text, int, text)")
        owner_conn.execute("DROP TABLE ops.test_side_effect")
        owner_conn.execute("DROP SEQUENCE ops.test_seq")


@pytest.mark.usefixtures("gateway_routines")
async def test_one_transaction_per_call_rolls_back_on_raise(
    pool: AsyncConnectionPool[object],
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    with pytest.raises(RuleViolation):
        await call(pool, "test_insert_then_fail")
    rows = owner_conn.execute("SELECT count(*) AS n FROM ops.test_side_effect").fetchall()
    assert rows[0]["n"] == 0


@pytest.mark.usefixtures("gateway_routines")
@pytest.mark.parametrize(
    ("sqlstate", "message", "detail", "exc_type", "expect_code"),
    [
        ("XC401", "session_invalid", "{}", SessionInvalid, "session_invalid"),
        ("XC403", "forbidden", "{}", Forbidden, "forbidden"),
        ("XC404", "not_found", "{}", NotFound, "not_found"),
        ("XC409", "version_conflict", '{"expected_version":3}', Conflict, "version_conflict"),
        ("XC422", "money_invalid", '{"field":"amount"}', RuleViolation, "money_invalid"),
        ("XC429", "cap_exceeded", "{}", CapExceeded, "cap_exceeded"),
        ("23505", "unique_violation", "{}", Conflict, "unique_conflict"),
    ],
)
async def test_sqlstate_translation(
    pool: AsyncConnectionPool[object],
    sqlstate: str,
    message: str,
    detail: str,
    exc_type: type[Exception],
    expect_code: str,
) -> None:
    with pytest.raises(exc_type) as exc:
        await call(pool, "test_raise", sqlstate, message, detail)
    if sqlstate.startswith("XC") or sqlstate == "23505":
        assert getattr(exc.value, "code", None) == expect_code


@pytest.mark.usefixtures("gateway_routines")
async def test_integrity_sqlstate_becomes_integrity_bug(
    pool: AsyncConnectionPool[object],
) -> None:
    with pytest.raises(IntegrityBug):
        await call(pool, "test_raise", "23502", "not_null", "{}")


@pytest.mark.usefixtures("gateway_routines")
async def test_idempotent_call_retries_a_transient_sqlstate(
    pool: AsyncConnectionPool[object],
) -> None:
    result = await call(pool, "test_fail_then_succeed", "a", 2, "40001", idempotent=True)
    assert result[0][next(iter(result[0].keys()))] == 3  # type: ignore[index]


@pytest.mark.usefixtures("gateway_routines")
async def test_non_idempotent_call_does_not_retry(
    pool: AsyncConnectionPool[object],
) -> None:
    with pytest.raises(TransientFailure):
        await call(pool, "test_fail_then_succeed", "b", 2, "40001", idempotent=False)


@pytest.mark.usefixtures("gateway_routines")
async def test_idempotent_call_does_not_retry_a_non_transient_sqlstate(
    pool: AsyncConnectionPool[object],
) -> None:
    with pytest.raises(RuleViolation):
        await call(pool, "test_fail_then_succeed", "c", 2, "XC422", idempotent=True)


@pytest.mark.usefixtures("gateway_routines")
async def test_statement_counter_increments_per_call(
    pool: AsyncConnectionPool[object],
    statement_counter: Callable[[], int],
) -> None:
    before = statement_counter()
    await call(pool, "meta_contract_version", idempotent=True)
    await call(pool, "meta_contract_version", idempotent=True)
    assert statement_counter() == before + 2


@pytest.mark.usefixtures("gateway_routines")
async def test_debug_log_carries_no_arguments(
    pool: AsyncConnectionPool[object],
) -> None:
    events: list[dict[str, object]] = []

    def capture(_logger: object, _method: str, event: dict[str, object]) -> dict[str, object]:
        events.append(dict(event))
        return event

    old_config = structlog.get_config()
    structlog.configure(
        processors=[structlog.stdlib.add_log_level, capture, structlog.processors.JSONRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(10),  # DEBUG
    )
    try:
        await call(pool, "meta_contract_version", idempotent=True)
    finally:
        structlog.configure(**old_config)
    routine_logs = [e for e in events if e.get("event") == "db.routine"]
    assert routine_logs, "no db.routine log line captured"
    for entry in routine_logs:
        assert set(entry.keys()) <= {"event", "routine", "duration_ms", "level", "timestamp"}


# --- IdentityRoutines and OpsRoutines -----------------------------------------------------


@pytest.fixture
async def operator_pool(app_url: str) -> AsyncIterator[AsyncConnectionPool[object]]:
    parts = urlsplit(app_url)
    url = urlunsplit(
        (
            parts.scheme,
            f"xcode_operator:xcode_operator@{parts.hostname}:{parts.port}",
            parts.path,
            parts.query,
            parts.fragment,
        )
    )
    pool = open_operator_pool(url)
    await pool.open(wait=True, timeout=15)
    try:
        yield pool
    finally:
        await pool.close()


def _one_statement(counter: Callable[[], int], before: int) -> int:
    assert counter() == before + 1
    return counter()


async def test_identity_routines_map_every_outcome_with_one_statement_each(
    pool: AsyncConnectionPool[object],
    operator_conn: Conn,
    owner_conn: Conn,
    statement_counter: Callable[[], int],
) -> None:
    account = make_account(operator_conn, owner_conn)
    identity = IdentityRoutines(pool)
    count = statement_counter()

    state = await identity.account_lookup(AccountLookup("req", PHONE, TRUSTED, AUTH_T0))
    count = _one_statement(statement_counter, count)
    assert state is not None
    assert (state.user_id, state.status, state.pin_hash, state.device_trusted) == (
        account.user_id,
        UserStatus.ACTIVE,
        PIN_HASH,
        True,
    )
    assert state.policy is not None
    assert (state.policy.organization_id, state.policy.role_name) == (
        account.organization_id,
        "Owner",
    )
    assert len(state.policy.permissions) == len(held_permissions(role_rights("Owner"), "Owner"))

    assert (
        await identity.account_lookup(AccountLookup("req", "0799999999", TRUSTED, AUTH_T0)) is None
    )
    count = _one_statement(statement_counter, count)

    refresh_hash = new_token_hash()
    signed_in = await identity.sign_in(
        PinVerdict(
            "req", account.user_id, TRUSTED, True, PIN_HASH, CODE_HASH, refresh_hash, False, AUTH_T0
        )
    )
    count = _one_statement(statement_counter, count)
    assert signed_in.outcome is AuthOutcomeKind.AUTHENTICATED
    assert (signed_in.user_id, signed_in.organization_id, signed_in.role) == (
        account.user_id,
        account.organization_id,
        "Owner",
    )
    assert signed_in.permissions is not None
    assert len(signed_in.permissions) == len(held_permissions(role_rights("Owner"), "Owner"))
    assert signed_in.refresh_expires_at == AUTH_T0 + timedelta(days=30)
    assert (signed_in.security_version, signed_in.access_token_minutes) == (0, 10)

    wrong = await identity.sign_in(
        PinVerdict(
            "req", account.user_id, TRUSTED, False, PIN_HASH, None, new_token_hash(), False, AUTH_T0
        )
    )
    count = _one_statement(statement_counter, count)
    assert (wrong.outcome, wrong.refusal) == (AuthOutcomeKind.REFUSED, SignInRefusal.WRONG_PIN)

    issued = await identity.request_code(
        CodeRequest("req", PHONE, UNTRUSTED, CodePurpose.PIN_RESET, CODE_HASH, False, AUTH_T0)
    )
    count = _one_statement(statement_counter, count)
    assert (issued.outcome, issued.email, issued.code_issued) == (
        AuthOutcomeKind.CHECK_EMAIL,
        account.email,
        True,
    )
    assert isinstance(issued.code_id, UUID)
    assert "jane" not in repr(issued)

    verified = await identity.verify_code(
        CodeCheck(
            request_id="req",
            phone=PHONE,
            device_id=UNTRUSTED,
            purpose=CodePurpose.PIN_RESET,
            code_hash=CODE_HASH,
            replacement_code_hash=NEW_CODE_HASH,
            now=AUTH_T0,
        )
    )
    count = _one_statement(statement_counter, count)
    assert verified.outcome is AuthOutcomeKind.CODE_VERIFIED

    unchanged = await identity.complete_pin(
        PinCompletion(
            request_id="req",
            phone=PHONE,
            device_id=UNTRUSTED,
            purpose=CodePurpose.PIN_RESET,
            code_hash=CODE_HASH,
            new_pin_is_current=True,
            checked_pin_hash=PIN_HASH,
            pin_hash=PIN_HASH,
            device_name=None,
            trust=True,
            device_token_hash=None,
            refresh_token_hash=new_token_hash(),
            trust_days=None,
            now=AUTH_T0,
        )
    )
    count = _one_statement(statement_counter, count)
    assert (unchanged.outcome, unchanged.pin_problem, unchanged.minimum_pin_length) == (
        AuthOutcomeKind.INVALID_PIN,
        PinProblem.UNCHANGED,
        4,
    )

    completed_hash = new_token_hash()
    completed = await identity.complete_pin(
        PinCompletion(
            request_id="req",
            phone=PHONE,
            device_id=UNTRUSTED,
            purpose=CodePurpose.PIN_RESET,
            code_hash=CODE_HASH,
            new_pin_is_current=False,
            checked_pin_hash=PIN_HASH,
            pin_hash=NEW_PIN_HASH,
            device_name=None,
            trust=True,
            device_token_hash=None,
            refresh_token_hash=completed_hash,
            trust_days=30,
            now=AUTH_T0,
        )
    )
    count = _one_statement(statement_counter, count)
    assert (completed.outcome, completed.security_version) == (AuthOutcomeKind.AUTHENTICATED, 1)

    rotated = await identity.refresh(
        TokenRefresh("req", completed_hash, UNTRUSTED, new_token_hash(), AUTH_T0)
    )
    count = _one_statement(statement_counter, count)
    assert rotated.outcome is AuthOutcomeKind.AUTHENTICATED

    signed_out = await identity.sign_out(TokenSignOut("req", completed_hash, UNTRUSTED, AUTH_T0))
    count = _one_statement(statement_counter, count)
    assert signed_out.outcome is AuthOutcomeKind.SIGNED_OUT

    context = await identity.resolve_session(SessionCheck(account.user_id, UNTRUSTED, 1, AUTH_T0))
    count = _one_statement(statement_counter, count)
    assert context == SessionContext(account.organization_id, "Owner")

    revoked = await identity.revoke_device(
        DeviceRevocation("req", account.user_id, UNTRUSTED, AUTH_T0)
    )
    count = _one_statement(statement_counter, count)
    assert revoked.outcome is AuthOutcomeKind.DEVICE_REVOKED

    with pytest.raises(SessionInvalid):
        await identity.resolve_session(SessionCheck(account.user_id, UNTRUSTED, 1, AUTH_T0))
    assert statement_counter() == count

    again = await identity.request_code(
        CodeRequest("req", PHONE, UNTRUSTED, CodePurpose.PIN_RESET, CODE_HASH, True, AUTH_T0)
    )
    assert again.code_id is not None
    count = statement_counter()
    await identity.withdraw_code(CodeWithdrawal("req", again.code_id, AUTH_T0))
    _one_statement(statement_counter, count)
    row = owner_conn.execute(
        "SELECT consumed, expires_at = created_at AS withdrawn FROM identity.verification_codes "
        "WHERE id = %s",
        (again.code_id,),
    ).fetchone()
    assert row == {"consumed": True, "withdrawn": True}


async def test_verify_device_maps_through_the_gateway(
    pool: AsyncConnectionPool[object], operator_conn: Conn, owner_conn: Conn
) -> None:
    account = make_account(operator_conn, owner_conn)
    store_code(owner_conn, account.user_id, "new_device", UNTRUSTED)
    outcome = await IdentityRoutines(pool).verify_device(
        DeviceVerification(
            request_id="req",
            phone=PHONE,
            device_id=UNTRUSTED,
            code_hash=CODE_HASH,
            replacement_code_hash=NEW_CODE_HASH,
            refresh_token_hash=new_token_hash(),
            trust_days=7,
            now=AUTH_T0,
        )
    )
    assert outcome.outcome is AuthOutcomeKind.AUTHENTICATED


async def test_ops_routines_map_the_operator_routines(
    operator_pool: AsyncConnectionPool[object],
    pool: AsyncConnectionPool[object],
    owner_conn: Conn,
    statement_counter: Callable[[], int],
) -> None:
    ops = OpsRoutines(operator_pool)
    count = statement_counter()
    provisioned = await ops.provision_user(
        UserProvisioning("alice", "req", EMAIL, PHONE, None, None, None, None, AUTH_T0)
    )
    count = _one_statement(statement_counter, count)
    assert (provisioned.created_user, provisioned.created_organization) == (True, True)
    request = OperatorRequest("alice", "req", EMAIL, AUTH_T0)

    summary = await ops.account_state(request)
    count = _one_statement(statement_counter, count)
    assert (summary.user_id, summary.status, summary.has_pin) == (
        provisioned.user_id,
        UserStatus.ACTIVE,
        False,
    )
    cleared = await ops.clear_pause(request)
    count = _one_statement(statement_counter, count)
    assert cleared.was_locked is False
    set_user(owner_conn, provisioned.user_id, failed_attempts=5)
    count = statement_counter()
    locked = await ops.clear_pause(request)
    count = _one_statement(statement_counter, count)
    assert (locked.user_id, locked.was_locked) == (provisioned.user_id, True)
    unlocked = await ops.clear_pause(request)
    count = _one_statement(statement_counter, count)
    assert unlocked.was_locked is False
    revoked = await ops.revoke_sessions(request)
    count = _one_statement(statement_counter, count)
    assert (revoked.devices, revoked.tokens) == (0, 0)
    removed = await ops.remove_user(request)
    count = _one_statement(statement_counter, count)
    assert removed.removed is True

    assert await OpsRoutines(pool).unassigned_user_count() == 0
    count = _one_statement(statement_counter, count)

    with pytest.raises(NotFound):
        await ops.clear_pause(OperatorRequest("alice", "req", "nobody@example.com", AUTH_T0))
    with pytest.raises(RuleViolation) as bad:
        await ops.provision_user(
            UserProvisioning("alice", "req", "nope", PHONE, None, None, None, None, AUTH_T0)
        )
    assert bad.value.code == "people_email_invalid"
    with pytest.raises(Conflict) as taken:
        await ops.provision_user(
            UserProvisioning(
                "alice", "req", "other@example.com", PHONE, None, None, None, None, AUTH_T0
            )
        )
    assert taken.value.code == "people_contact_taken"


def test_write_result_adapter(owner_conn: Conn) -> None:
    row = owner_conn.execute(
        "SELECT (ROW('6c1f2a8e-0000-4000-8000-000000000001'::uuid, 3, 'updated')"
        "::api.write_result).*"
    ).fetchone()
    assert row is not None
    assert write_result(row) == WriteResult(
        UUID("6c1f2a8e-0000-4000-8000-000000000001"), 3, WriteOutcome.UPDATED
    )
    with pytest.raises(IntegrityBug):
        write_result({"id": row["id"], "version": 3})
