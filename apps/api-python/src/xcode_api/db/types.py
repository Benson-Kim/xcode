"""Row adapters: a ``RETURNS TABLE`` row, composite value or ``jsonb`` document into a frozen
dataclass.

Mapping is by field name. A column the dataclass does not declare, or a field the row does
not carry, is drift between a routine and its record: it raises :class:`IntegrityBug`,
never a silent ``None`` (``docs/01-architecture.md`` section 3).
The named adapters below also convert the JSON scalars of ``jsonb`` documents (uuid and
timestamp text, arrays) into the record's types.
"""

from __future__ import annotations

import dataclasses
import functools
import types
import typing
from collections.abc import Callable, Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from ..application.errors import IntegrityBug
from ..domain.identity import (
    AccountPolicy,
    AccountState,
    AccountSummary,
    AuthOutcome,
    AuthOutcomeKind,
    ClearedPause,
    CodePurpose,
    PinProblem,
    ProvisionedUser,
    RemovedUser,
    RevokedSessions,
    SessionContext,
    SignInRefusal,
    SignInStatus,
    TrustedDeviceView,
    UserStatus,
)
from ..domain.values import WriteOutcome, WriteResult


def adapt_row[T](row: Mapping[str, Any], record: type[T]) -> T:
    """Build ``record`` from ``row`` (a dict-factory row), matching by field name."""
    fields = dataclasses.fields(record)  # type: ignore[arg-type]
    expected = {f.name for f in fields}
    present = set(row.keys())

    missing = expected - present
    if missing:
        raise IntegrityBug(
            f"{record.__name__} is missing column(s) {sorted(missing)} from the routine result"
        )
    unknown = present - expected
    if unknown:
        raise IntegrityBug(
            f"{record.__name__} received unexpected column(s) {sorted(unknown)} from the routine"
        )
    return record(**{f.name: row[f.name] for f in fields})


def write_result(row: Mapping[str, Any]) -> WriteResult:
    """``api.write_result`` to :class:`WriteResult`."""
    _require(row, ("id", "version", "outcome"), "api.write_result")
    return WriteResult(
        id=row["id"], version=int(row["version"]), outcome=WriteOutcome(row["outcome"])
    )


def account_state(row: Mapping[str, Any]) -> AccountState:
    """``api.account_state`` (its ``policy`` travels as ``jsonb``) to :class:`AccountState`."""
    _require(row, [f.name for f in dataclasses.fields(AccountState)], "api.account_state")
    return AccountState(
        user_id=row["user_id"],
        status=UserStatus(row["status"]),
        pin_hash=row["pin_hash"],
        phone_number=row["phone_number"],
        security_version=int(row["security_version"]),
        failed_attempts=int(row["failed_attempts"]),
        untrusted_failed_attempts=int(row["untrusted_failed_attempts"]),
        pin_reset_required=bool(row["pin_reset_required"]),
        device_trusted=bool(row["device_trusted"]),
        policy=None if row["policy"] is None else account_policy(row["policy"]),
    )


def account_policy(document: Mapping[str, Any]) -> AccountPolicy:
    """``identity.policy`` as ``to_jsonb`` renders it, to :class:`AccountPolicy`."""
    _require(document, [f.name for f in dataclasses.fields(AccountPolicy)], "identity.policy")
    return AccountPolicy(
        organization_id=UUID(document["organization_id"]),
        pin_length=int(document["pin_length"]),
        lockout_threshold=int(document["lockout_threshold"]),
        lockout_minutes=int(document["lockout_minutes"]),
        access_token_minutes=int(document["access_token_minutes"]),
        refresh_token_days=int(document["refresh_token_days"]),
        role_name=str(document["role_name"]),
        first_name=str(document["first_name"]),
        last_name=str(document["last_name"]),
        permissions=tuple(document["permissions"] or ()),
    )


