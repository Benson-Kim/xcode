"""``IdentityRoutines``: the real ``IdentityRepository``, one typed method per ``api.auth_*``
routine. Only the reads (the account lookups, the device list and session resolution) are
marked idempotent, so only they are retried on a transient SQLSTATE."""

from __future__ import annotations

from typing import Any

from psycopg_pool import AsyncConnectionPool

from ...application.errors import IntegrityBug
from ...application.observability import report_auth_outcome
from ...domain.identity import (
    AccountLookup,
    AccountState,
    AuthOutcome,
    CodeCheck,
    CodeEntry,
    CodeRequest,
    CodeResend,
    CodeWithdrawal,
    DeviceListing,
    DeviceRemoval,
    DeviceRevocation,
    DeviceVerification,
    NumberCheck,
    PinChange,
    PinCheck,
    PinCompletion,
    PinVerdict,
    SessionCheck,
    SessionContext,
    TokenRefresh,
    TokenSignOut,
    TrustedDeviceView,
    UserLookup,
)
from ..session import call
from ..types import account_state, auth_outcome, session_context, trusted_device_view


class IdentityRoutines:
    """Authentication routines (``api.auth_*``)."""

    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    async def account_lookup(self, query: AccountLookup) -> AccountState | None:
        rows = await call(
            self._pool,
            "auth_account_lookup",
            query.request_id,
            query.phone,
            query.device_id,
            query.device_token_hash,
            query.pin_try,
            query.now,
            idempotent=True,
        )
        return account_state(rows[0]) if rows else None

    async def account_lookup_user(self, query: UserLookup) -> AccountState | None:
        rows = await call(
            self._pool,
            "auth_account_lookup_user",
            query.request_id,
            query.user_id,
            query.device_id,
            query.now,
            idempotent=True,
        )
        return account_state(rows[0]) if rows else None

    async def start(self, command: NumberCheck) -> AuthOutcome:
        return await self._outcome(
            "auth_start",
            command.request_id,
            command.phone,
            command.device_id,
            command.device_token_hash,
            command.code_hash,
            command.skip_cooldown,
            command.now,
        )

    async def sign_in(self, verdict: PinVerdict) -> AuthOutcome:
        return await self._outcome(
            "auth_sign_in",
            verdict.request_id,
            verdict.user_id,
            verdict.device_id,
            verdict.pin_ok,
            verdict.checked_pin_hash,
            verdict.code_hash,
            verdict.refresh_token_hash,
            verdict.skip_cooldown,
            verdict.now,
        )

    async def pin(self, command: PinCheck) -> AuthOutcome:
        return await self._outcome(
            "auth_pin",
            command.request_id,
            command.phone,
            command.device_id,
            command.device_token_hash,
            command.pin_ok,
            command.checked_pin_hash,
            command.code_hash,
            command.refresh_token_hash,
            command.skip_cooldown,
            command.now,
        )

    async def check_code(self, command: CodeEntry) -> AuthOutcome:
        return await self._outcome(
            "auth_check_code",
            command.request_id,
            command.phone,
            command.device_id,
            command.purpose.value,
            command.code_hash,
            command.replacement_code_hash,
            command.device_name,
            command.trust,
            command.device_token_hash,
            command.refresh_token_hash,
            command.trust_days,
            command.now,
        )

    async def resend_code(self, command: CodeResend) -> AuthOutcome:
        return await self._outcome(
            "auth_resend_code",
            command.request_id,
            command.phone,
            command.device_id,
            command.purpose.value,
            command.code_hash,
            command.skip_cooldown,
            command.now,
        )

    async def verify_device(self, command: DeviceVerification) -> AuthOutcome:
        return await self._outcome(
            "auth_verify_device",
            command.request_id,
            command.phone,
            command.device_id,
            command.code_hash,
            command.replacement_code_hash,
            command.refresh_token_hash,
            command.trust_days,
            command.now,
        )

    async def request_code(self, command: CodeRequest) -> AuthOutcome:
        return await self._outcome(
            "auth_request_code",
            command.request_id,
            command.phone,
            command.device_id,
            command.purpose.value,
            command.code_hash,
            command.skip_cooldown,
            command.now,
        )

    async def verify_code(self, command: CodeCheck) -> AuthOutcome:
        return await self._outcome(
            "auth_verify_code",
            command.request_id,
            command.phone,
            command.device_id,
            command.purpose.value,
            command.code_hash,
            command.replacement_code_hash,
            command.now,
        )

    async def complete_pin(self, command: PinCompletion) -> AuthOutcome:
        return await self._outcome(
            "auth_complete_pin",
            command.request_id,
            command.phone,
            command.device_id,
            command.purpose.value,
            command.code_hash,
            command.new_pin_is_current,
            command.checked_pin_hash,
            command.pin_hash,
            command.device_name,
            command.trust,
            command.device_token_hash,
            command.refresh_token_hash,
            command.trust_days,
            command.now,
        )

    async def change_pin(self, command: PinChange) -> AuthOutcome:
        return await self._outcome(
            "auth_change_pin",
            command.request_id,
            command.user_id,
            command.device_id,
            command.current_ok,
            command.checked_pin_hash,
            command.pin_hash,
            command.now,
        )

    async def refresh(self, command: TokenRefresh) -> AuthOutcome:
        return await self._outcome(
            "auth_refresh",
            command.request_id,
            command.token_hash,
            command.device_id,
            command.new_token_hash,
            command.now,
        )

    async def sign_out(self, command: TokenSignOut) -> AuthOutcome:
        return await self._outcome(
            "auth_sign_out",
            command.request_id,
            command.token_hash,
            command.device_id,
            command.now,
        )

    async def revoke_device(self, command: DeviceRevocation) -> AuthOutcome:
        return await self._outcome(
            "auth_revoke_device",
            command.request_id,
            command.user_id,
            command.device_id,
            command.now,
        )

    async def device_list(self, query: DeviceListing) -> tuple[TrustedDeviceView, ...]:
        rows = await call(
            self._pool,
            "auth_device_list",
            query.user_id,
            query.device_id,
            query.now,
            idempotent=True,
        )
        if len(rows) != 1 or not isinstance(rows[0].get("auth_device_list"), list):
            raise IntegrityBug("api.auth_device_list returned no list")
        return tuple(trusted_device_view(item) for item in rows[0]["auth_device_list"])

    async def device_remove(self, command: DeviceRemoval) -> AuthOutcome:
        return await self._outcome(
            "auth_device_remove",
            command.request_id,
            command.user_id,
            command.row_id,
            command.now,
        )

    async def withdraw_code(self, command: CodeWithdrawal) -> None:
        await call(
            self._pool, "auth_withdraw_code", command.request_id, command.code_id, command.now
        )

    async def resolve_session(self, check: SessionCheck) -> SessionContext:
        rows = await call(
            self._pool,
            "auth_resolve_session",
            check.user_id,
            check.device_id,
            check.security_version,
            check.now,
            idempotent=True,
        )
        return session_context(_document(rows, "auth_resolve_session"))

    async def _outcome(self, routine: str, *args: Any) -> AuthOutcome:
        rows = await call(self._pool, routine, *args)
        outcome = auth_outcome(_document(rows, routine))
        report_auth_outcome(outcome)
        return outcome


def _document(rows: list[dict[str, Any]], routine: str) -> dict[str, Any]:
    if len(rows) != 1:
        raise IntegrityBug(f"api.{routine} returned {len(rows)} rows, expected one")
    value = rows[0].get(routine)
    if not isinstance(value, dict):
        raise IntegrityBug(f"api.{routine} returned no document")
    return value
