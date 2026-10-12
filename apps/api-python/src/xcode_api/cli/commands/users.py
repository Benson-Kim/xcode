"""``xcode-api provision-user|remove-user|clear-pause|revoke-sessions|account-state``.

Each connects as ``xcode_operator`` through ``XCODE_DATABASE_OPERATOR_URL`` (exit 2 when it
is unset), passes ``XCODE_OPERATOR`` and a fresh request id to its ``api.ops_*`` routine,
and prints ids and counts only, never personal data beyond what the operator typed. A
refusal prints its code, is recorded in ``ops.operator_actions`` (the routine's own record
rolled back with it) and exits 1 (``docs/08-operability.md`` section 8).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from datetime import datetime
from typing import Any

from psycopg_pool import PoolTimeout

from ...application.errors import TransientFailure
from ...application.ops.clear_pause import ClearPause, ClearPauseCommand
from ...application.ops.provision_user import ProvisionUser, ProvisionUserCommand
from ...application.ops.read_account_state import ReadAccountState, ReadAccountStateCommand
from ...application.ops.remove_user import RemoveUser, RemoveUserCommand
from ...application.ops.revoke_sessions import RevokeSessions, RevokeSessionsCommand
from ...application.ports import Clock
from ...application.repositories import OpsRepository
from ...db.pool import open_operator_pool
from ...db.routines.ops import OpsRoutines
from ...domain.errors import DomainRefusal
from ...infra.clock import SystemClock
from ...settings import SettingsError, load_cli_settings
from .db import resolve_operator

CONNECT_TIMEOUT_SECONDS = 30.0

Perform = Callable[[OpsRepository, Clock, str, str, argparse.Namespace], Awaitable[str]]


class UserCommand:
    """One operator command: its arguments and what it performs through ``OpsRepository``."""

    def __init__(
        self,
        name: str,
        help_text: str,
        perform: Perform,
        arguments: Callable[[argparse.ArgumentParser], None] | None = None,
    ) -> None:
        self.NAME = name
        self.HELP = help_text
        self._perform = perform
        self._arguments = arguments

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--email", required=True)
        if self._arguments is not None:
            self._arguments(parser)

    def run(self, args: argparse.Namespace) -> int:
        try:
            settings = load_cli_settings()
        except SettingsError as exc:
            for message in exc.messages:
                print(message)
            return 2
        if not settings.database_operator_url:
            print(f"XCODE_DATABASE_OPERATOR_URL is required for {self.NAME}")
            return 2
        operator = resolve_operator(settings)
        request_id = uuid.uuid4().hex
        return _run(self._execute(settings.database_operator_url, operator, request_id, args))

    async def _execute(
        self, url: str, operator: str, request_id: str, args: argparse.Namespace
    ) -> int:
        pool = open_operator_pool(url)
        try:
            await pool.open(wait=True, timeout=CONNECT_TIMEOUT_SECONDS)
        except PoolTimeout:
            print("could not connect to the database as the operator")
            await pool.close()
            return 1
        try:
            ops = OpsRoutines(pool)
            try:
                line = await self._perform(ops, SystemClock(), operator, request_id, args)
            except DomainRefusal as refusal:
                await _record_refusal(
                    ops,
                    operator=operator,
                    action=self.NAME,
                    email=args.email,
                    refusal=refusal,
                    request_id=request_id,
                )
                print(f"refused: {refusal.code}")
                return 1
            except TransientFailure:
                print("the database is not available right now")
                return 1
            print(line)
            return 0
        finally:
            await pool.close()


def _run(coroutine: Coroutine[Any, Any, int]) -> int:
    # psycopg's async connections need the selector loop on Windows.
    loop_factory = asyncio.SelectorEventLoop if os.name == "nt" else None
    return asyncio.run(coroutine, loop_factory=loop_factory)


async def _record_refusal(
    ops: OpsRepository,
    *,
    operator: str,
    action: str,
    email: str,
    refusal: DomainRefusal,
    request_id: str,
) -> None:
    try:
        await ops.record_operator_action(
            operator,
            action,
            email.strip().lower(),
            {"refused": refusal.code, "request_id": request_id},
        )
    except (DomainRefusal, TransientFailure):
        print("the refusal could not be recorded")


def _flag(value: bool) -> str:
    return "yes" if value else "no"


def _instant(value: datetime | None) -> str:
    return "none" if value is None else value.isoformat()


def _provision_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--phone", required=True)
    parser.add_argument("--role", default=None)
    parser.add_argument("--first-name", dest="first_name", default=None)
    parser.add_argument("--last-name", dest="last_name", default=None)
    parser.add_argument("--organization-name", dest="organization_name", default=None)


async def _provision(
    ops: OpsRepository, clock: Clock, operator: str, request_id: str, args: argparse.Namespace
) -> str:
    result = await ProvisionUser(ops, clock).execute(
        ProvisionUserCommand(
            operator=operator,
            request_id=request_id,
            email=args.email,
            phone=args.phone,
            role=args.role,
            first_name=args.first_name,
            last_name=args.last_name,
            organization_name=args.organization_name,
        )
    )
    return (
        f"user_id={result.user_id} organization_id={result.organization_id} "
        f"created_user={_flag(result.created_user)} "
        f"created_organization={_flag(result.created_organization)} "
        f"reactivated={_flag(result.reactivated)}\n"
        "They can now set a PIN with an email code."
    )


async def _remove(
    ops: OpsRepository, clock: Clock, operator: str, request_id: str, args: argparse.Namespace
) -> str:
    result = await RemoveUser(ops, clock).execute(
        RemoveUserCommand(operator=operator, request_id=request_id, email=args.email)
    )
    return f"user_id={result.user_id} removed={_flag(result.removed)} tokens={result.tokens}"


async def _clear_pause(
    ops: OpsRepository, clock: Clock, operator: str, request_id: str, args: argparse.Namespace
) -> str:
    result = await ClearPause(ops, clock).execute(
        ClearPauseCommand(operator=operator, request_id=request_id, email=args.email)
    )
    return f"user_id={result.user_id} was_locked={_flag(result.was_locked)}"


async def _revoke_sessions(
    ops: OpsRepository, clock: Clock, operator: str, request_id: str, args: argparse.Namespace
) -> str:
    result = await RevokeSessions(ops, clock).execute(
        RevokeSessionsCommand(operator=operator, request_id=request_id, email=args.email)
    )
    return f"user_id={result.user_id} devices={result.devices} tokens={result.tokens}"


async def _account_state(
    ops: OpsRepository, clock: Clock, operator: str, request_id: str, args: argparse.Namespace
) -> str:
    state = await ReadAccountState(ops, clock).execute(
        ReadAccountStateCommand(operator=operator, request_id=request_id, email=args.email)
    )
    return (
        f"user_id={state.user_id} status={state.status.value} has_pin={_flag(state.has_pin)} "
        f"pin_reset_required={_flag(state.pin_reset_required)} "
        f"sign_in_status={state.sign_in_status.value} "
        f"last_signed_in_at={_instant(state.last_signed_in_at)} "
        f"failed_attempts={state.failed_attempts} "
        f"untrusted_failed_attempts={state.untrusted_failed_attempts} "
        f"trusted_devices={state.trusted_devices} "
        f"live_refresh_tokens={state.live_refresh_tokens} "
        f"active_membership={_flag(state.active_membership)}"
    )


COMMANDS = (
    UserCommand(
        "provision-user",
        "create or re-activate a person; they then set a PIN with an email code",
        _provision,
        _provision_arguments,
    ),
    UserCommand("remove-user", "mark a user removed and revoke their refresh tokens", _remove),
    UserCommand(
        "clear-pause", "clear a sign-in pause (never the untrusted-device cap)", _clear_pause
    ),
    UserCommand(
        "revoke-sessions", "end every session and device trust of a user", _revoke_sessions
    ),
    UserCommand(
        "account-state", "print an account's status, pause, counters and counts", _account_state
    ),
)