def auth_outcome(document: Mapping[str, Any]) -> AuthOutcome:
    """The ``jsonb`` outcome of an ``api.auth_*`` routine to :class:`AuthOutcome`."""
    _require(document, [f.name for f in dataclasses.fields(AuthOutcome)], "api.auth_* outcome")
    permissions = document["permissions"]
    return AuthOutcome(
        outcome=AuthOutcomeKind(document["outcome"]),
        refusal=_optional(document["refusal"], SignInRefusal),
        retry_after_seconds=_optional(document["retry_after_seconds"], int),
        masked_email=document["masked_email"],
        code_issued=document["code_issued"],
        code_id=_optional(document["code_id"], UUID),
        email=document["email"],
        minimum_pin_length=_optional(document["minimum_pin_length"], int),
        user_id=_optional(document["user_id"], UUID),
        organization_id=_optional(document["organization_id"], UUID),
        role=document["role"],
        first_name=document["first_name"],
        last_name=document["last_name"],
        permissions=None if permissions is None else tuple(permissions),
        security_version=_optional(document["security_version"], int),
        access_token_minutes=_optional(document["access_token_minutes"], int),
        refresh_expires_at=_optional(document["refresh_expires_at"], datetime.fromisoformat),
        purpose=_optional(document["purpose"], CodePurpose),
        tries_left=_optional(document["tries_left"], int),
        pin_problem=_optional(document["pin_problem"], PinProblem),
        device_token_issued=document["device_token_issued"],
    )


def trusted_device_view(document: Mapping[str, Any]) -> TrustedDeviceView:
    """One element of ``api.auth_device_list`` to :class:`TrustedDeviceView`."""
    _require(
        document,
        ("id", "name", "trusted_at", "last_used_at", "this_device"),
        "api.auth_device_list",
    )
    return TrustedDeviceView(
        id=UUID(document["id"]),
        name=document["name"],
        trusted_at=datetime.fromisoformat(document["trusted_at"]),
        last_used_at=datetime.fromisoformat(document["last_used_at"]),
        this_device=bool(document["this_device"]),
    )


def session_context(document: Mapping[str, Any]) -> SessionContext:
    """The ``jsonb`` of ``api.auth_resolve_session`` to :class:`SessionContext`."""
    _require(document, ("organization_id", "role"), "api.auth_resolve_session")
    return SessionContext(
        organization_id=_optional(document["organization_id"], UUID),
        role=document["role"],
    )


def provisioned_user(document: Mapping[str, Any]) -> ProvisionedUser:
    fields = ("user_id", "organization_id", "created_user", "created_organization", "reactivated")
    _require(document, fields, "api.ops_provision_user")
    return ProvisionedUser(
        user_id=UUID(document["user_id"]),
        organization_id=UUID(document["organization_id"]),
        created_user=bool(document["created_user"]),
        created_organization=bool(document["created_organization"]),
        reactivated=bool(document["reactivated"]),
    )


def removed_user(document: Mapping[str, Any]) -> RemovedUser:
    _require(document, ("user_id", "removed", "tokens"), "api.ops_remove_user")
    return RemovedUser(
        user_id=UUID(document["user_id"]),
        removed=bool(document["removed"]),
        tokens=int(document["tokens"]),
    )


def cleared_pause(document: Mapping[str, Any]) -> ClearedPause:
    _require(document, ("user_id", "was_locked"), "api.ops_clear_pause")
    return ClearedPause(user_id=UUID(document["user_id"]), was_locked=bool(document["was_locked"]))


def revoked_sessions(document: Mapping[str, Any]) -> RevokedSessions:
    _require(document, ("user_id", "devices", "tokens"), "api.ops_revoke_sessions")
    return RevokedSessions(
        user_id=UUID(document["user_id"]),
        devices=int(document["devices"]),
        tokens=int(document["tokens"]),
    )


def account_summary(document: Mapping[str, Any]) -> AccountSummary:
    _require(
        document, [f.name for f in dataclasses.fields(AccountSummary)], "api.ops_account_state"
    )
    return AccountSummary(
        user_id=UUID(document["user_id"]),
        status=UserStatus(document["status"]),
        has_pin=bool(document["has_pin"]),
        pin_reset_required=bool(document["pin_reset_required"]),
        sign_in_status=SignInStatus(document["sign_in_status"]),
        last_signed_in_at=_optional(document["last_signed_in_at"], datetime.fromisoformat),
        failed_attempts=int(document["failed_attempts"]),
        untrusted_failed_attempts=int(document["untrusted_failed_attempts"]),
        trusted_devices=int(document["trusted_devices"]),
        live_refresh_tokens=int(document["live_refresh_tokens"]),
        active_membership=bool(document["active_membership"]),
    )


def _optional[T](value: Any, convert: Callable[[Any], T]) -> T | None:
    return None if value is None else convert(value)


def _require(row: Mapping[str, Any], fields: Any, source: str) -> None:
    expected = set(fields)
    present = set(row.keys())
    if expected != present:
        raise IntegrityBug(
            f"{source} drifted: missing {sorted(expected - present)}, "
            f"unexpected {sorted(present - expected)}"
        )


def document[T](value: Any, record: type[T], source: str) -> T:
    """Build ``record`` from a routine's ``jsonb`` document, recursively: nested records,
    tuples, optional values, UUID, date and instant text, numbers, enums. A key the record
    does not declare, a field the document lacks, or a ``null`` where the record allows none is
    drift between the routine and its record: :class:`IntegrityBug`."""
    if not isinstance(value, Mapping):
        raise IntegrityBug(f"{source} returned {type(value).__name__}, not a document")
    fields = dataclasses.fields(record)  # type: ignore[arg-type]
    _require(value, [f.name for f in fields], source)
    hints = _hints(typing.cast(Any, record))
    built = {f.name: _convert(value[f.name], hints[f.name], f"{source}.{f.name}") for f in fields}
    return record(**built)


@functools.cache
def _hints(record: Any) -> dict[str, Any]:
    return typing.get_type_hints(record)


def _convert(value: Any, hint: Any, source: str) -> Any:
    if typing.get_origin(hint) in (types.UnionType, typing.Union):
        if value is None:
            if type(None) not in typing.get_args(hint):
                raise IntegrityBug(f"{source} is null")
            return None
        (inner,) = [a for a in typing.get_args(hint) if a is not type(None)]
        return _convert(value, inner, source)
    if value is None and hint is not Any:
        raise IntegrityBug(f"{source} is null")
    return _convert_present(value, hint, source)


def _convert_present(value: Any, hint: Any, source: str) -> Any:
    if typing.get_origin(hint) is tuple:
        item = typing.get_args(hint)[0]
        return tuple(_convert(v, item, source) for v in value)
    if dataclasses.is_dataclass(hint):
        return document(value, hint, source)  # type: ignore[arg-type]
    if isinstance(hint, type) and issubclass(hint, Enum):
        return hint(value)
    converter = _SCALARS.get(hint, _any if hint is Any else None)
    if converter is None:
        raise IntegrityBug(f"{source} has no conversion for {hint!r}")
    return converter(value)


def _any(value: Any) -> Any:
    return value


def _as_bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise IntegrityBug(f"expected a boolean, got {type(value).__name__}")
    return value


def _as_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise IntegrityBug(f"expected an integer, got {type(value).__name__}")
    return value


def _as_str(value: Any) -> str:
    if not isinstance(value, str):
        raise IntegrityBug(f"expected text, got {type(value).__name__}")
    return value


def _as_decimal(value: Any) -> Decimal:
    # jsonb numbers arrive as int or float; repr() of a float is the shortest text that round-trips.
    return Decimal(repr(value)) if isinstance(value, float) else Decimal(value)


_SCALARS: dict[Any, Callable[[Any], Any]] = {
    bool: _as_bool,
    int: _as_int,
    str: _as_str,
    float: float,
    Decimal: _as_decimal,
    UUID: lambda v: v if isinstance(v, UUID) else UUID(v),
    date: lambda v: v if isinstance(v, date) else date.fromisoformat(v),
    datetime: lambda v: v if isinstance(v, datetime) else datetime.fromisoformat(v),
}
