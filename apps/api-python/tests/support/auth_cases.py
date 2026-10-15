"""One scenario table for the ``api.auth_*`` routines, run against two worlds.

A case arranges accounts and state through a :class:`World`, calls repository methods through
it, and ends with an :class:`Observation`: every outcome projected to comparable values plus
the account state the calls changed. :class:`FakeWorld` drives ``FakeIdentityRepository``;
:class:`DatabaseWorld` drives ``IdentityRoutines`` on PostgreSQL. The same case must observe
the same thing in both, and must match its stated outcome kind and refusal. Time is always an
explicit instant (``T0`` and offsets), never the wall clock.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from xcode_api.application.repositories import IdentityRepository
from xcode_api.domain.errors import NotFound, SessionInvalid
from xcode_api.domain.identity import (
    AccountLookup,
    AccountState,
    AuthOutcome,
    CodeCheck,
    CodeEntry,
    CodePurpose,
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
    UserLookup,
    UserStatus,
)

from .fakes import FakeIdentityRepository, role_permissions
from .scenario import (
    CODE_HASH,
    EMAIL,
    NEW_CODE_HASH,
    NEW_PIN_HASH,
    NORMALIZED,
    PHONE,
    PIN_HASH,
    T0,
    TRUSTED,
    UNTRUSTED,
    WRONG_CODE_HASH,
    Conn,
    digest,
    provision,
    set_user,
    store_code,
    store_token,
    trust,
    user_row,
)

OTHER = "other-device"
THIRD = "third-device"
STRANGER = UUID(int=1)
MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
LATER = T0 + 30 * DAY
NEWER_CODE_HASH = digest("code:654321")
TOKEN = "held-device-token"
ISSUED = "issued-device-token"

_POLICY_COLUMNS = frozenset(
    {
        "pin_length",
        "lockout_threshold",
        "lockout_minutes",
        "access_token_minutes",
        "refresh_token_days",
    }
)
_USER_COLUMNS = frozenset(
    {
        "failed_attempts",
        "untrusted_failed_attempts",
        "status",
        "security_version",
        "pin_hash",
        "pin_reset_required",
        "last_signed_in_at",
    }
)


def token_hash(name: str) -> str:
    return digest(f"token:{name}")


def device_token_hash(token: str | None) -> str | None:
    """A device token's digest; ``None`` stays ``None`` (the released routes) and ``""`` is
    the new routes' "no token sent"."""
    if not token:
        return token
    return digest(f"device-token:{token}")


@dataclass(frozen=True, slots=True)
class Ref:
    """An account the world created: its identity as the caller needs it."""

    user_id: UUID
    organization_id: UUID
    email: str
    phone: str
    label: str


@dataclass(frozen=True, slots=True)
class Seen:
    """One repository call projected to values that are equal across worlds."""

    call: str
    kind: str
    refusal: str | None = None
    retry_after_seconds: int | None = None
    masked_email: str | None = None
    code_issued: bool | None = None
    code_id_set: bool = False
    email: str | None = None
    minimum_pin_length: int | None = None
    user: str | None = None
    organization_matches: bool | None = None
    role: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    permissions: tuple[str, ...] | None = None
    security_version: int | None = None
    access_token_minutes: int | None = None
    refresh_expires_at: datetime | None = None
    purpose: str | None = None
    tries_left: int | None = None
    pin_problem: str | None = None
    device_token_issued: bool | None = None
    detail: tuple[Any, ...] | None = None


@dataclass(frozen=True, slots=True)
class Snapshot:
    """The state of one account after the calls: counters, sessions, codes, devices.

    A device is ``(device_id, revoked, trust_expires_at, token_hash, name, remembered,
    last_used_at)``; see :func:`row`."""

    label: str
    status: str
    pin_hash: str | None
    security_version: int
    failed_attempts: int
    untrusted_failed_attempts: int
    pin_reset_required: bool
    last_signed_in_at: datetime | None
    live_tokens: tuple[tuple[str, int], ...]
    tokens_total: int
    codes: tuple[tuple[Any, ...], ...]
    devices: tuple[tuple[Any, ...], ...]

    def live(self, device: str) -> int:
        return dict(self.live_tokens).get(device, 0)

    def device(self, device: str) -> tuple[Any, ...] | None:
        return next((d for d in self.devices if d[0] == device), None)


def row(
    device: str,
    *,
    revoked: bool = False,
    expires: datetime | None = None,
    token: str | None = None,
    name: str | None = None,
    remembered: bool = True,
    used: datetime = T0,
) -> tuple[Any, ...]:
    """The device tuple of a :class:`Snapshot`; ``token`` is the device token, not its digest."""
    return (device, revoked, expires, device_token_hash(token), name, remembered, used)


@dataclass(frozen=True, slots=True)
class Observation:
    steps: tuple[Seen, ...]
    accounts: tuple[Snapshot, ...]

    @property
    def last(self) -> Seen:
        return self.steps[-1]

    @property
    def account(self) -> Snapshot:
        return self.accounts[0]


def _code_row(
    created_at: datetime,
    purpose: str,
    device: str,
    consumed: bool,
    failed_attempts: int,
    expires_at: datetime,
) -> tuple[Any, ...]:
    lifetime = int((expires_at - created_at).total_seconds())
    return (created_at, purpose, device, consumed, failed_attempts, lifetime)


class World:
    """The arrangement and calling surface cases use; subclasses supply the storage."""

    repo: IdentityRepository

    def __init__(self) -> None:
        self.refs: list[Ref] = []
        self.steps: list[Seen] = []
        self._issued = 0

    # --- arranging (implemented per world) --------------------------------------------------

    async def add_account(
        self,
        *,
        email: str = EMAIL,
        phone: str = PHONE,
        pin: bool = True,
        status: str = "active",
        role: str | None = "Owner",
        first_name: str = "Jane",
        last_name: str = "Doe",
        membership: bool = True,
    ) -> Ref:
        raise NotImplementedError

    async def set_policy(self, ref: Ref, **fields: int) -> None:
        raise NotImplementedError

    async def trust(
        self,
        ref: Ref,
        device: str,
        *,
        expires_at: datetime | None = None,
        revoked: bool = False,
        token: str | None = None,
        name: str | None = None,
        remembered: bool = True,
        last_used_at: datetime = T0,
    ) -> None:
        raise NotImplementedError

    async def store_token(
        self,
        ref: Ref,
        device: str,
        name: str,
        *,
        expires_at: datetime = LATER,
        revoked: bool = False,
    ) -> str:
        raise NotImplementedError

    async def store_code(
        self,
        ref: Ref,
        purpose: CodePurpose,
        device: str,
        *,
        code_hash: str = CODE_HASH,
        created_at: datetime = T0,
        consumed: bool = False,
        withdrawn: bool = False,
        failed_attempts: int = 0,
    ) -> UUID:
        raise NotImplementedError

    async def set_user(self, ref: Ref, **fields: Any) -> None:
        raise NotImplementedError

    async def snapshot(self, ref: Ref) -> Snapshot:
        raise NotImplementedError

    async def row_id(self, ref: Ref, device: str) -> UUID:
        raise NotImplementedError

    async def device_ids(self, ref: Ref) -> dict[UUID, str]:
        raise NotImplementedError

    # --- observing --------------------------------------------------------------------------

    async def observe(self) -> Observation:
        accounts = [await self.snapshot(ref) for ref in self.refs]
        return Observation(tuple(self.steps), tuple(accounts))

    def _label(self, user_id: UUID | None) -> str | None:
        if user_id is None:
            return None
        return next((r.label for r in self.refs if r.user_id == user_id), "stranger")

    def _fresh_hash(self) -> str:
        self._issued += 1
        return digest(f"issued:{self._issued}")

    def _record(self, call: str, outcome: AuthOutcome) -> AuthOutcome:
        organization = self.refs[0].organization_id if self.refs else None
        self.steps.append(
            Seen(
                call=call,
                kind=outcome.outcome.value,
                refusal=outcome.refusal.value if outcome.refusal else None,
                retry_after_seconds=outcome.retry_after_seconds,
                masked_email=outcome.masked_email,
                code_issued=outcome.code_issued,
                code_id_set=outcome.code_id is not None,
                email=outcome.email,
                minimum_pin_length=outcome.minimum_pin_length,
                user=self._label(outcome.user_id),
                organization_matches=(
                    None
                    if outcome.organization_id is None
                    else outcome.organization_id == organization
                ),
                role=outcome.role,
                first_name=outcome.first_name,
                last_name=outcome.last_name,
                permissions=outcome.permissions,
                security_version=outcome.security_version,
                access_token_minutes=outcome.access_token_minutes,
                refresh_expires_at=outcome.refresh_expires_at,
                purpose=outcome.purpose.value if outcome.purpose else None,
                tries_left=outcome.tries_left,
                pin_problem=outcome.pin_problem.value if outcome.pin_problem else None,
                device_token_issued=outcome.device_token_issued,
            )
        )
        return outcome

    # --- calling ----------------------------------------------------------------------------

    def _seen_state(self, call: str, state: AccountState | None) -> AccountState | None:
        if state is None:
            self.steps.append(Seen(call=call, kind="no_account"))
            return None
        policy = state.policy
        organization = self.refs[0].organization_id if self.refs else None
        policy_detail = (
            None
            if policy is None
            else (
                policy.organization_id == organization,
                policy.pin_length,
                policy.lockout_threshold,
                policy.lockout_minutes,
                policy.access_token_minutes,
                policy.refresh_token_days,
                policy.role_name,
                policy.first_name,
                policy.last_name,
                policy.permissions,
            )
        )
        self.steps.append(
            Seen(
                call=call,
                kind="lookup",
                user=self._label(state.user_id),
                detail=(
                    state.status.value,
                    state.pin_hash,
                    state.phone_number,
                    state.security_version,
                    state.failed_attempts,
                    state.untrusted_failed_attempts,
                    state.pin_reset_required,
                    state.device_trusted,
                    policy_detail,
                ),
            )
        )
        return state

    async def lookup(
        self,
        phone: str = PHONE,
        device: str = TRUSTED,
        now: datetime = T0,
        *,
        token: str | None = None,
        pin_try: bool = True,
    ) -> AccountState | None:
        """The released routes' lookup (``token=None``), or a new route's (``token=""`` for
        none sent)."""
        state = await self.repo.account_lookup(
            AccountLookup("req-case", phone, device, now, device_token_hash(token), pin_try)
        )
        return self._seen_state("account_lookup", state)

    async def lookup_user(
        self, who: Ref | UUID, device: str = TRUSTED, now: datetime = T0
    ) -> AccountState | None:
        user_id = who.user_id if isinstance(who, Ref) else who
        state = await self.repo.account_lookup_user(UserLookup("req-case", user_id, device, now))
        return self._seen_state("account_lookup_user", state)

    async def start(
        self,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        token: str | None = None,
        code_hash: str = CODE_HASH,
        skip_cooldown: bool = False,
        now: datetime = T0,
    ) -> AuthOutcome:
        command = NumberCheck(
            "req-case", phone, device, device_token_hash(token), code_hash, skip_cooldown, now
        )
        return self._record("start", await self.repo.start(command))

    async def sign_in(
        self,
        ref: Ref | None,
        *,
        device: str = TRUSTED,
        pin_ok: bool = True,
        checked_pin_hash: str | None = PIN_HASH,
        code_hash: str | None = CODE_HASH,
        skip_cooldown: bool = False,
        now: datetime = T0,
    ) -> AuthOutcome:
        verdict = PinVerdict(
            request_id="req-case",
            user_id=None if ref is None else ref.user_id,
            device_id=device,
            pin_ok=pin_ok,
            checked_pin_hash=checked_pin_hash,
            code_hash=code_hash,
            refresh_token_hash=self._fresh_hash(),
            skip_cooldown=skip_cooldown,
            now=now,
        )
        return self._record("sign_in", await self.repo.sign_in(verdict))

    async def pin(
        self,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        token: str | None = None,
        pin_ok: bool = True,
        checked_pin_hash: str | None = PIN_HASH,
        code_hash: str = CODE_HASH,
        skip_cooldown: bool = False,
        now: datetime = T0,
    ) -> AuthOutcome:
        """The PIN step as the service runs it: the lookup that records an unknown number's
        try, then the verdict."""
        token_digest = device_token_hash(token or "")
        await self.repo.account_lookup(
            AccountLookup("req-case", phone, device, now, token_digest, True)
        )
        command = PinCheck(
            "req-case",
            phone,
            device,
            token_digest,
            pin_ok,
            checked_pin_hash,
            code_hash,
            self._fresh_hash(),
            skip_cooldown,
            now,
        )
        return self._record("pin", await self.repo.pin(command))

    async def check_code(
        self,
        purpose: CodePurpose,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        code_hash: str = CODE_HASH,
        replacement_hash: str = NEW_CODE_HASH,
        name: str | None = None,
        trust: bool = True,
        token: str | None = None,
        trust_days: int | None = None,
        now: datetime = T0,
    ) -> AuthOutcome:
        command = CodeEntry(
            "req-case",
            phone,
            device,
            purpose,
            code_hash,
            replacement_hash,
            name,
            trust,
            device_token_hash(token),
            self._fresh_hash(),
            trust_days,
            now,
        )
        return self._record("check_code", await self.repo.check_code(command))

    async def resend_code(
        self,
        purpose: CodePurpose,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        code_hash: str = NEW_CODE_HASH,
        skip_cooldown: bool = False,
        now: datetime = T0,
    ) -> AuthOutcome:
        command = CodeResend("req-case", phone, device, purpose, code_hash, skip_cooldown, now)
        return self._record("resend_code", await self.repo.resend_code(command))

    async def verify_device(
        self,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        code_hash: str = CODE_HASH,
        replacement_hash: str = NEW_CODE_HASH,
        trust_days: int | None = None,
        now: datetime = T0,
    ) -> AuthOutcome:
        command = DeviceVerification(
            "req-case",
            phone,
            device,
            code_hash,
            replacement_hash,
            self._fresh_hash(),
            trust_days,
            now,
        )
        return self._record("verify_device", await self.repo.verify_device(command))

    async def request_code(
        self,
        purpose: CodePurpose,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        code_hash: str = CODE_HASH,
        skip_cooldown: bool = False,
        now: datetime = T0,
    ) -> AuthOutcome:
        command = CodeRequest("req-case", phone, device, purpose, code_hash, skip_cooldown, now)
        return self._record("request_code", await self.repo.request_code(command))

    async def verify_code(
        self,
        purpose: CodePurpose,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        code_hash: str = CODE_HASH,
        replacement_hash: str = NEW_CODE_HASH,
        now: datetime = T0,
    ) -> AuthOutcome:
        command = CodeCheck("req-case", phone, device, purpose, code_hash, replacement_hash, now)
        return self._record("verify_code", await self.repo.verify_code(command))

    async def complete_pin(
        self,
        purpose: CodePurpose,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        code_hash: str = CODE_HASH,
        new_pin_is_current: bool = False,
        checked_pin_hash: str | None = PIN_HASH,
        name: str | None = None,
        trust: bool = True,
        token: str | None = None,
        trust_days: int | None = None,
        now: datetime = T0,
    ) -> AuthOutcome:
        """A completion; a first PIN has nothing to check the new PIN against."""
        command = PinCompletion(
            "req-case",
            phone,
            device,
            purpose,
            code_hash,
            new_pin_is_current,
            checked_pin_hash if purpose is CodePurpose.PIN_RESET else None,
            NEW_PIN_HASH,
            name,
            trust,
            device_token_hash(token),
            self._fresh_hash(),
            trust_days,
            now,
        )
        return self._record("complete_pin", await self.repo.complete_pin(command))

    async def change_pin(
        self,
        who: Ref | UUID,
        *,
        device: str = TRUSTED,
        current_ok: bool = True,
        checked_pin_hash: str | None = PIN_HASH,
        now: datetime = T0,
    ) -> AuthOutcome:
        user_id = who.user_id if isinstance(who, Ref) else who
        command = PinChange(
            "req-case", user_id, device, current_ok, checked_pin_hash, NEW_PIN_HASH, now
        )
        return self._record("change_pin", await self.repo.change_pin(command))

    async def device_list(
        self, who: Ref | UUID, *, device: str = TRUSTED, now: datetime = T0
    ) -> None:
        user_id = who.user_id if isinstance(who, Ref) else who
        ids = await self.device_ids(who) if isinstance(who, Ref) else {}
        views = await self.repo.device_list(DeviceListing(user_id, device, now))
        self.steps.append(
            Seen(
                call="device_list",
                kind="devices",
                detail=tuple(
                    (ids[v.id], v.name, v.trusted_at, v.last_used_at, v.this_device) for v in views
                ),
            )
        )

    async def device_remove(
        self, who: Ref | UUID, row: UUID, *, now: datetime = T0
    ) -> AuthOutcome | None:
        user_id = who.user_id if isinstance(who, Ref) else who
        try:
            outcome = await self.repo.device_remove(DeviceRemoval("req-case", user_id, row, now))
        except NotFound:
            self.steps.append(Seen(call="device_remove", kind="not_found"))
            return None
        return self._record("device_remove", outcome)

    async def refresh(
        self,
        name: str,
        *,
        device: str = TRUSTED,
        new: str | None = None,
        now: datetime = T0,
    ) -> AuthOutcome:
        command = TokenRefresh(
            "req-case",
            token_hash(name),
            device,
            self._fresh_hash() if new is None else token_hash(new),
            now,
        )
        return self._record("refresh", await self.repo.refresh(command))

    async def sign_out(
        self, name: str, *, device: str = TRUSTED, now: datetime = T0
    ) -> AuthOutcome:
        command = TokenSignOut("req-case", token_hash(name), device, now)
        return self._record("sign_out", await self.repo.sign_out(command))

    async def revoke_device(
        self, who: Ref | UUID, *, device: str = TRUSTED, now: datetime = T0
    ) -> AuthOutcome:
        user_id = who.user_id if isinstance(who, Ref) else who
        command = DeviceRevocation("req-case", user_id, device, now)
        return self._record("revoke_device", await self.repo.revoke_device(command))

    async def withdraw(self, code_id: UUID, *, now: datetime = T0) -> None:
        await self.repo.withdraw_code(CodeWithdrawal("req-case", code_id, now))
        self.steps.append(Seen(call="withdraw_code", kind="withdrawn"))

    async def resolve(
        self,
        who: Ref | UUID,
        version: int = 0,
        *,
        device: str = TRUSTED,
        now: datetime = T0,
    ) -> SessionContext | None:
        user_id = who.user_id if isinstance(who, Ref) else who
        try:
            context = await self.repo.resolve_session(SessionCheck(user_id, device, version, now))
        except SessionInvalid:
            self.steps.append(Seen(call="resolve_session", kind="session_invalid"))
            return None
        organization = self.refs[0].organization_id if self.refs else None
        self.steps.append(
            Seen(
                call="resolve_session",
                kind="session",
                role=context.role,
                organization_matches=(
                    None
                    if context.organization_id is None
                    else context.organization_id == organization
                ),
            )
        )
        return context


class FakeWorld(World):
    """The cases against ``FakeIdentityRepository``."""

    def __init__(self, *, calls: list[str] | None = None) -> None:
        super().__init__()
        self.fake = FakeIdentityRepository(calls=calls)
        self.repo = self.fake

    async def add_account(
        self,
        *,
        email: str = EMAIL,
        phone: str = PHONE,
        pin: bool = True,
        status: str = "active",
        role: str | None = "Owner",
        first_name: str = "Jane",
        last_name: str = "Doe",
        membership: bool = True,
    ) -> Ref:
        user_id = self.fake.add_account(
            email=email,
            phone=phone,
            pin_hash=PIN_HASH if pin else None,
            status=UserStatus(status),
            role=role,
            first_name=first_name,
            last_name=last_name,
            membership=membership,
        )
        ref = Ref(user_id, self.fake.user(user_id).organization_id, email, phone, self._next())
        self.refs.append(ref)
        return ref

    def _next(self) -> str:
        return f"account{len(self.refs)}"

    async def set_policy(self, ref: Ref, **fields: int) -> None:
        self.fake.set_policy(ref.organization_id, **fields)

    async def trust(
        self,
        ref: Ref,
        device: str,
        *,
        expires_at: datetime | None = None,
        revoked: bool = False,
        token: str | None = None,
        name: str | None = None,
        remembered: bool = True,
        last_used_at: datetime = T0,
    ) -> None:
        self.fake.trust(
            ref.user_id,
            device,
            expires_at=expires_at,
            revoked=revoked,
            token_hash=device_token_hash(token),
            name=name,
            remembered=remembered,
            last_used_at=last_used_at,
        )

    async def store_token(
        self,
        ref: Ref,
        device: str,
        name: str,
        *,
        expires_at: datetime = LATER,
        revoked: bool = False,
    ) -> str:
        digest_ = token_hash(name)
        self.fake.store_token(ref.user_id, device, digest_, expires_at=expires_at, revoked=revoked)
        return digest_

    async def store_code(
        self,
        ref: Ref,
        purpose: CodePurpose,
        device: str,
        *,
        code_hash: str = CODE_HASH,
        created_at: datetime = T0,
        consumed: bool = False,
        withdrawn: bool = False,
        failed_attempts: int = 0,
    ) -> UUID:
        return self.fake.store_code(
            ref.user_id,
            purpose,
            device,
            code_hash,
            created_at=created_at,
            consumed=consumed,
            withdrawn=withdrawn,
            failed_attempts=failed_attempts,
        )

    async def set_user(self, ref: Ref, **fields: Any) -> None:
        if "status" in fields:
            fields["status"] = UserStatus(fields["status"])
        self.fake.set_user(ref.user_id, **fields)

    async def snapshot(self, ref: Ref) -> Snapshot:
        user = self.fake.user(ref.user_id)
        tokens = self.fake.tokens(ref.user_id)
        live: dict[str, int] = {}
        for token in tokens:
            if not token.revoked:
                live[token.device_id] = live.get(token.device_id, 0) + 1
        codes = sorted(
            _code_row(
                c.created_at,
                c.purpose.value,
                c.device_id,
                c.consumed,
                c.failed_attempts,
                c.expires_at,
            )
            for c in self.fake.codes(ref.user_id)
        )
        devices = sorted(
            (
                d.device_id,
                d.revoked,
                d.trust_expires_at,
                d.token_hash,
                d.name,
                d.remembered,
                d.last_used_at,
            )
            for d in self.fake.devices(ref.user_id)
        )
        return Snapshot(
            label=ref.label,
            status=user.status.value,
            pin_hash=user.pin_hash,
            security_version=user.security_version,
            failed_attempts=user.failed_attempts,
            untrusted_failed_attempts=user.untrusted_failed_attempts,
            pin_reset_required=user.pin_reset_required,
            last_signed_in_at=user.last_signed_in_at,
            live_tokens=tuple(sorted(live.items())),
            tokens_total=len(tokens),
            codes=tuple(codes),
            devices=tuple(devices),
        )

    async def row_id(self, ref: Ref, device: str) -> UUID:
        found = next(d for d in self.fake.devices(ref.user_id) if d.device_id == device)
        return found.row_id

    async def device_ids(self, ref: Ref) -> dict[UUID, str]:
        return {d.row_id: d.device_id for d in self.fake.devices(ref.user_id)}


class DatabaseWorld(World):
    """The cases against ``IdentityRoutines`` on PostgreSQL: accounts provisioned as
    ``xcode_operator``, state adjusted as ``xcode_owner``, routines called as ``xcode_app``."""

    def __init__(self, repo: IdentityRepository, operator: Conn, owner: Conn) -> None:
        super().__init__()
        self.repo = repo
        self.operator = operator
        self.owner = owner

    async def add_account(
        self,
        *,
        email: str = EMAIL,
        phone: str = PHONE,
        pin: bool = True,
        status: str = "active",
        role: str | None = "Owner",
        first_name: str = "Jane",
        last_name: str = "Doe",
        membership: bool = True,
    ) -> Ref:
        created = provision(
            self.operator,
            email=email,
            phone=phone,
            role=role,
            first_name=first_name,
            last_name=last_name,
        )
        user_id = UUID(created["user_id"])
        ref = Ref(
            user_id, UUID(created["organization_id"]), email, phone, f"account{len(self.refs)}"
        )
        self.refs.append(ref)
        if pin:
            set_user(self.owner, user_id, pin_hash=PIN_HASH)
        if status != "active":
            set_user(self.owner, user_id, status=status)
        if not membership:
            self.owner.execute(
                "UPDATE tenancy.memberships SET active = false WHERE user_id = %s", (user_id,)
            )
        if role is None:
            self.owner.execute("DELETE FROM tenancy.person_roles WHERE user_id = %s", (user_id,))
        return ref

    async def set_policy(self, ref: Ref, **fields: int) -> None:
        assert set(fields) <= _POLICY_COLUMNS
        assignments = ", ".join(f"{name} = %s" for name in fields)
        self.owner.execute(
            f"UPDATE tenancy.organization_security_policies SET {assignments} "
            "WHERE organization_id = %s",
            (*fields.values(), ref.organization_id),
        )

    async def trust(
        self,
        ref: Ref,
        device: str,
        *,
        expires_at: datetime | None = None,
        revoked: bool = False,
        token: str | None = None,
        name: str | None = None,
        remembered: bool = True,
        last_used_at: datetime = T0,
    ) -> None:
        trust(
            self.owner,
            ref.user_id,
            device,
            expires_at=expires_at,
            revoked=revoked,
            token_hash=device_token_hash(token),
            name=name,
            remembered=remembered,
            last_used_at=last_used_at,
        )

    async def store_token(
        self,
        ref: Ref,
        device: str,
        name: str,
        *,
        expires_at: datetime = LATER,
        revoked: bool = False,
    ) -> str:
        return store_token(
            self.owner,
            ref.user_id,
            device,
            token_hash=token_hash(name),
            expires_at=expires_at,
            revoked=revoked,
        )

    async def store_code(
        self,
        ref: Ref,
        purpose: CodePurpose,
        device: str,
        *,
        code_hash: str = CODE_HASH,
        created_at: datetime = T0,
        consumed: bool = False,
        withdrawn: bool = False,
        failed_attempts: int = 0,
    ) -> UUID:
        return store_code(
            self.owner,
            ref.user_id,
            purpose.value,
            device,
            code_hash=code_hash,
            created_at=created_at,
            consumed=consumed,
            withdrawn=withdrawn,
            failed_attempts=failed_attempts,
        )

    async def set_user(self, ref: Ref, **fields: Any) -> None:
        assert set(fields) <= _USER_COLUMNS
        set_user(self.owner, ref.user_id, **fields)

    async def snapshot(self, ref: Ref) -> Snapshot:
        user = user_row(self.owner, ref.user_id)
        tokens = self.owner.execute(
            "SELECT device_id, revoked FROM identity.refresh_tokens WHERE user_id = %s",
            (ref.user_id,),
        ).fetchall()
        live: dict[str, int] = {}
        for token in tokens:
            if not token["revoked"]:
                live[token["device_id"]] = live.get(token["device_id"], 0) + 1
        code_rows = self.owner.execute(
            "SELECT * FROM identity.verification_codes WHERE user_id = %s", (ref.user_id,)
        ).fetchall()
        codes = sorted(
            _code_row(
                c["created_at"],
                c["purpose"],
                c["device_id"],
                c["consumed"],
                c["failed_attempts"],
                c["expires_at"],
            )
            for c in code_rows
        )
        device_rows = self.owner.execute(
            "SELECT device_id, revoked, trust_expires_at, token_hash, name, remembered, "
            "last_used_at FROM identity.trusted_devices WHERE user_id = %s",
            (ref.user_id,),
        ).fetchall()
        devices = sorted(
            (
                d["device_id"],
                d["revoked"],
                d["trust_expires_at"],
                d["token_hash"],
                d["name"],
                d["remembered"],
                d["last_used_at"],
            )
            for d in device_rows
        )
        return Snapshot(
            label=ref.label,
            status=user["status"],
            pin_hash=user["pin_hash"],
            security_version=user["security_version"],
            failed_attempts=user["failed_attempts"],
            untrusted_failed_attempts=user["untrusted_failed_attempts"],
            pin_reset_required=user["pin_reset_required"],
            last_signed_in_at=user["last_signed_in_at"],
            live_tokens=tuple(sorted(live.items())),
            tokens_total=len(tokens),
            codes=tuple(codes),
            devices=tuple(devices),
        )

    async def row_id(self, ref: Ref, device: str) -> UUID:
        found = self.owner.execute(
            "SELECT id FROM identity.trusted_devices WHERE user_id = %s AND device_id = %s",
            (ref.user_id, device),
        ).fetchone()
        assert found is not None
        return UUID(str(found["id"]))

    async def device_ids(self, ref: Ref) -> dict[UUID, str]:
        found = self.owner.execute(
            "SELECT id, device_id FROM identity.trusted_devices WHERE user_id = %s",
            (ref.user_id,),
        ).fetchall()
        return {UUID(str(d["id"])): d["device_id"] for d in found}


# --- the table ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    kind: str
    refusal: str | None
    run: Callable[[World], Awaitable[None]]
    check: Callable[[Observation], None] | None = field(default=None)


CASES: list[Case] = []


def case(
    kind: str, refusal: str | None = None, *, check: Callable[[Observation], None] | None = None
) -> Callable[[Callable[[World], Awaitable[None]]], Callable[[World], Awaitable[None]]]:
    """Register a case; ``kind`` and ``refusal`` are what its last call must answer."""

    def register(run: Callable[[World], Awaitable[None]]) -> Callable[[World], Awaitable[None]]:
        CASES.append(Case(run.__name__, kind, refusal, run, check))
        return run

    return register


async def standard(w: World, **options: Any) -> Ref:
    """An account with a PIN and one device trusted by its id alone (a released phone)."""
    ref = await w.add_account(**options)
    await w.trust(ref, TRUSTED)
    return ref


async def tokened(w: World, **options: Any) -> Ref:
    """An account with a PIN and one device trusted through ``TOKEN`` (a new-model phone)."""
    ref = await w.add_account(**options)
    await w.trust(ref, TRUSTED, token=TOKEN)
    return ref


def lapsed() -> datetime:
    return T0 - timedelta(seconds=1)


async def codes_at(
    w: World,
    ref: Ref,
    purposes: list[CodePurpose],
    *,
    first: timedelta,
    step: timedelta,
    withdrawn: bool = False,
    device: str = OTHER,
) -> None:
    """One code per entry of ``purposes``, the first ``first`` before T0, each ``step`` older."""
    for index, purpose in enumerate(purposes):
        await w.store_code(
            ref,
            purpose,
            device,
            created_at=T0 - first - index * step,
            withdrawn=withdrawn,
            consumed=not withdrawn and index % 2 == 0,
        )


def _expect(condition: bool) -> None:
    assert condition


def _check_no_code(obs: Observation) -> None:
    step = obs.last
    assert (step.code_issued, step.code_id_set, step.email) == (False, False, None)
    assert step.masked_email == "j***@example.com"


def _check_skipped_cooldown(obs: Observation) -> None:
    assert obs.last.code_issued is True
    assert [row[3] for row in obs.account.codes] == [True, False]


# --- the lookups ----------------------------------------------------------------------------


def _check_lookup_state(obs: Observation) -> None:
    first, second = obs.steps
    assert first.detail is not None and second.detail is not None
    assert (first.detail[7], second.detail[7]) == (True, False)
    policy = first.detail[8]
    assert policy[1:9] == (6, 7, 20, 12, 60, "Fleet manager", "Wanjiku", "Kamau")
    assert policy[9] == role_permissions("Fleet manager")
    assert first.detail[:7] == ("active", PIN_HASH, NORMALIZED, 0, 2, 3, True)


@case("lookup", check=_check_lookup_state)
async def lookup_returns_the_state_and_policy_of_the_account(w: World) -> None:
    ref = await standard(w, role="Fleet manager", first_name="Wanjiku", last_name="Kamau")
    await w.set_policy(
        ref,
        pin_length=6,
        lockout_threshold=7,
        lockout_minutes=20,
        access_token_minutes=12,
        refresh_token_days=60,
    )
    await w.set_user(ref, failed_attempts=2, untrusted_failed_attempts=3, pin_reset_required=True)
    await w.lookup("+254 712 345 678", TRUSTED)
    await w.lookup(PHONE, UNTRUSTED)


@case(
    "lookup", check=lambda obs: _expect(obs.last.detail is not None and obs.last.detail[8] is None)
)
async def lookup_without_a_membership_has_no_policy(w: World) -> None:
    await standard(w, membership=False)
    await w.lookup()


@case("no_account")
async def lookup_of_an_unknown_number_finds_nobody(w: World) -> None:
    await standard(w)
    await w.lookup("0799999999")


@case("no_account")
async def lookup_of_a_non_normalising_number_finds_nobody(w: World) -> None:
    await standard(w)
    await w.lookup("12345")


def _trusted_flags(obs: Observation) -> list[bool]:
    return [step.detail[7] for step in obs.steps if step.detail is not None]


@case("lookup", check=lambda o: _expect(_trusted_flags(o) == [True, False, False, False]))
async def lookup_with_a_device_token_trusts_only_the_row_holding_that_token(w: World) -> None:
    await tokened(w)
    await w.lookup(token=TOKEN)
    await w.lookup(token="other-token")
    await w.lookup(token="")
    await w.lookup(token=None)


@case("lookup", check=lambda o: _expect(_trusted_flags(o) == [True, False, False]))
async def lookup_without_a_token_trusts_a_legacy_row_only(w: World) -> None:
    await standard(w)
    await w.lookup(token=None)
    await w.lookup(token=TOKEN)
    await w.lookup(token="")


@case("lookup", check=lambda o: _expect(_trusted_flags(o) == [False, False, True, True]))
async def lookup_trusts_a_device_only_while_it_is_remembered_and_in_use(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, "session-device", remembered=False)
    await w.trust(ref, "idle-device", last_used_at=T0 - 90 * DAY)
    await w.trust(ref, "recent-device", last_used_at=T0 - 90 * DAY + timedelta(seconds=1))
    await w.trust(ref, "lasting-device", expires_at=T0 + timedelta(seconds=1))
    for device in ("session-device", "idle-device", "recent-device", "lasting-device"):
        await w.lookup(device=device)


@case("pin_required", "unknown_number")
async def lookup_of_an_unknown_number_counts_a_pin_try_only_when_asked(w: World) -> None:
    await standard(w)
    for _ in range(6):
        await w.lookup("0799999999", pin_try=False)
    await w.start(phone="0799999999")


@case("pin_locked", "unknown_number")
async def five_pin_tries_in_the_lookup_lock_the_number_step_of_an_unknown_number(w: World) -> None:
    await standard(w)
    for _ in range(5):
        await w.lookup("0799999999")
    await w.start(phone="0799999999")


@case("lookup", check=lambda o: _expect(_trusted_flags(o) == [True, False, True, True]))
async def lookup_user_reports_whether_the_session_device_row_is_live(w: World) -> None:
    ref = await standard(w)
    await w.trust(ref, "session-device", remembered=False)
    await w.trust(ref, "tokened-device", token=TOKEN)
    await w.lookup_user(ref, TRUSTED)
    await w.lookup_user(ref, UNTRUSTED)
    await w.lookup_user(ref, "session-device")
    await w.lookup_user(ref, "tokened-device")


def _check_lookup_user_state(obs: Observation) -> None:
    detail = obs.last.detail
    assert detail is not None
    assert detail[:7] == ("active", PIN_HASH, NORMALIZED, 3, 1, 2, False)
    assert detail[7] is False
    assert detail[8][6:9] == ("Owner", "Jane", "Doe")


@case("lookup", check=_check_lookup_user_state)
async def lookup_user_returns_the_stored_hash_number_and_counters(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, security_version=3, failed_attempts=1, untrusted_failed_attempts=2)
    await w.trust(ref, "revoked-device", revoked=True)
    await w.lookup_user(ref, "revoked-device")


@case("no_account")
async def lookup_user_of_an_unknown_user_finds_nobody(w: World) -> None:
    await standard(w)
    await w.lookup_user(STRANGER)


# --- the number step (start) ----------------------------------------------------------------


def _check_no_code_stored(obs: Observation) -> None:
    assert obs.account.codes == ()


@case("pin_required", "unknown_number", check=lambda o: _expect(o.last.purpose is None))
async def start_of_an_unknown_number_answers_as_an_account_with_a_pin(w: World) -> None:
    await standard(w)
    await w.start(phone="0799999999")


@case("pin_required", "unknown_number")
async def start_of_a_non_normalising_number_answers_as_an_account_with_a_pin(w: World) -> None:
    await standard(w)
    await w.start(phone="12345")


@case("pin_required", "unknown_number")
async def start_of_an_unknown_number_after_four_pin_tries_still_asks_for_the_pin(
    w: World,
) -> None:
    await standard(w)
    for _ in range(4):
        await w.pin(phone="0799999999", pin_ok=False)
    await w.start(phone="0799999999")


@case("pin_locked", "unknown_number")
async def start_of_an_unknown_number_after_five_pin_tries_answers_pin_locked(w: World) -> None:
    await standard(w)
    for _ in range(5):
        await w.pin(phone="0799999999", pin_ok=False)
    await w.start(phone="0799999999")


def _check_start_counts_nothing(obs: Observation) -> None:
    account = obs.account
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (2, 3)
    assert account.codes == () and account.tokens_total == 0


@case("pin_required", check=_check_start_counts_nothing)
async def start_of_an_account_with_a_pin_asks_for_it_and_counts_nothing(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=2, untrusted_failed_attempts=3)
    await w.start()


def _check_setup_code(purpose: str) -> Callable[[Observation], None]:
    def check(obs: Observation) -> None:
        step = obs.last
        assert step.purpose == purpose
        assert step.masked_email == "j***@example.com"
        assert (step.code_issued, step.code_id_set, step.email) == (True, True, EMAIL)
        assert obs.account.codes == (_code_row(T0, purpose, UNTRUSTED, False, 0, T0 + 10 * MINUTE),)

    return check


@case("verification_required", check=_check_setup_code("first_setup"))
async def start_without_a_pin_issues_a_first_setup_code(w: World) -> None:
    await standard(w, pin=False)
    await w.start()


@case("verification_required", check=_check_setup_code("pin_reset"))
async def start_with_a_forced_reset_issues_a_pin_reset_code(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, pin_reset_required=True)
    await w.start()


@case("verification_required", check=_check_setup_code("pin_reset"))
async def start_asks_for_the_forced_reset_before_the_lock(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, pin_reset_required=True, failed_attempts=5, untrusted_failed_attempts=5)
    await w.start()


@case("verification_required", check=_check_no_code)
async def start_without_a_pin_inside_the_cooldown_issues_no_code(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.PIN_RESET, OTHER, created_at=T0 - timedelta(seconds=30))
    await w.start()


@case("verification_required", check=_check_skipped_cooldown)
async def start_can_skip_the_cooldown(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.FIRST_SETUP, OTHER, created_at=T0 - timedelta(seconds=30))
    await w.start(skip_cooldown=True)


@case("blocked", "inactive", check=_check_no_code_stored)
async def start_of_a_removed_account_is_blocked(w: World) -> None:
    await standard(w, status="removed")
    await w.start()


@case("blocked", "inactive", check=_check_no_code_stored)
async def start_without_a_membership_is_blocked(w: World) -> None:
    await standard(w, membership=False)
    await w.start()


@case("blocked", "inactive", check=_check_no_code_stored)
async def start_without_a_role_is_blocked(w: World) -> None:
    await standard(w, role=None)
    await w.start()


@case("blocked", "inactive", check=_check_no_code_stored)
async def start_is_blocked_before_a_missing_pin_is_looked_at(w: World) -> None:
    await standard(w, pin=False, status="removed")
    await w.start()


def _check_start_locked(obs: Observation) -> None:
    account = obs.account
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (5, 1)
    assert account.codes == ()


@case("pin_locked", "locked", check=_check_start_locked)
async def start_locked_on_every_device_refuses_an_untrusted_device(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=1)
    await w.start()


@case("pin_locked", "locked", check=_check_start_locked)
async def start_locked_on_every_device_refuses_a_trusted_device_too(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=1)
    await w.start(device=TRUSTED, token=TOKEN)


@case("pin_locked", "locked")
async def start_locked_for_new_devices_refuses_an_untrusted_device(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, untrusted_failed_attempts=5)
    await w.start()


@case("pin_required")
async def start_locked_for_new_devices_lets_a_token_trusted_device_through(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, untrusted_failed_attempts=5)
    await w.start(device=TRUSTED, token=TOKEN)


@case("pin_locked", "locked")
async def start_locked_for_new_devices_refuses_a_tokened_device_that_sends_no_token(
    w: World,
) -> None:
    ref = await tokened(w)
    await w.set_user(ref, untrusted_failed_attempts=5)
    await w.start(device=TRUSTED)


@case("pin_locked", "locked")
async def start_locked_for_new_devices_refuses_a_legacy_row_on_the_new_route(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, untrusted_failed_attempts=5)
    await w.start(device=TRUSTED, token=TOKEN)


# --- the PIN step (pin) ---------------------------------------------------------------------


def _check_unknown_countdown(obs: Observation) -> None:
    assert [step.tries_left for step in obs.steps] == [4, 3, 2, 1]
    assert all(step.refusal == "unknown_number" for step in obs.steps)


@case("refused", "unknown_number", check=_check_unknown_countdown)
async def pin_of_an_unknown_number_counts_the_tries_down_from_four(w: World) -> None:
    await standard(w)
    for _ in range(4):
        await w.pin(phone="0799999999", pin_ok=False)


def _check_unknown_lock(obs: Observation) -> None:
    assert [step.tries_left for step in obs.steps] == [4, 3, 2, 1, None]
    assert [step.kind for step in obs.steps] == ["refused"] * 4 + ["pin_locked"]


@case("pin_locked", "unknown_number", check=_check_unknown_lock)
async def pin_of_an_unknown_number_is_locked_on_the_fifth_try(w: World) -> None:
    await standard(w)
    for _ in range(5):
        await w.pin(phone="0799999999", pin_ok=False)


@case("pin_locked", "unknown_number", check=lambda o: _expect(len(o.steps) == 8))
async def pin_of_an_unknown_number_stays_locked_past_the_fifth_try(w: World) -> None:
    await standard(w)
    for _ in range(8):
        await w.pin(phone="0799999999", pin_ok=False)


@case("refused", "unknown_number", check=lambda o: _expect(o.last.tries_left == 1))
async def pin_of_an_unknown_number_counts_the_released_routes_tries_too(w: World) -> None:
    await standard(w)
    for _ in range(3):
        await w.lookup("0799999999")
    await w.pin(phone="0799999999", pin_ok=False)


@case("refused", "unknown_number", check=lambda o: _expect(o.last.tries_left == 4))
async def pin_of_a_non_normalising_number_counts_down_as_well(w: World) -> None:
    await standard(w)
    await w.pin(phone="12345", pin_ok=False)


@case("blocked", "inactive", check=lambda o: _expect(o.account.failed_attempts == 0))
async def pin_of_a_removed_account_is_blocked_and_counts_nothing(w: World) -> None:
    await standard(w, status="removed")
    await w.pin(pin_ok=False)


@case("blocked", "inactive", check=_check_no_code_stored)
async def pin_without_a_membership_is_blocked(w: World) -> None:
    await standard(w, membership=False)
    await w.pin()


@case("blocked", "inactive", check=_check_no_code_stored)
async def pin_is_blocked_before_a_forced_reset_is_looked_at(w: World) -> None:
    ref = await standard(w, status="removed")
    await w.set_user(ref, pin_reset_required=True)
    await w.pin()


@case("verification_required", check=_check_setup_code("first_setup"))
async def pin_of_an_account_without_a_pin_issues_a_first_setup_code(w: World) -> None:
    await standard(w, pin=False)
    await w.pin(pin_ok=False, checked_pin_hash=None)


@case("verification_required", check=_check_setup_code("pin_reset"))
async def pin_during_a_forced_reset_issues_a_pin_reset_code_without_looking_at_the_pin(
    w: World,
) -> None:
    ref = await standard(w)
    await w.set_user(ref, pin_reset_required=True, failed_attempts=5)
    await w.pin(pin_ok=False, checked_pin_hash=None)


@case("verification_required", check=_check_no_code)
async def pin_without_a_pin_inside_the_cooldown_issues_no_code(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, OTHER, created_at=T0 - timedelta(seconds=30))
    await w.pin(pin_ok=False, checked_pin_hash=None)


def _check_pin_locked_counts_nothing(obs: Observation) -> None:
    account = obs.account
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (5, 2)
    assert account.codes == () and account.tokens_total == 0


@case("pin_locked", "locked", check=_check_pin_locked_counts_nothing)
async def pin_locked_on_every_device_counts_nothing_for_a_wrong_pin(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=2)
    await w.pin(device=TRUSTED, token=TOKEN, pin_ok=False)


@case("pin_locked", "locked", check=_check_pin_locked_counts_nothing)
async def pin_locked_on_every_device_refuses_a_right_pin_on_a_trusted_device(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=2)
    await w.pin(device=TRUSTED, token=TOKEN)


@case("pin_locked", "locked", check=_check_pin_locked_counts_nothing)
async def pin_locked_on_every_device_refuses_a_right_pin_on_an_untrusted_device(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=2)
    await w.pin()


def _check_new_device_lock_kept(obs: Observation) -> None:
    account = obs.account
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (0, 5)
    assert account.codes == ()


@case("pin_locked", "locked", check=_check_new_device_lock_kept)
async def pin_locked_for_new_devices_counts_nothing_on_an_untrusted_device(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, untrusted_failed_attempts=5)
    await w.pin(pin_ok=False)


@case("pin_locked", "locked", check=_check_new_device_lock_kept)
async def pin_locked_for_new_devices_refuses_a_right_pin_on_an_untrusted_device(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, untrusted_failed_attempts=5)
    await w.pin()


@case("authenticated", check=lambda o: _expect(o.account.untrusted_failed_attempts == 5))
async def pin_locked_for_new_devices_lets_a_token_trusted_device_sign_in(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, untrusted_failed_attempts=5)
    await w.pin(device=TRUSTED, token=TOKEN)


def _check_token_sign_in(obs: Observation) -> None:
    step, account = obs.last, obs.account
    assert (step.role, step.first_name, step.last_name) == ("Owner", "Jane", "Doe")
    assert (step.user, step.organization_matches) == ("account0", True)
    assert step.device_token_issued is None
    assert account.live_tokens == ((TRUSTED, 1),)
    assert account.last_signed_in_at == T0
    assert account.device(TRUSTED) == row(TRUSTED, token=TOKEN, used=T0)
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (0, 4)


@case("authenticated", check=_check_token_sign_in)
async def pin_right_on_a_token_trusted_device_signs_in_and_clears_only_its_scope(
    w: World,
) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, token=TOKEN, last_used_at=T0 - 5 * DAY)
    await w.set_user(ref, failed_attempts=3, untrusted_failed_attempts=4)
    await w.pin(device=TRUSTED, token=TOKEN)


def _check_new_device_code_by_pin(device: str) -> Callable[[Observation], None]:
    def check(obs: Observation) -> None:
        step, account = obs.last, obs.account
        assert step.purpose == "new_device" and step.masked_email == "j***@example.com"
        assert (step.code_issued, step.code_id_set, step.email) == (True, True, EMAIL)
        assert account.codes == (_code_row(T0, "new_device", device, False, 0, T0 + 10 * MINUTE),)
        assert account.live_tokens == () and account.last_signed_in_at is None
        assert (account.failed_attempts, account.untrusted_failed_attempts) == (2, 3)

    return check


@case("verification_required", check=_check_new_device_code_by_pin(UNTRUSTED))
async def pin_right_on_an_untrusted_device_issues_a_new_device_code(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, failed_attempts=2, untrusted_failed_attempts=3)
    await w.pin()


@case("verification_required", check=_check_new_device_code_by_pin(TRUSTED))
async def pin_right_on_a_tokened_device_without_its_token_asks_for_a_code(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, failed_attempts=2, untrusted_failed_attempts=3)
    await w.pin(device=TRUSTED, token=None)


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def pin_right_on_a_legacy_device_row_asks_for_a_code_on_the_new_route(w: World) -> None:
    await standard(w)
    await w.pin(device=TRUSTED, token=TOKEN)


@case("verification_required", check=_check_no_code)
async def pin_right_on_an_untrusted_device_inside_the_cooldown_issues_no_code(w: World) -> None:
    ref = await tokened(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, OTHER, created_at=T0 - timedelta(seconds=30))
    await w.pin()


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def pin_right_on_an_untrusted_device_can_skip_the_cooldown(w: World) -> None:
    ref = await tokened(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, OTHER, created_at=T0 - timedelta(seconds=30))
    await w.pin(skip_cooldown=True)


def _check_trusted_wrong_pin(obs: Observation) -> None:
    account = obs.account
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (1, 0)
    assert obs.last.tries_left == 4
    assert account.tokens_total == 0 and account.last_signed_in_at is None


@case("refused", "wrong_pin", check=_check_trusted_wrong_pin)
async def pin_wrong_on_a_token_trusted_device_counts_in_the_trusted_scope(w: World) -> None:
    await tokened(w)
    await w.pin(device=TRUSTED, token=TOKEN, pin_ok=False)


@case("refused", "wrong_pin", check=_check_trusted_wrong_pin)
async def pin_a_verdict_on_a_replaced_hash_is_a_wrong_pin(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, pin_hash=NEW_PIN_HASH)
    await w.pin(device=TRUSTED, token=TOKEN, pin_ok=True, checked_pin_hash=PIN_HASH)


def _check_trusted_countdown(obs: Observation) -> None:
    assert [step.tries_left for step in obs.steps] == [4, 3, 2, 1]
    assert obs.account.failed_attempts == 4


@case("refused", "wrong_pin", check=_check_trusted_countdown)
async def pin_wrong_on_a_trusted_device_counts_the_tries_down(w: World) -> None:
    await tokened(w)
    for _ in range(4):
        await w.pin(device=TRUSTED, token=TOKEN, pin_ok=False)


def _check_fifth_trusted_wrong_pin(obs: Observation) -> None:
    account = obs.account
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (5, 0)
    assert obs.last.tries_left is None and obs.last.retry_after_seconds is None


@case("pin_locked", "wrong_pin", check=_check_fifth_trusted_wrong_pin)
async def pin_the_fifth_wrong_pin_on_a_trusted_device_locks_every_device(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, failed_attempts=4)
    await w.pin(device=TRUSTED, token=TOKEN, pin_ok=False)


@case("pin_locked", "locked", check=lambda o: _expect(o.account.failed_attempts == 5))
async def pin_after_the_fifth_wrong_pin_a_right_pin_is_locked_out(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, failed_attempts=4)
    await w.pin(device=TRUSTED, token=TOKEN, pin_ok=False)
    await w.pin(device=TRUSTED, token=TOKEN)


def _check_untrusted_wrong_pin_by_pin(obs: Observation) -> None:
    account = obs.account
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (0, 1)
    assert obs.last.tries_left == 4


@case("refused", "wrong_pin", check=_check_untrusted_wrong_pin_by_pin)
async def pin_wrong_on_an_untrusted_device_counts_in_the_new_device_scope(w: World) -> None:
    await tokened(w)
    await w.pin(pin_ok=False)


@case(
    "pin_locked",
    "wrong_pin",
    check=lambda o: _expect(
        (o.account.failed_attempts, o.account.untrusted_failed_attempts) == (0, 5)
    ),
)
async def pin_the_fifth_wrong_pin_on_an_untrusted_device_locks_new_devices(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, untrusted_failed_attempts=4)
    await w.pin(pin_ok=False)


@case("authenticated", check=lambda o: _expect(o.account.untrusted_failed_attempts == 5))
async def pin_five_untrusted_wrong_pins_leave_a_token_trusted_device_open(w: World) -> None:
    await tokened(w)
    for _ in range(5):
        await w.pin(pin_ok=False)
    await w.pin(device=TRUSTED, token=TOKEN)


@case(
    "refused",
    "wrong_pin",
    check=lambda o: _expect(
        o.last.tries_left == 2
        and (o.account.failed_attempts, o.account.untrusted_failed_attempts) == (4, 3)
    ),
)
async def pin_the_scopes_count_separately(w: World) -> None:
    ref = await tokened(w)
    await w.set_user(ref, failed_attempts=4, untrusted_failed_attempts=2)
    await w.pin(pin_ok=False)


# --- 3.1 statement two: sign-in, step by step -----------------------------------------------


@case("refused", "unknown_number")
async def sign_in_without_an_account_is_refused(w: World) -> None:
    await w.sign_in(None)


@case("refused", "inactive")
async def sign_in_of_a_removed_account_is_refused(w: World) -> None:
    ref = await standard(w, status="removed")
    await w.sign_in(ref)


@case("refused", "no_pin")
async def sign_in_of_an_account_without_a_pin_is_refused(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.sign_in(ref)


def _check_reset_pending_counts_nothing(obs: Observation) -> None:
    account = obs.account
    assert account.failed_attempts == 2 and account.pin_reset_required
    assert account.tokens_total == 0 and account.codes == ()


@case("refused", "reset_required", check=_check_reset_pending_counts_nothing)
async def sign_in_with_a_forced_reset_pending_is_refused_and_counts_nothing(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, pin_reset_required=True, failed_attempts=2)
    await w.sign_in(ref, pin_ok=False)


@case("refused", "reset_required", check=_check_reset_pending_counts_nothing)
async def sign_in_with_a_forced_reset_pending_refuses_a_right_pin_too(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, pin_reset_required=True, failed_attempts=2)
    await w.sign_in(ref)


def _check_trusted_sign_in(obs: Observation) -> None:
    step, account = obs.last, obs.account
    assert step.permissions == role_permissions("Owner")
    assert (step.role, step.first_name, step.last_name) == ("Owner", "Jane", "Doe")
    assert (step.security_version, step.access_token_minutes) == (0, 10)
    assert step.refresh_expires_at == LATER
    assert (step.user, step.organization_matches) == ("account0", True)
    assert account.live_tokens == ((TRUSTED, 1),)
    assert account.last_signed_in_at == T0


@case("authenticated", check=_check_trusted_sign_in)
async def step_9_right_pin_on_a_trusted_device_issues_tokens(w: World) -> None:
    ref = await standard(w)
    await w.sign_in(ref)


def _check_sign_in_marks_use(obs: Observation) -> None:
    account = obs.account
    assert account.last_signed_in_at == T0
    assert account.device(TRUSTED) == row(TRUSTED, used=T0)


@case("authenticated", check=_check_sign_in_marks_use)
async def step_9_a_sign_in_marks_the_device_used_and_the_person_signed_in(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, last_used_at=T0 - 5 * DAY)
    await w.sign_in(ref)


def _check_counters_after_trusted_sign_in(obs: Observation) -> None:
    account = obs.account
    assert account.failed_attempts == 0
    assert account.untrusted_failed_attempts == 4


@case("authenticated", check=_check_counters_after_trusted_sign_in)
async def step_9_clears_the_trusted_counter_and_keeps_the_untrusted_one(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=3, untrusted_failed_attempts=4)
    await w.sign_in(ref)


def _check_one_wrong_try(obs: Observation) -> None:
    account = obs.account
    assert account.failed_attempts == 1
    assert account.tokens_total == 0 and account.last_signed_in_at is None


@case("refused", "wrong_pin", check=_check_one_wrong_try)
async def step_6_a_verdict_on_a_hash_replaced_since_the_lookup_is_a_wrong_pin(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, pin_hash=NEW_PIN_HASH)
    await w.sign_in(ref, checked_pin_hash=PIN_HASH)


@case("refused", "wrong_pin", check=_check_one_wrong_try)
async def step_6_a_wrong_pin_on_a_trusted_device_is_counted(w: World) -> None:
    ref = await standard(w)
    await w.sign_in(ref, pin_ok=False)


@case("refused", "wrong_pin", check=_check_one_wrong_try)
async def step_6_a_verdict_checked_against_no_hash_is_a_wrong_pin(w: World) -> None:
    ref = await standard(w)
    await w.sign_in(ref, checked_pin_hash=None)


def _check_locked_everywhere(seconds: int | None) -> Callable[[Observation], None]:
    def check(obs: Observation) -> None:
        account = obs.account
        assert obs.last.retry_after_seconds == seconds
        assert (account.failed_attempts, account.untrusted_failed_attempts) == (5, 2)
        assert account.tokens_total == 0 and account.codes == ()

    return check


@case("paused", "locked", check=_check_locked_everywhere(120))
async def locked_on_every_device_a_trusted_device_shows_the_policy_pause(w: World) -> None:
    ref = await standard(w)
    await w.set_policy(ref, lockout_minutes=2)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=2)
    await w.sign_in(ref)


@case("paused", "locked", check=_check_locked_everywhere(900))
async def locked_on_every_device_a_trusted_device_without_a_membership_shows_the_default_pause(
    w: World,
) -> None:
    ref = await standard(w, membership=False)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=2)
    await w.sign_in(ref)


@case("paused", "locked", check=_check_locked_everywhere(900))
async def locked_on_every_device_a_wrong_pin_moves_no_counter(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=2)
    await w.sign_in(ref, pin_ok=False)


@case("paused", "locked", check=_check_locked_everywhere(900))
async def locked_on_every_device_the_lock_does_not_lapse_with_time(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, last_used_at=T0 + 59 * DAY)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=2)
    await w.sign_in(ref, now=T0 + 60 * DAY)


@case("refused", "locked", check=_check_locked_everywhere(None))
async def locked_on_every_device_an_untrusted_device_is_refused_with_the_right_pin(
    w: World,
) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=2)
    await w.sign_in(ref, device=UNTRUSTED)


@case("refused", "locked", check=_check_locked_everywhere(None))
async def locked_on_every_device_an_untrusted_device_is_refused_with_a_wrong_pin(
    w: World,
) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=2)
    await w.sign_in(ref, device=UNTRUSTED, pin_ok=False)


def _check_new_device_lock_untouched(obs: Observation) -> None:
    assert obs.account.untrusted_failed_attempts == 5
    assert obs.account.codes == ()


@case("refused", "locked", check=_check_new_device_lock_untouched)
async def locked_for_new_devices_an_untrusted_device_is_refused_with_the_right_pin(
    w: World,
) -> None:
    ref = await standard(w)
    await w.set_user(ref, untrusted_failed_attempts=5)
    await w.sign_in(ref, device=UNTRUSTED)


@case("refused", "locked", check=_check_new_device_lock_untouched)
async def locked_for_new_devices_an_untrusted_device_is_refused_with_a_wrong_pin(
    w: World,
) -> None:
    ref = await standard(w)
    await w.set_user(ref, untrusted_failed_attempts=5)
    await w.sign_in(ref, device=UNTRUSTED, pin_ok=False)


@case("authenticated", check=lambda o: _expect(o.account.untrusted_failed_attempts == 5))
async def locked_for_new_devices_a_trusted_device_signs_in_and_keeps_the_count(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, untrusted_failed_attempts=5)
    await w.sign_in(ref, device=TRUSTED)


@case(
    "refused",
    "wrong_pin",
    check=lambda o: _expect(
        (o.account.failed_attempts, o.account.untrusted_failed_attempts) == (1, 5)
    ),
)
async def locked_for_new_devices_a_wrong_pin_on_a_trusted_device_counts_in_its_own_scope(
    w: World,
) -> None:
    ref = await standard(w)
    await w.set_user(ref, untrusted_failed_attempts=5)
    await w.sign_in(ref, device=TRUSTED, pin_ok=False)


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def step_4_an_expired_trust_is_untrusted(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, "expired-device", expires_at=lapsed())
    await w.sign_in(ref, device="expired-device")


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def step_4_trust_ending_exactly_now_is_untrusted(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, "ending-device", expires_at=T0)
    await w.sign_in(ref, device="ending-device")


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def step_4_a_revoked_device_is_untrusted(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, "revoked-device", revoked=True)
    await w.sign_in(ref, device="revoked-device")


@case("authenticated")
async def step_4_trust_lasting_beyond_now_is_trusted(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, "lasting-device", expires_at=T0 + timedelta(seconds=1))
    await w.sign_in(ref, device="lasting-device")


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def step_4_a_device_unused_for_90_days_is_untrusted(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, last_used_at=T0 - 90 * DAY)
    await w.sign_in(ref)


@case("authenticated")
async def step_4_a_device_used_just_inside_90_days_is_trusted(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, last_used_at=T0 - 90 * DAY + timedelta(seconds=1))
    await w.sign_in(ref)


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def step_4_a_session_only_device_is_untrusted(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, remembered=False)
    await w.sign_in(ref)


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def step_4_a_device_holding_a_token_is_not_trusted_by_its_id_alone(w: World) -> None:
    ref = await tokened(w)
    await w.sign_in(ref)


def _check_fifth_wrong_pin_pause(obs: Observation) -> None:
    account = obs.account
    assert obs.last.retry_after_seconds == 900
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (5, 0)


@case("paused", "wrong_pin", check=_check_fifth_wrong_pin_pause)
async def step_6_the_fifth_wrong_pin_on_a_trusted_device_answers_paused(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=4)
    await w.sign_in(ref, pin_ok=False)


def _check_five_wrong_pins(obs: Observation) -> None:
    assert [step.kind for step in obs.steps] == ["refused"] * 4 + ["paused"] + ["paused"]
    assert [step.refusal for step in obs.steps][-2:] == ["wrong_pin", "locked"]
    assert obs.account.failed_attempts == 5 and obs.account.tokens_total == 0


@case("paused", "locked", check=_check_five_wrong_pins)
async def step_6_after_five_wrong_pins_a_right_pin_is_still_paused(w: World) -> None:
    ref = await standard(w)
    for _ in range(5):
        await w.sign_in(ref, pin_ok=False)
    await w.sign_in(ref)


@case(
    "paused",
    "wrong_pin",
    check=lambda o: _expect(o.last.retry_after_seconds == 120 and o.account.failed_attempts == 5),
)
async def step_6_the_policy_minutes_set_the_pause_and_the_threshold_is_not_read(w: World) -> None:
    ref = await standard(w)
    await w.set_policy(ref, lockout_threshold=7, lockout_minutes=2)
    await w.set_user(ref, failed_attempts=4)
    await w.sign_in(ref, pin_ok=False)


@case("refused", "wrong_pin", check=lambda o: _expect(o.account.failed_attempts == 3))
async def step_6_a_lower_policy_threshold_does_not_lock_earlier(w: World) -> None:
    ref = await standard(w)
    await w.set_policy(ref, lockout_threshold=3)
    for _ in range(3):
        await w.sign_in(ref, pin_ok=False)


@case("paused", "wrong_pin", check=_check_fifth_wrong_pin_pause)
async def step_6_without_a_membership_the_fifth_wrong_pin_answers_the_default_pause(
    w: World,
) -> None:
    ref = await standard(w, membership=False)
    await w.set_user(ref, failed_attempts=4)
    await w.sign_in(ref, pin_ok=False)


def _check_untrusted_wrong_pin(obs: Observation) -> None:
    assert (obs.account.failed_attempts, obs.account.untrusted_failed_attempts) == (0, 1)


@case("refused", "wrong_pin", check=_check_untrusted_wrong_pin)
async def step_7_a_wrong_pin_on_an_untrusted_device_counts_toward_the_new_device_lock(
    w: World,
) -> None:
    ref = await standard(w)
    await w.sign_in(ref, device=UNTRUSTED, pin_ok=False)


@case(
    "refused",
    "wrong_pin",
    check=lambda o: _expect(
        (o.account.failed_attempts, o.account.untrusted_failed_attempts) == (0, 5)
    ),
)
async def step_7_the_fifth_untrusted_wrong_pin_locks_new_devices_and_answers_refused(
    w: World,
) -> None:
    ref = await standard(w)
    await w.set_user(ref, untrusted_failed_attempts=4)
    await w.sign_in(ref, device=UNTRUSTED, pin_ok=False)


@case("authenticated", check=lambda o: _expect(o.account.untrusted_failed_attempts == 5))
async def step_7_five_untrusted_wrong_pins_leave_a_trusted_device_open(w: World) -> None:
    ref = await standard(w)
    for _ in range(5):
        await w.sign_in(ref, device=UNTRUSTED, pin_ok=False)
    await w.sign_in(ref, device=TRUSTED)


@case(
    "paused",
    "wrong_pin",
    check=lambda o: _expect(
        (o.account.failed_attempts, o.account.untrusted_failed_attempts) == (5, 1)
    ),
)
async def step_7_the_two_scopes_count_separately(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=4)
    await w.sign_in(ref, device=UNTRUSTED, pin_ok=False)
    await w.sign_in(ref, device=TRUSTED, pin_ok=False)


def _check_new_device_code(obs: Observation) -> None:
    step = obs.last
    assert step.masked_email == "j***@example.com"
    assert (step.code_issued, step.code_id_set, step.email) == (True, True, EMAIL)
    assert obs.account.codes == (
        _code_row(T0, "new_device", UNTRUSTED, False, 0, T0 + 10 * MINUTE),
    )
    assert obs.account.live_tokens == ()


@case("verification_required", check=_check_new_device_code)
async def step_8_the_right_pin_on_an_untrusted_device_issues_a_new_device_code(w: World) -> None:
    ref = await standard(w)
    await w.sign_in(ref, device=UNTRUSTED)


@case(
    "verification_required",
    check=lambda o: _expect(
        (
            o.account.failed_attempts,
            o.account.untrusted_failed_attempts,
            o.account.last_signed_in_at,
        )
        == (2, 3, None)
    ),
)
async def step_8_asking_for_a_code_moves_no_counter(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=2, untrusted_failed_attempts=3)
    await w.sign_in(ref, device=UNTRUSTED)


@case(
    "verification_required",
    check=lambda o: _expect(o.last.masked_email == "a***@example.co.ke"),
)
async def step_8_the_masked_address_keeps_the_first_character_and_the_domain(w: World) -> None:
    ref = await standard(w, email="a.b@example.co.ke", phone="0722000111")
    await w.sign_in(ref, device=UNTRUSTED)


@case("verification_required", check=_check_no_code)
async def step_8_inside_the_cooldown_no_code_is_issued(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, OTHER, created_at=T0 - timedelta(seconds=30))
    await w.sign_in(ref, device=UNTRUSTED)


@case("verification_required", check=_check_no_code)
async def step_8_the_cooldown_counts_consumed_codes(w: World) -> None:
    ref = await standard(w)
    await w.store_code(
        ref, CodePurpose.NEW_DEVICE, OTHER, created_at=T0 - timedelta(seconds=30), consumed=True
    )
    await w.sign_in(ref, device=UNTRUSTED)


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def step_8_the_cooldown_ignores_withdrawn_codes(w: World) -> None:
    ref = await standard(w)
    await w.store_code(
        ref, CodePurpose.NEW_DEVICE, OTHER, created_at=T0 - timedelta(seconds=10), withdrawn=True
    )
    await w.sign_in(ref, device=UNTRUSTED)


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def step_8_the_cooldown_ends_after_one_minute(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, OTHER, created_at=T0 - MINUTE)
    await w.sign_in(ref, device=UNTRUSTED)


@case("verification_required", check=_check_no_code)
async def step_8_the_cooldown_is_kept_per_person_across_purposes(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, OTHER, created_at=T0 - timedelta(seconds=10))
    await w.sign_in(ref, device=UNTRUSTED)


@case("verification_required", check=_check_skipped_cooldown)
async def step_8_skipping_the_cooldown_issues_a_code_and_supersedes_the_old_one(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, OTHER, created_at=T0 - timedelta(seconds=10))
    await w.sign_in(ref, device=UNTRUSTED, skip_cooldown=True)


def _check_superseded_everywhere(obs: Observation) -> None:
    assert obs.last.code_issued is True
    consumed = {row[2]: row[3] for row in obs.account.codes}
    assert consumed == {OTHER: True, UNTRUSTED: True, THIRD: False}


@case("verification_required", check=_check_superseded_everywhere)
async def step_8_a_new_code_supersedes_older_codes_on_every_device(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, OTHER, created_at=T0 - 5 * MINUTE)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - 4 * MINUTE)
    await w.sign_in(ref, device=THIRD)


@case("verification_required", check=_check_no_code)
async def step_8_five_codes_in_the_last_hour_block_a_sixth(w: World) -> None:
    ref = await standard(w)
    purposes = [CodePurpose.NEW_DEVICE] * 3 + [CodePurpose.PIN_RESET] * 2
    await codes_at(w, ref, purposes, first=5 * MINUTE, step=5 * MINUTE)
    await w.sign_in(ref, device=UNTRUSTED, skip_cooldown=True)


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def step_8_four_codes_in_the_last_hour_still_allow_a_fifth(w: World) -> None:
    ref = await standard(w)
    purposes = [CodePurpose.NEW_DEVICE] * 2 + [CodePurpose.PIN_RESET] * 2
    await codes_at(w, ref, purposes, first=5 * MINUTE, step=5 * MINUTE)
    await w.sign_in(ref, device=UNTRUSTED, skip_cooldown=True)


@case("verification_required", check=_check_no_code)
async def step_8_ten_codes_in_a_day_block_another(w: World) -> None:
    ref = await standard(w)
    recent = [CodePurpose.NEW_DEVICE, CodePurpose.PIN_RESET] * 2
    await codes_at(w, ref, recent, first=10 * MINUTE, step=10 * MINUTE)
    older = [CodePurpose.NEW_DEVICE, CodePurpose.PIN_RESET, CodePurpose.NEW_DEVICE] * 2
    await codes_at(w, ref, older, first=2 * HOUR, step=HOUR)
    await w.sign_in(ref, device=UNTRUSTED, skip_cooldown=True)


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def step_8_codes_older_than_a_day_count_for_nothing(w: World) -> None:
    ref = await standard(w)
    purposes = [CodePurpose.NEW_DEVICE, CodePurpose.PIN_RESET] * 5
    await codes_at(w, ref, purposes, first=DAY + MINUTE, step=MINUTE)
    await w.sign_in(ref, device=UNTRUSTED, skip_cooldown=True)


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def step_8_withdrawn_codes_count_toward_no_cap(w: World) -> None:
    ref = await standard(w)
    purposes = [CodePurpose.NEW_DEVICE] * 6
    await codes_at(w, ref, purposes, first=5 * MINUTE, step=5 * MINUTE, withdrawn=True)
    await w.sign_in(ref, device=UNTRUSTED)


@case("verification_required", check=_check_no_code)
async def step_8_without_a_code_digest_no_code_is_issued(w: World) -> None:
    ref = await standard(w)
    await w.sign_in(ref, device=UNTRUSTED, code_hash=None)


@case("refused", "inactive", check=lambda o: _expect(o.account.codes == ()))
async def step_8_without_a_membership_nothing_is_issued(w: World) -> None:
    ref = await standard(w, membership=False)
    await w.sign_in(ref, device=UNTRUSTED)


@case("refused", "inactive", check=lambda o: _expect(o.account.tokens_total == 0))
async def step_9_without_a_role_nothing_is_issued(w: World) -> None:
    ref = await standard(w, role=None)
    await w.set_user(ref, failed_attempts=2)
    await w.sign_in(ref)


@case("refused", "inactive", check=lambda o: _expect(o.account.failed_attempts == 2))
async def step_9_without_a_membership_the_counters_stay(w: World) -> None:
    ref = await standard(w, membership=False)
    await w.set_user(ref, failed_attempts=2)
    await w.sign_in(ref)


def _check_clerk_claims(obs: Observation) -> None:
    step = obs.last
    assert step.permissions == role_permissions("Revenue clerk")
    assert (step.role, step.first_name, step.last_name) == ("Revenue clerk", "Achieng", "Otieno")
    assert (step.security_version, step.access_token_minutes) == (4, 7)
    assert step.refresh_expires_at == T0 + timedelta(days=45)


@case("authenticated", check=_check_clerk_claims)
async def step_9_the_claims_follow_the_role_names_and_policy(w: World) -> None:
    ref = await standard(w, role="Revenue clerk", first_name="Achieng", last_name="Otieno")
    await w.set_policy(ref, access_token_minutes=7, refresh_token_days=45)
    await w.set_user(ref, security_version=4)
    await w.sign_in(ref)


# --- 3.2 verify-device ----------------------------------------------------------------------


@case("refused", "unknown_number")
async def verify_device_of_an_unknown_number_is_refused(w: World) -> None:
    await standard(w)
    await w.verify_device(phone="0799999999")


@case("refused", "unknown_number")
async def verify_device_of_a_non_normalising_number_is_refused(w: World) -> None:
    await standard(w)
    await w.verify_device(phone="12345")


@case("refused", "inactive")
async def verify_device_of_a_removed_account_is_refused(w: World) -> None:
    ref = await standard(w, status="removed")
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.verify_device()


@case("refused", "no_pin")
async def verify_device_of_an_account_without_a_pin_is_refused(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.verify_device()


@case(
    "refused",
    "reset_required",
    check=lambda o: _expect(o.account.codes[0][3:5] == (False, 0) and o.account.tokens_total == 0),
)
async def verify_device_with_a_forced_reset_pending_is_refused_and_keeps_the_code(
    w: World,
) -> None:
    ref = await standard(w)
    await w.set_user(ref, pin_reset_required=True)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.verify_device()


@case("refused", "code_expired")
async def verify_device_without_a_code_is_refused(w: World) -> None:
    await standard(w)
    await w.verify_device()


@case(
    "refused",
    "wrong_code",
    check=lambda o: _expect(
        o.account.codes[0][4] == 1 and o.last.code_issued is None and o.last.purpose is None
    ),
)
async def verify_device_counts_a_wrong_code(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.verify_device(code_hash=WRONG_CODE_HASH)


def _check_voided_and_replaced(purpose: str) -> Callable[[Observation], None]:
    def check(obs: Observation) -> None:
        step = obs.last
        assert (step.refusal, step.purpose, step.tries_left) == ("wrong_code", purpose, None)
        assert (step.code_issued, step.code_id_set, step.email) == (True, True, EMAIL)
        assert obs.account.codes == (
            _code_row(T0, purpose, UNTRUSTED, False, 0, T0 + 10 * MINUTE),
            _code_row(T0, purpose, UNTRUSTED, True, 3, T0 + 10 * MINUTE),
        )

    return check


@case("refused", "wrong_code", check=_check_voided_and_replaced("new_device"))
async def verify_device_voids_a_code_on_the_third_wrong_try_and_issues_a_replacement(
    w: World,
) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, failed_attempts=2)
    await w.verify_device(code_hash=WRONG_CODE_HASH)


def _check_replacement_used(obs: Observation) -> None:
    assert [row_[3] for row_ in obs.account.codes] == [True, True]
    assert sorted(row_[4] for row_ in obs.account.codes) == [0, 3]
    assert obs.account.live_tokens == ((UNTRUSTED, 1),)


@case("authenticated", check=_check_replacement_used)
async def verify_device_accepts_the_replacement_after_the_third_wrong_try(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    for _ in range(3):
        await w.verify_device(code_hash=WRONG_CODE_HASH)
    await w.verify_device(code_hash=NEW_CODE_HASH)


def _check_replacement_used_for_a_reset(obs: Observation) -> None:
    assert sorted(c[3:5] for c in obs.account.codes) == [(False, 0), (True, 3)]
    assert obs.last.purpose == "pin_reset"


def _check_replacement_capped(obs: Observation) -> None:
    step = obs.last
    assert (step.refusal, step.purpose, step.code_issued) == ("wrong_code", "new_device", False)
    assert (step.code_id_set, step.email) == (False, None)
    assert len(obs.account.codes) == 5


@case("refused", "wrong_code", check=_check_replacement_capped)
async def verify_device_replacement_past_the_hourly_cap_is_not_issued(w: World) -> None:
    ref = await standard(w)
    await codes_at(w, ref, [CodePurpose.NEW_DEVICE] * 4, first=5 * MINUTE, step=5 * MINUTE)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, failed_attempts=2)
    await w.verify_device(code_hash=WRONG_CODE_HASH)


@case("refused", "code_expired", check=lambda o: _expect(o.account.codes[0][4] == 0))
async def verify_device_refuses_an_expired_code_without_counting(w: World) -> None:
    ref = await standard(w)
    await w.store_code(
        ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - 10 * MINUTE - timedelta(seconds=1)
    )
    await w.verify_device(code_hash=WRONG_CODE_HASH)


@case("authenticated")
async def verify_device_accepts_a_code_at_its_expiry_instant(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - 10 * MINUTE)
    await w.verify_device()


@case("refused", "code_expired", check=lambda o: _expect(o.account.codes[0][3:5] == (False, 3)))
async def verify_device_refuses_a_code_at_three_failures(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, failed_attempts=3)
    await w.verify_device()


@case("refused", "code_expired")
async def verify_device_cannot_use_the_code_of_another_device(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, OTHER)
    await w.verify_device(device=UNTRUSTED)


@case("refused", "code_expired")
async def verify_device_cannot_use_a_code_of_another_purpose(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.verify_device()


@case("refused", "wrong_code", check=lambda o: _expect(o.account.codes[1][4] == 1))
async def verify_device_checks_only_the_newest_code(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - 5 * MINUTE)
    await w.store_code(
        ref,
        CodePurpose.NEW_DEVICE,
        UNTRUSTED,
        code_hash=NEWER_CODE_HASH,
        created_at=T0 - MINUTE,
    )
    await w.verify_device()


def _check_device_verified(obs: Observation) -> None:
    account = obs.account
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (0, 0)
    assert account.device(UNTRUSTED) == row(UNTRUSTED, expires=LATER)
    assert account.device(TRUSTED) == row(TRUSTED)
    assert account.live_tokens == ((UNTRUSTED, 1),)
    assert account.codes[0][3] is True
    assert account.security_version == 0
    assert account.last_signed_in_at == T0
    assert obs.last.refresh_expires_at == LATER


@case("authenticated", check=_check_device_verified)
async def verify_device_trusts_the_device_clears_both_lock_scopes_and_issues_tokens(
    w: World,
) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=5)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.verify_device(trust_days=30)


@case(
    "authenticated",
    check=lambda o: _expect(o.account.device(UNTRUSTED) == row(UNTRUSTED)),
)
async def verify_device_without_trust_days_trusts_without_expiry(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.verify_device(trust_days=None)


@case(
    "authenticated",
    check=lambda o: _expect(o.account.device(UNTRUSTED) == row(UNTRUSTED, expires=T0 + 7 * DAY)),
)
async def verify_device_trusts_a_previously_revoked_device_again(w: World) -> None:
    ref = await standard(w)
    await w.trust(ref, UNTRUSTED, revoked=True)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.verify_device(trust_days=7)


@case(
    "authenticated",
    check=lambda o: _expect(o.account.device(UNTRUSTED) == row(UNTRUSTED, name="Old phone")),
)
async def verify_device_trusts_by_id_dropping_an_earlier_token_and_keeping_the_name(
    w: World,
) -> None:
    ref = await standard(w)
    await w.trust(ref, UNTRUSTED, token="old-token", name="Old phone", last_used_at=T0 - DAY)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.verify_device()


@case(
    "refused",
    "inactive",
    check=lambda o: _expect(o.account.codes[0][3:5] == (False, 0) and o.account.tokens_total == 0),
)
async def verify_device_without_a_membership_is_refused_and_keeps_the_code(w: World) -> None:
    ref = await standard(w, membership=False)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.set_user(ref, failed_attempts=2)
    await w.verify_device()


# --- 3.3 request a code ---------------------------------------------------------------------


def _check_issued_code(purpose: str) -> Callable[[Observation], None]:
    def check(obs: Observation) -> None:
        step = obs.last
        assert (step.code_issued, step.code_id_set, step.email) == (True, True, EMAIL)
        assert step.purpose == purpose
        assert obs.account.codes[-1] == _code_row(
            T0, purpose, UNTRUSTED, False, 0, T0 + 10 * MINUTE
        )

    return check


@case("check_email", check=_check_issued_code("first_setup"))
async def request_code_issues_a_first_setup_code(w: World) -> None:
    await standard(w, pin=False)
    await w.request_code(CodePurpose.FIRST_SETUP)


@case("check_email", check=_check_issued_code("pin_reset"))
async def request_code_issues_a_pin_reset_code(w: World) -> None:
    await standard(w)
    await w.request_code(CodePurpose.PIN_RESET)


@case("silent", "unknown_number")
async def request_code_for_an_unknown_number_is_silent(w: World) -> None:
    await standard(w)
    await w.request_code(CodePurpose.PIN_RESET, phone="0799999999")


@case("silent", "unknown_number")
async def request_code_for_a_non_normalising_number_is_silent(w: World) -> None:
    await standard(w)
    await w.request_code(CodePurpose.PIN_RESET, phone="12345")


@case("silent", "inactive", check=lambda o: _expect(o.account.codes == ()))
async def request_code_for_a_removed_account_is_silent(w: World) -> None:
    await standard(w, status="removed", pin=False)
    await w.request_code(CodePurpose.FIRST_SETUP)


@case("silent", "no_pin")
async def request_code_for_a_reset_without_a_pin_is_silent(w: World) -> None:
    await standard(w, pin=False)
    await w.request_code(CodePurpose.PIN_RESET)


@case("silent", check=lambda o: _expect(o.last.refusal is None and o.account.codes == ()))
async def request_code_for_a_first_setup_with_a_pin_is_silent(w: World) -> None:
    await standard(w)
    await w.request_code(CodePurpose.FIRST_SETUP)


@case("silent", check=lambda o: _expect(o.account.codes == ()))
async def request_code_for_the_new_device_purpose_is_silent(w: World) -> None:
    await standard(w)
    await w.request_code(CodePurpose.NEW_DEVICE)


@case("silent", check=lambda o: _expect(len(o.account.codes) == 1))
async def request_code_inside_the_cooldown_is_silent(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, OTHER, created_at=T0 - timedelta(seconds=30))
    await w.request_code(CodePurpose.PIN_RESET)


@case("check_email", check=lambda o: _expect([c[3] for c in o.account.codes] == [True, False]))
async def request_code_can_skip_the_cooldown(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, OTHER, created_at=T0 - timedelta(seconds=30))
    await w.request_code(CodePurpose.PIN_RESET, skip_cooldown=True)


@case("silent", check=lambda o: _expect(len(o.account.codes) == 1))
async def request_code_has_a_cooldown_per_person_across_purposes(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, OTHER, created_at=T0 - timedelta(seconds=10))
    await w.request_code(CodePurpose.PIN_RESET)


def _check_reset_supersedes(obs: Observation) -> None:
    by_device = {row_[2]: row_ for row_ in obs.account.codes}
    assert by_device[OTHER][3] and by_device[THIRD][3]
    assert by_device[OTHER][5] == 600 and by_device[THIRD][5] == 600
    assert by_device[UNTRUSTED][3] is False


@case("check_email", check=_check_reset_supersedes)
async def request_code_supersedes_older_codes_of_the_purpose_on_every_device(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, OTHER, created_at=T0 - 5 * MINUTE)
    await w.store_code(ref, CodePurpose.PIN_RESET, THIRD, created_at=T0 - 4 * MINUTE)
    await w.request_code(CodePurpose.PIN_RESET)


@case("check_email", check=lambda o: _expect(o.account.codes[0][3] is False))
async def request_code_leaves_codes_of_other_purposes_alone(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, OTHER, created_at=T0 - 5 * MINUTE)
    await w.request_code(CodePurpose.PIN_RESET)


@case("silent", check=lambda o: _expect(len(o.account.codes) == 5))
async def request_code_past_the_hourly_cap_is_silent(w: World) -> None:
    ref = await standard(w)
    purposes = [CodePurpose.NEW_DEVICE, CodePurpose.PIN_RESET] * 2 + [CodePurpose.NEW_DEVICE]
    await codes_at(w, ref, purposes, first=5 * MINUTE, step=5 * MINUTE)
    await w.request_code(CodePurpose.PIN_RESET)


@case("silent", check=lambda o: _expect(len(o.account.codes) == 10))
async def request_code_past_the_daily_cap_is_silent(w: World) -> None:
    ref = await standard(w)
    recent = [CodePurpose.NEW_DEVICE, CodePurpose.PIN_RESET] * 2
    await codes_at(w, ref, recent, first=10 * MINUTE, step=10 * MINUTE)
    older = [CodePurpose.PIN_RESET, CodePurpose.NEW_DEVICE, CodePurpose.PIN_RESET] * 2
    await codes_at(w, ref, older, first=2 * HOUR, step=HOUR)
    await w.request_code(CodePurpose.PIN_RESET)


@case("check_email")
async def request_code_counts_withdrawn_codes_for_nothing(w: World) -> None:
    ref = await standard(w)
    purposes = [CodePurpose.PIN_RESET] * 6
    await codes_at(w, ref, purposes, first=5 * MINUTE, step=5 * MINUTE, withdrawn=True)
    await w.request_code(CodePurpose.PIN_RESET)


@case(
    "check_email",
    check=lambda o: _expect(
        (o.account.failed_attempts, o.account.untrusted_failed_attempts) == (5, 5)
    ),
)
async def request_code_is_allowed_for_a_locked_account(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=5)
    await w.request_code(CodePurpose.PIN_RESET)


@case("check_email", check=lambda o: _expect(o.account.pin_reset_required is True))
async def request_code_is_allowed_with_a_forced_reset_pending_and_keeps_the_flag(
    w: World,
) -> None:
    ref = await standard(w)
    await w.set_user(ref, pin_reset_required=True)
    await w.request_code(CodePurpose.PIN_RESET)


# --- 3.4 verify a code ----------------------------------------------------------------------


@case("refused", "unknown_number")
async def verify_code_of_an_unknown_number_is_refused(w: World) -> None:
    await standard(w)
    await w.verify_code(CodePurpose.PIN_RESET, phone="0799999999")


@case("refused", "inactive")
async def verify_code_of_a_removed_account_is_refused(w: World) -> None:
    ref = await standard(w, status="removed")
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.verify_code(CodePurpose.PIN_RESET)


@case("refused", "no_pin")
async def verify_code_for_a_reset_without_a_pin_is_refused(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.verify_code(CodePurpose.PIN_RESET)


@case("refused", check=lambda o: _expect(o.last.refusal is None and o.account.codes[0][4] == 0))
async def verify_code_for_a_first_setup_with_a_pin_is_refused(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.FIRST_SETUP, UNTRUSTED)
    await w.verify_code(CodePurpose.FIRST_SETUP)


@case("refused", check=lambda o: _expect(o.last.refusal is None))
async def verify_code_for_the_new_device_purpose_is_refused(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.verify_code(CodePurpose.NEW_DEVICE)


@case("code_verified", check=lambda o: _expect(o.account.codes[0][3:5] == (False, 0)))
async def verify_code_keeps_a_matching_code_for_the_completion(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.FIRST_SETUP, UNTRUSTED)
    await w.verify_code(CodePurpose.FIRST_SETUP)


@case("refused", "wrong_code", check=lambda o: _expect(o.account.codes[0][4] == 1))
async def verify_code_counts_a_wrong_code(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.verify_code(CodePurpose.PIN_RESET, code_hash=WRONG_CODE_HASH)


@case("refused", "code_expired")
async def verify_code_without_a_code_is_refused(w: World) -> None:
    await standard(w)
    await w.verify_code(CodePurpose.PIN_RESET)


@case("refused", "code_expired", check=lambda o: _expect(o.account.codes[0][4] == 0))
async def verify_code_refuses_an_expired_code_without_counting(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED, created_at=T0 - 11 * MINUTE)
    await w.verify_code(CodePurpose.PIN_RESET, code_hash=WRONG_CODE_HASH)


@case("code_verified")
async def verify_code_accepts_a_code_at_its_expiry_instant(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED, created_at=T0 - 10 * MINUTE)
    await w.verify_code(CodePurpose.PIN_RESET)


@case("refused", "wrong_code", check=_check_voided_and_replaced("pin_reset"))
async def verify_code_voids_a_code_on_the_third_wrong_try_and_issues_a_replacement(
    w: World,
) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED, failed_attempts=2)
    await w.verify_code(CodePurpose.PIN_RESET, code_hash=WRONG_CODE_HASH)


@case("code_verified", check=_check_replacement_used_for_a_reset)
async def verify_code_accepts_the_replacement_after_the_third_wrong_try(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    for _ in range(3):
        await w.verify_code(CodePurpose.PIN_RESET, code_hash=WRONG_CODE_HASH)
    await w.verify_code(CodePurpose.PIN_RESET, code_hash=NEW_CODE_HASH)


@case("refused", "code_expired", check=lambda o: _expect(o.account.codes[0][3:5] == (False, 3)))
async def verify_code_refuses_a_code_at_three_failures(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED, failed_attempts=3)
    await w.verify_code(CodePurpose.PIN_RESET)


# --- N03 the code step ----------------------------------------------------------------------


def _check_code_verified(purpose: str) -> Callable[[Observation], None]:
    def check(obs: Observation) -> None:
        step, account = obs.last, obs.account
        assert (step.purpose, step.device_token_issued) == (purpose, None)
        assert account.codes[0][3:5] == (False, 0)
        assert account.tokens_total == 0 and account.last_signed_in_at is None

    return check


@case("code_verified", check=_check_code_verified("first_setup"))
async def check_code_keeps_a_first_setup_code_for_the_completion(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.FIRST_SETUP, UNTRUSTED)
    await w.check_code(CodePurpose.FIRST_SETUP)


@case("code_verified", check=_check_code_verified("pin_reset"))
async def check_code_keeps_a_pin_reset_code_for_the_completion(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.check_code(CodePurpose.PIN_RESET)


@case("code_verified", check=_check_code_verified("pin_reset"))
async def check_code_accepts_a_pin_reset_code_during_a_forced_reset(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, pin_reset_required=True)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.check_code(CodePurpose.PIN_RESET)


@case("code_verified")
async def check_code_accepts_a_code_at_its_expiry_instant(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.FIRST_SETUP, UNTRUSTED, created_at=T0 - 10 * MINUTE)
    await w.check_code(CodePurpose.FIRST_SETUP)


def _check_new_device_trusted(obs: Observation) -> None:
    step, account = obs.last, obs.account
    assert step.device_token_issued is True
    assert (step.user, step.role) == ("account0", "Owner")
    assert account.device(UNTRUSTED) == row(UNTRUSTED, expires=LATER, token=ISSUED, name="Pixel 8")
    assert account.device(TRUSTED) == row(TRUSTED)
    assert account.live_tokens == ((UNTRUSTED, 1),)
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (0, 0)
    assert account.codes[0][3] is True
    assert (account.security_version, account.last_signed_in_at) == (0, T0)


@case("authenticated", check=_check_new_device_trusted)
async def check_code_trusts_a_new_device_with_a_token_and_clears_both_lock_scopes(
    w: World,
) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=5)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.check_code(CodePurpose.NEW_DEVICE, name="Pixel 8", token=ISSUED, trust_days=30)


def _check_new_device_session_only(obs: Observation) -> None:
    step, account = obs.last, obs.account
    assert step.device_token_issued is False
    assert account.device(UNTRUSTED) == row(
        UNTRUSTED, expires=LATER, name="Pixel 8", remembered=False
    )
    assert account.live_tokens == ((UNTRUSTED, 1),)
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (0, 0)


@case("authenticated", check=_check_new_device_session_only)
async def check_code_without_trust_signs_in_for_this_session_only(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=3, untrusted_failed_attempts=5)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.check_code(
        CodePurpose.NEW_DEVICE, name="Pixel 8", trust=False, token=ISSUED, trust_days=30
    )


@case(
    "authenticated",
    check=lambda o: _expect(
        o.account.device(UNTRUSTED) == row(UNTRUSTED, token=ISSUED, name="Old phone")
        and o.last.device_token_issued is True
    ),
)
async def check_code_renews_a_device_row_with_the_new_token_and_keeps_its_name(w: World) -> None:
    ref = await standard(w)
    await w.trust(
        ref, UNTRUSTED, revoked=True, token="old-token", name="Old phone", last_used_at=T0 - DAY
    )
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.check_code(CodePurpose.NEW_DEVICE, token=ISSUED)


@case(
    "authenticated",
    check=lambda o: _expect(
        o.account.device(UNTRUSTED) == row(UNTRUSTED) and o.last.device_token_issued is False
    ),
)
async def check_code_trusting_without_a_token_digest_stores_none_and_issues_none(
    w: World,
) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.check_code(CodePurpose.NEW_DEVICE, token=None)


@case(
    "refused",
    "inactive",
    check=lambda o: _expect(o.account.codes[0][3:5] == (False, 0) and o.account.tokens_total == 0),
)
async def check_code_for_a_new_device_without_a_membership_is_refused_and_keeps_the_code(
    w: World,
) -> None:
    ref = await standard(w, membership=False)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.check_code(CodePurpose.NEW_DEVICE)


@case("refused", "inactive")
async def check_code_of_a_removed_account_is_refused(w: World) -> None:
    ref = await standard(w, status="removed")
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.check_code(CodePurpose.NEW_DEVICE)


@case("refused", "no_pin")
async def check_code_for_a_new_device_without_a_pin_is_refused(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.check_code(CodePurpose.NEW_DEVICE)


@case("refused", "no_pin")
async def check_code_for_a_reset_without_a_pin_is_refused(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.check_code(CodePurpose.PIN_RESET)


@case("refused", "reset_required", check=lambda o: _expect(o.account.codes[0][3:5] == (False, 0)))
async def check_code_for_a_new_device_with_a_forced_reset_pending_is_refused(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, pin_reset_required=True)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.check_code(CodePurpose.NEW_DEVICE)


@case("refused", check=lambda o: _expect(o.last.refusal is None and o.account.codes[0][4] == 0))
async def check_code_for_a_first_setup_with_a_pin_is_refused(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.FIRST_SETUP, UNTRUSTED)
    await w.check_code(CodePurpose.FIRST_SETUP)


@case(
    "refused",
    "wrong_code",
    check=lambda o: _expect(o.last.tries_left == 2 and o.account.codes[0][4] == 1),
)
async def check_code_counts_a_wrong_code_and_says_how_many_tries_are_left(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED)
    await w.check_code(CodePurpose.NEW_DEVICE, code_hash=WRONG_CODE_HASH)


@case(
    "refused",
    "wrong_code",
    check=lambda o: _expect(o.last.tries_left == 1 and o.account.codes[0][4] == 2),
)
async def check_code_says_one_try_is_left_after_the_second_wrong_code(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED, failed_attempts=1)
    await w.check_code(CodePurpose.PIN_RESET, code_hash=WRONG_CODE_HASH)


@case(
    "refused",
    "code_expired",
    check=lambda o: _expect(o.last.tries_left is None and o.account.codes[0][4] == 0),
)
async def check_code_refuses_an_expired_code_without_counting(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - 11 * MINUTE)
    await w.check_code(CodePurpose.NEW_DEVICE, code_hash=WRONG_CODE_HASH)


@case("refused", "code_expired", check=lambda o: _expect(o.last.tries_left is None))
async def check_code_without_a_code_is_refused(w: World) -> None:
    await standard(w)
    await w.check_code(CodePurpose.NEW_DEVICE)


@case("refused", "code_expired", check=lambda o: _expect(o.account.codes[0][3:5] == (False, 3)))
async def check_code_refuses_a_code_at_three_failures(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, failed_attempts=3)
    await w.check_code(CodePurpose.NEW_DEVICE)


def _check_resent(purpose: str, *, issued: bool = True) -> Callable[[Observation], None]:
    def check(obs: Observation) -> None:
        step = obs.last
        assert (step.refusal, step.purpose, step.tries_left) == ("wrong_code", purpose, None)
        assert step.masked_email is None
        assert step.code_issued is issued
        assert (step.code_id_set, step.email) == (issued, EMAIL if issued else None)
        voided = [c for c in obs.account.codes if c[3] and c[4] == 3]
        assert len(voided) == 1
        fresh = [c for c in obs.account.codes if c[0] == T0 and not c[3]]
        assert len(fresh) == (1 if issued else 0)

    return check


@case("code_resent", "wrong_code", check=_check_resent("new_device"))
async def check_code_voids_a_new_device_code_on_the_third_wrong_try_and_resends(
    w: World,
) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, failed_attempts=2)
    await w.check_code(CodePurpose.NEW_DEVICE, code_hash=WRONG_CODE_HASH)


@case("code_resent", "wrong_code", check=_check_resent("pin_reset"))
async def check_code_voids_a_pin_reset_code_on_the_third_wrong_try_and_resends(
    w: World,
) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED, failed_attempts=2)
    await w.check_code(CodePurpose.PIN_RESET, code_hash=WRONG_CODE_HASH)


@case("code_resent", "wrong_code", check=_check_resent("first_setup"))
async def check_code_voids_a_first_setup_code_on_the_third_wrong_try_and_resends(
    w: World,
) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.FIRST_SETUP, UNTRUSTED, failed_attempts=2)
    await w.check_code(CodePurpose.FIRST_SETUP, code_hash=WRONG_CODE_HASH)


@case("code_resent", "wrong_code", check=_check_resent("new_device", issued=False))
async def check_code_resend_past_the_hourly_cap_is_silent(w: World) -> None:
    ref = await standard(w)
    await codes_at(w, ref, [CodePurpose.NEW_DEVICE] * 4, first=5 * MINUTE, step=5 * MINUTE)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, failed_attempts=2)
    await w.check_code(CodePurpose.NEW_DEVICE, code_hash=WRONG_CODE_HASH)


@case("code_resent", "wrong_code", check=_check_resent("new_device"))
async def check_code_resend_skips_the_cooldown(w: World) -> None:
    ref = await standard(w)
    await w.store_code(
        ref,
        CodePurpose.NEW_DEVICE,
        UNTRUSTED,
        created_at=T0 - timedelta(seconds=10),
        failed_attempts=2,
    )
    await w.check_code(CodePurpose.NEW_DEVICE, code_hash=WRONG_CODE_HASH)


@case("code_verified", check=_check_replacement_used_for_a_reset)
async def check_code_accepts_the_replacement_after_the_third_wrong_try(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    for _ in range(3):
        await w.check_code(CodePurpose.PIN_RESET, code_hash=WRONG_CODE_HASH)
    await w.check_code(CodePurpose.PIN_RESET, code_hash=NEW_CODE_HASH)


@case("refused", "wrong_code", check=lambda o: _expect(o.last.tries_left == 2))
async def check_code_counts_again_from_a_replacement(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    for _ in range(4):
        await w.check_code(CodePurpose.PIN_RESET, code_hash=WRONG_CODE_HASH)


UNKNOWN = "0799999999"


async def _wrong_codes(w: World, count: int, *, phone: str = UNKNOWN) -> None:
    for _ in range(count):
        await w.check_code(CodePurpose.PIN_RESET, phone=phone, code_hash=WRONG_CODE_HASH)


@case("refused", "wrong_code", check=lambda o: _expect(o.last.tries_left == 2))
async def check_code_of_an_unknown_number_counts_down_after_a_reset_request(w: World) -> None:
    await standard(w)
    await w.request_code(CodePurpose.PIN_RESET, phone=UNKNOWN)
    await _wrong_codes(w, 1)


@case("refused", "wrong_code", check=lambda o: _expect(o.last.tries_left == 1))
async def check_code_of_an_unknown_number_has_one_try_left_after_two(w: World) -> None:
    await standard(w)
    await w.request_code(CodePurpose.PIN_RESET, phone=UNKNOWN)
    await _wrong_codes(w, 2)


@case(
    "code_resent",
    "wrong_code",
    check=lambda o: _expect(
        (o.last.purpose, o.last.code_issued, o.last.masked_email) == ("pin_reset", None, None)
    ),
)
async def check_code_of_an_unknown_number_resends_on_the_third_wrong_try(w: World) -> None:
    await standard(w)
    await w.request_code(CodePurpose.PIN_RESET, phone=UNKNOWN)
    await _wrong_codes(w, 3)


@case("refused", "wrong_code", check=lambda o: _expect(o.last.tries_left == 2))
async def check_code_of_an_unknown_number_counts_again_after_a_resend(w: World) -> None:
    await standard(w)
    await w.request_code(CodePurpose.PIN_RESET, phone=UNKNOWN)
    await _wrong_codes(w, 4)


@case("refused", "wrong_code", check=lambda o: _expect(o.last.tries_left == 2))
async def check_code_of_an_unknown_number_counts_a_reset_request_made_ten_minutes_ago(
    w: World,
) -> None:
    await standard(w)
    await w.request_code(CodePurpose.PIN_RESET, phone=UNKNOWN, now=T0 - 10 * MINUTE)
    await _wrong_codes(w, 1)


@case("refused", "code_expired", check=lambda o: _expect(o.last.tries_left is None))
async def check_code_of_an_unknown_number_ignores_a_reset_request_older_than_ten_minutes(
    w: World,
) -> None:
    await standard(w)
    await w.request_code(CodePurpose.PIN_RESET, phone=UNKNOWN, now=T0 - 11 * MINUTE)
    await _wrong_codes(w, 1)


@case("refused", "code_expired")
async def check_code_of_an_unknown_number_without_a_reset_request_is_expired(w: World) -> None:
    await standard(w)
    await _wrong_codes(w, 1)


@case("refused", "code_expired")
async def check_code_of_an_unknown_number_after_a_first_setup_request_is_expired(
    w: World,
) -> None:
    await standard(w)
    await w.request_code(CodePurpose.FIRST_SETUP, phone=UNKNOWN)
    await _wrong_codes(w, 1)


@case("refused", "code_expired")
async def check_code_of_an_unknown_number_for_another_purpose_is_expired(w: World) -> None:
    await standard(w)
    await w.request_code(CodePurpose.PIN_RESET, phone=UNKNOWN)
    await w.check_code(CodePurpose.NEW_DEVICE, phone=UNKNOWN, code_hash=WRONG_CODE_HASH)


@case("refused", "wrong_code", check=lambda o: _expect(o.last.tries_left == 2))
async def check_code_of_a_non_normalising_number_counts_down_after_a_reset_request(
    w: World,
) -> None:
    await standard(w)
    await w.request_code(CodePurpose.PIN_RESET, phone="12345")
    await _wrong_codes(w, 1, phone="12345")


# --- N04 send a new code --------------------------------------------------------------------


def _check_resend_issued(purpose: str, *, superseded: int = 0) -> Callable[[Observation], None]:
    def check(obs: Observation) -> None:
        step = obs.last
        assert step.purpose == purpose and step.masked_email is None
        assert (step.code_issued, step.code_id_set, step.email) == (True, True, EMAIL)
        assert obs.account.codes[-1] == _code_row(
            T0, purpose, UNTRUSTED, False, 0, T0 + 10 * MINUTE
        )
        assert sum(1 for c in obs.account.codes if c[3]) == superseded

    return check


def _check_resend_not_issued(codes: int) -> Callable[[Observation], None]:
    def check(obs: Observation) -> None:
        step = obs.last
        assert (step.code_issued, step.code_id_set, step.email) == (False, False, None)
        assert len(obs.account.codes) == codes

    return check


@case("verification_required", check=_check_resend_issued("new_device", superseded=1))
async def resend_code_for_a_new_device_follows_a_recent_code_for_that_device(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - 5 * MINUTE)
    await w.resend_code(CodePurpose.NEW_DEVICE)


@case("verification_required", check=_check_resend_issued("new_device", superseded=2))
async def resend_code_supersedes_the_older_code_of_the_purpose_on_every_device(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - 5 * MINUTE)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, OTHER, created_at=T0 - 4 * MINUTE)
    await w.resend_code(CodePurpose.NEW_DEVICE)


@case("verification_required", check=_check_resend_not_issued(0))
async def resend_code_for_a_new_device_without_a_recent_code_issues_nothing(w: World) -> None:
    await standard(w)
    await w.resend_code(CodePurpose.NEW_DEVICE)


@case("verification_required", check=_check_resend_not_issued(1))
async def resend_code_for_a_new_device_treats_a_ten_minute_old_code_as_not_recent(
    w: World,
) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - 10 * MINUTE)
    await w.resend_code(CodePurpose.NEW_DEVICE)


@case("verification_required", check=_check_resend_issued("new_device", superseded=1))
async def resend_code_for_a_new_device_treats_a_code_just_inside_ten_minutes_as_recent(
    w: World,
) -> None:
    ref = await standard(w)
    await w.store_code(
        ref,
        CodePurpose.NEW_DEVICE,
        UNTRUSTED,
        created_at=T0 - 10 * MINUTE + timedelta(seconds=1),
    )
    await w.resend_code(CodePurpose.NEW_DEVICE)


@case("verification_required", check=_check_resend_not_issued(1))
async def resend_code_for_a_new_device_ignores_the_recent_code_of_another_device(
    w: World,
) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, OTHER, created_at=T0 - 5 * MINUTE)
    await w.resend_code(CodePurpose.NEW_DEVICE)


@case("verification_required", check=_check_resend_issued("new_device", superseded=1))
async def resend_code_for_a_new_device_counts_a_consumed_code_as_recent(w: World) -> None:
    ref = await standard(w)
    await w.store_code(
        ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - 5 * MINUTE, consumed=True
    )
    await w.resend_code(CodePurpose.NEW_DEVICE)


@case("verification_required", check=_check_resend_not_issued(1))
async def resend_code_for_a_new_device_ignores_a_withdrawn_code(w: World) -> None:
    ref = await standard(w)
    await w.store_code(
        ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - 5 * MINUTE, withdrawn=True
    )
    await w.resend_code(CodePurpose.NEW_DEVICE)


@case("verification_required", check=_check_resend_not_issued(1))
async def resend_code_for_a_new_device_inside_the_cooldown_issues_nothing(w: World) -> None:
    ref = await standard(w)
    await w.store_code(
        ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - timedelta(seconds=30)
    )
    await w.resend_code(CodePurpose.NEW_DEVICE)


@case("verification_required", check=_check_resend_issued("new_device", superseded=1))
async def resend_code_can_skip_the_cooldown(w: World) -> None:
    ref = await standard(w)
    await w.store_code(
        ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - timedelta(seconds=30)
    )
    await w.resend_code(CodePurpose.NEW_DEVICE, skip_cooldown=True)


@case("verification_required", check=_check_resend_not_issued(5))
async def resend_code_past_the_hourly_cap_issues_nothing(w: World) -> None:
    ref = await standard(w)
    await codes_at(w, ref, [CodePurpose.NEW_DEVICE] * 4, first=5 * MINUTE, step=5 * MINUTE)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - 5 * MINUTE)
    await w.resend_code(CodePurpose.NEW_DEVICE)


@case("verification_required", check=_check_resend_not_issued(1))
async def resend_code_for_a_new_device_with_a_forced_reset_pending_issues_nothing(
    w: World,
) -> None:
    ref = await standard(w)
    await w.set_user(ref, pin_reset_required=True)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - 5 * MINUTE)
    await w.resend_code(CodePurpose.NEW_DEVICE)


@case("verification_required", check=_check_resend_not_issued(1))
async def resend_code_for_a_new_device_without_a_pin_issues_nothing(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - 5 * MINUTE)
    await w.resend_code(CodePurpose.NEW_DEVICE)


@case("verification_required", check=_check_resend_issued("first_setup"))
async def resend_code_for_a_first_setup_needs_no_earlier_code(w: World) -> None:
    await standard(w, pin=False)
    await w.resend_code(CodePurpose.FIRST_SETUP)


@case("verification_required", check=_check_resend_not_issued(0))
async def resend_code_for_a_first_setup_with_a_pin_issues_nothing(w: World) -> None:
    await standard(w)
    await w.resend_code(CodePurpose.FIRST_SETUP)


@case("verification_required", check=_check_resend_issued("pin_reset"))
async def resend_code_for_a_pin_reset_follows_a_forced_reset(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, pin_reset_required=True)
    await w.resend_code(CodePurpose.PIN_RESET)


@case("verification_required", check=_check_resend_issued("pin_reset", superseded=1))
async def resend_code_for_a_pin_reset_follows_a_recent_reset_code_for_that_device(
    w: World,
) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED, created_at=T0 - 5 * MINUTE)
    await w.resend_code(CodePurpose.PIN_RESET)


@case("verification_required", check=_check_resend_not_issued(1))
async def resend_code_for_a_pin_reset_ignores_the_recent_reset_code_of_another_device(
    w: World,
) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, OTHER, created_at=T0 - 5 * MINUTE)
    await w.resend_code(CodePurpose.PIN_RESET)


@case("verification_required", check=_check_resend_not_issued(1))
async def resend_code_for_a_pin_reset_ignores_a_recent_code_of_another_purpose(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, UNTRUSTED, created_at=T0 - 5 * MINUTE)
    await w.resend_code(CodePurpose.PIN_RESET)


@case("verification_required", check=_check_resend_not_issued(0))
async def resend_code_for_a_pin_reset_with_nothing_pending_issues_nothing(w: World) -> None:
    await standard(w)
    await w.resend_code(CodePurpose.PIN_RESET)


@case("verification_required", check=_check_resend_not_issued(1))
async def resend_code_for_a_pin_reset_without_a_pin_issues_nothing(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED, created_at=T0 - 5 * MINUTE)
    await w.resend_code(CodePurpose.PIN_RESET)


@case("verification_required", check=_check_resend_not_issued(0))
async def resend_code_of_a_removed_account_issues_nothing(w: World) -> None:
    await standard(w, pin=False, status="removed")
    await w.resend_code(CodePurpose.FIRST_SETUP)


@case("verification_required", check=_check_resend_not_issued(0))
async def resend_code_without_a_membership_issues_nothing(w: World) -> None:
    await standard(w, pin=False, membership=False)
    await w.resend_code(CodePurpose.FIRST_SETUP)


@case(
    "verification_required",
    check=lambda o: _expect(
        (o.last.purpose, o.last.code_issued, o.last.code_id_set, o.last.user)
        == ("new_device", None, False, None)
    ),
)
async def resend_code_for_an_unknown_number_answers_alike_without_a_code(w: World) -> None:
    await standard(w)
    await w.resend_code(CodePurpose.NEW_DEVICE, phone=UNKNOWN)


# --- 3.5 complete a PIN ---------------------------------------------------------------------


@case("refused", "unknown_number")
async def complete_pin_of_an_unknown_number_is_refused(w: World) -> None:
    await standard(w)
    await w.complete_pin(CodePurpose.PIN_RESET, phone="0799999999")


@case("refused", "inactive")
async def complete_pin_of_a_removed_account_is_refused(w: World) -> None:
    ref = await standard(w, status="removed")
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.complete_pin(CodePurpose.PIN_RESET)


@case("refused", "no_pin")
async def complete_pin_for_a_reset_without_a_pin_is_refused(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.complete_pin(CodePurpose.PIN_RESET)


@case("refused", check=lambda o: _expect(o.last.refusal is None))
async def complete_pin_for_a_first_setup_with_a_pin_is_refused(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.FIRST_SETUP, UNTRUSTED)
    await w.complete_pin(CodePurpose.FIRST_SETUP)


@case("refused", "wrong_code", check=lambda o: _expect(o.account.codes[0][4] == 1))
async def complete_pin_counts_a_wrong_code(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.complete_pin(CodePurpose.PIN_RESET, code_hash=WRONG_CODE_HASH)


@case(
    "refused",
    "wrong_code",
    check=lambda o: _expect(
        o.account.codes == (_code_row(T0, "pin_reset", UNTRUSTED, True, 3, T0 + 10 * MINUTE),)
        and o.last.code_issued is None
        and o.account.pin_hash == PIN_HASH
    ),
)
async def complete_pin_voids_a_code_on_the_third_wrong_try_without_a_replacement(
    w: World,
) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED, failed_attempts=2)
    await w.complete_pin(CodePurpose.PIN_RESET, code_hash=WRONG_CODE_HASH)


@case("refused", "code_expired")
async def complete_pin_without_a_code_is_refused(w: World) -> None:
    await standard(w)
    await w.complete_pin(CodePurpose.PIN_RESET)


def _check_unchanged_pin(obs: Observation) -> None:
    step, account = obs.last, obs.account
    assert (step.pin_problem, step.minimum_pin_length) == ("unchanged", 4)
    assert account.pin_hash == PIN_HASH
    assert account.codes[0][3:5] == (False, 0)
    assert (account.security_version, account.tokens_total) == (0, 0)
    assert account.failed_attempts == 2 and account.pin_reset_required


@case("invalid_pin", "pin_rule", check=_check_unchanged_pin)
async def complete_pin_to_the_current_pin_is_invalid_and_keeps_the_code(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=2, pin_reset_required=True)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.complete_pin(CodePurpose.PIN_RESET, new_pin_is_current=True)


@case("invalid_pin", "pin_rule", check=_check_unchanged_pin)
async def complete_pin_checks_unchanged_before_the_membership(w: World) -> None:
    ref = await standard(w, membership=False)
    await w.set_user(ref, failed_attempts=2, pin_reset_required=True)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.complete_pin(CodePurpose.PIN_RESET, new_pin_is_current=True)


@case(
    "refused",
    "wrong_code",
    check=lambda o: _expect(o.last.pin_problem is None and o.last.minimum_pin_length is None),
)
async def complete_pin_never_discloses_unchanged_without_a_valid_code(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.complete_pin(CodePurpose.PIN_RESET, code_hash=WRONG_CODE_HASH, new_pin_is_current=True)


def _check_verdict_void(obs: Observation) -> None:
    account = obs.account
    assert account.pin_hash == PIN_HASH
    assert account.codes[0][3:5] == (False, 0)
    assert (account.security_version, account.tokens_total) == (0, 0)
    assert obs.last.pin_problem is None


@case("refused", "verdict_void", check=_check_verdict_void)
async def complete_pin_a_reset_verdict_on_a_replaced_hash_changes_nothing(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.complete_pin(CodePurpose.PIN_RESET, checked_pin_hash=NEW_PIN_HASH)


@case("refused", "verdict_void", check=_check_verdict_void)
async def complete_pin_a_reset_verdict_against_no_hash_changes_nothing(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.complete_pin(CodePurpose.PIN_RESET, checked_pin_hash=None)


@case("refused", "verdict_void", check=_check_verdict_void)
async def complete_pin_checks_the_verdict_hash_before_the_unchanged_verdict(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.complete_pin(
        CodePurpose.PIN_RESET, checked_pin_hash=NEW_PIN_HASH, new_pin_is_current=True
    )


@case("authenticated", check=lambda o: _expect(o.account.pin_hash == NEW_PIN_HASH))
async def complete_pin_a_first_setup_has_nothing_to_be_unchanged_from(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.store_code(ref, CodePurpose.FIRST_SETUP, UNTRUSTED)
    await w.complete_pin(CodePurpose.FIRST_SETUP, new_pin_is_current=True)


@case(
    "refused",
    "inactive",
    check=lambda o: _expect(
        o.account.pin_hash == PIN_HASH
        and o.account.codes[0][3] is False
        and o.account.tokens_total == 0
    ),
)
async def complete_pin_without_a_membership_is_refused_and_changes_nothing(w: World) -> None:
    ref = await standard(w, membership=False)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.complete_pin(CodePurpose.PIN_RESET)


def _check_pin_completed(
    trust_expiry: datetime | None, *, trusted_device_kept: bool
) -> Callable[[Observation], None]:
    def check(obs: Observation) -> None:
        account = obs.account
        assert account.pin_hash == NEW_PIN_HASH
        assert account.security_version == 3 and obs.last.security_version == 3
        assert (account.failed_attempts, account.untrusted_failed_attempts) == (0, 0)
        assert account.pin_reset_required is False
        assert account.last_signed_in_at == T0
        assert account.live_tokens == ((UNTRUSTED, 1),)
        assert all(row_[3] for row_ in account.codes)
        assert account.device(UNTRUSTED) == row(UNTRUSTED, expires=trust_expiry)
        assert account.device(TRUSTED) == row(TRUSTED, revoked=not trusted_device_kept)
        assert obs.last.device_token_issued is False

    return check


async def _arrange_pin_completion(w: World, purpose: CodePurpose, *, pin: bool) -> None:
    ref = await standard(w, pin=pin)
    await w.set_user(
        ref,
        failed_attempts=5,
        untrusted_failed_attempts=5,
        security_version=2,
        pin_reset_required=True,
    )
    await w.store_token(ref, TRUSTED, "t-trusted")
    await w.store_token(ref, OTHER, "t-other")
    await w.store_code(ref, purpose, UNTRUSTED, created_at=T0 - MINUTE)
    await w.store_code(ref, CodePurpose.NEW_DEVICE, OTHER, created_at=T0 - 5 * MINUTE)
    await w.store_code(ref, CodePurpose.PIN_RESET, THIRD, created_at=T0 - 6 * MINUTE)


@case("authenticated", check=_check_pin_completed(LATER, trusted_device_kept=True))
async def complete_pin_sets_the_pin_and_ends_every_session_for_a_first_setup(w: World) -> None:
    await _arrange_pin_completion(w, CodePurpose.FIRST_SETUP, pin=False)
    await w.complete_pin(CodePurpose.FIRST_SETUP, trust_days=30)


@case("authenticated", check=_check_pin_completed(None, trusted_device_kept=False))
async def complete_pin_sets_the_pin_and_ends_every_session_for_a_reset(w: World) -> None:
    await _arrange_pin_completion(w, CodePurpose.PIN_RESET, pin=True)
    await w.complete_pin(CodePurpose.PIN_RESET, trust_days=None)


def _check_reset_removed_every_device(obs: Observation) -> None:
    step, account = obs.last, obs.account
    assert account.device(TRUSTED) == row(TRUSTED, revoked=True)
    assert account.device(OTHER) == row(OTHER, revoked=True, token="old-token", name="Old phone")
    assert account.device(THIRD) == row(THIRD, revoked=True, remembered=False)
    assert account.device(UNTRUSTED) == row(UNTRUSTED, token=ISSUED, name="New phone")
    assert account.live_tokens == ((UNTRUSTED, 1),)
    assert step.device_token_issued is True


@case("authenticated", check=_check_reset_removed_every_device)
async def complete_pin_for_a_reset_removes_every_other_device_and_trusts_the_completing_one(
    w: World,
) -> None:
    ref = await standard(w)
    await w.trust(ref, OTHER, token="old-token", name="Old phone")
    await w.trust(ref, THIRD, remembered=False)
    for device, name in ((TRUSTED, "t1"), (OTHER, "t2"), (THIRD, "t3")):
        await w.store_token(ref, device, name)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.complete_pin(CodePurpose.PIN_RESET, name="New phone", token=ISSUED)


def _check_first_setup_kept_devices(obs: Observation) -> None:
    account = obs.account
    assert account.device(TRUSTED) == row(TRUSTED)
    assert account.device(OTHER) == row(OTHER, token="old-token", name="Old phone")
    assert account.device(UNTRUSTED) == row(UNTRUSTED, token=ISSUED, name="New phone")
    assert account.live_tokens == ((UNTRUSTED, 1),)
    assert obs.last.device_token_issued is True


@case("authenticated", check=_check_first_setup_kept_devices)
async def complete_pin_for_a_first_setup_keeps_the_other_devices_and_ends_their_sessions(
    w: World,
) -> None:
    ref = await standard(w, pin=False)
    await w.trust(ref, OTHER, token="old-token", name="Old phone")
    await w.store_token(ref, TRUSTED, "t1")
    await w.store_token(ref, OTHER, "t2")
    await w.store_code(ref, CodePurpose.FIRST_SETUP, UNTRUSTED)
    await w.complete_pin(CodePurpose.FIRST_SETUP, name="New phone", token=ISSUED)


def _check_completed_for_a_session_only(obs: Observation) -> None:
    account = obs.account
    assert account.device(UNTRUSTED) == row(UNTRUSTED, name="Pixel 8", remembered=False)
    assert account.live_tokens == ((UNTRUSTED, 1),)
    assert obs.last.device_token_issued is False
    assert account.pin_hash == NEW_PIN_HASH


@case("authenticated", check=_check_completed_for_a_session_only)
async def complete_pin_without_trust_signs_in_for_this_session_only(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, UNTRUSTED)
    await w.complete_pin(CodePurpose.PIN_RESET, name="Pixel 8", trust=False, token=ISSUED)


# --- N07 change the PIN ---------------------------------------------------------------------


@case("refused", "unknown_number")
async def change_pin_of_an_unknown_user_is_refused(w: World) -> None:
    await standard(w)
    await w.change_pin(STRANGER)


@case("refused", "inactive", check=lambda o: _expect(o.account.pin_hash == PIN_HASH))
async def change_pin_of_a_removed_account_is_refused(w: World) -> None:
    ref = await standard(w, status="removed")
    await w.change_pin(ref)


@case("refused", "inactive")
async def change_pin_of_an_account_without_a_pin_is_refused(w: World) -> None:
    ref = await standard(w, pin=False)
    await w.change_pin(ref)


def _check_pin_changed(obs: Observation) -> None:
    account = obs.account
    assert account.pin_hash == NEW_PIN_HASH
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (0, 0)
    assert account.security_version == 2 and account.live_tokens == ((TRUSTED, 1),)
    assert account.device(TRUSTED) == row(TRUSTED)
    assert account.last_signed_in_at is None
    step = obs.last
    assert (step.code_issued, step.security_version, step.tries_left) == (None, None, None)


@case("pin_changed", check=_check_pin_changed)
async def change_pin_stores_the_new_hash_clears_both_scopes_and_keeps_sessions(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=3, untrusted_failed_attempts=5, security_version=2)
    await w.store_token(ref, TRUSTED, "t1")
    await w.change_pin(ref)


@case("pin_changed", check=lambda o: _expect(o.account.untrusted_failed_attempts == 0))
async def change_pin_works_while_locked_for_new_devices_only(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, untrusted_failed_attempts=5)
    await w.change_pin(ref)


@case("pin_changed", check=lambda o: _expect(o.account.pin_reset_required is True))
async def change_pin_does_not_clear_a_forced_reset(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, pin_reset_required=True)
    await w.change_pin(ref)


def _check_change_countdown(obs: Observation) -> None:
    assert [step.tries_left for step in obs.steps] == [4, 3, 2, 1]
    account = obs.account
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (4, 0)
    assert account.pin_hash == PIN_HASH


@case("refused", "wrong_pin", check=_check_change_countdown)
async def change_pin_counts_wrong_current_pins_down_in_the_trusted_scope(w: World) -> None:
    ref = await standard(w)
    for _ in range(4):
        await w.change_pin(ref, current_ok=False)


@case(
    "pin_locked",
    "wrong_pin",
    check=lambda o: _expect(
        o.account.failed_attempts == 5
        and o.account.pin_hash == PIN_HASH
        and o.last.tries_left is None
    ),
)
async def change_pin_the_fifth_wrong_current_pin_locks_every_device(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=4)
    await w.change_pin(ref, current_ok=False)


@case(
    "pin_locked",
    "locked",
    check=lambda o: _expect(o.account.failed_attempts == 5 and o.account.pin_hash == PIN_HASH),
)
async def change_pin_locked_on_every_device_refuses_even_a_right_current_pin(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=5)
    await w.change_pin(ref)


@case(
    "refused",
    "wrong_pin",
    check=lambda o: _expect(
        o.last.tries_left == 4
        and o.account.failed_attempts == 1
        and o.account.pin_hash == NEW_PIN_HASH
    ),
)
async def change_pin_a_verdict_on_a_replaced_hash_is_a_wrong_pin(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, pin_hash=NEW_PIN_HASH)
    await w.change_pin(ref, checked_pin_hash=PIN_HASH)


# --- N08 and N09 the person's own devices ---------------------------------------------------


def _check_device_revoked(obs: Observation) -> None:
    account = obs.account
    assert account.device(TRUSTED) == row(TRUSTED, revoked=True)
    assert account.device(OTHER) == row(OTHER)
    assert account.live(TRUSTED) == 0 and account.live(OTHER) == 1
    consumed = {row_[2]: row_[3] for row_ in account.codes}
    assert consumed == {TRUSTED: True, OTHER: False}


@case(
    "devices",
    check=lambda o: _expect(
        o.last.detail
        == (
            (THIRD, "Tablet", T0 - HOUR, T0 - HOUR, False),
            (TRUSTED, "Old phone", T0 - DAY, T0 - DAY, False),
            (OTHER, None, T0 - 2 * DAY, T0 - 2 * DAY, True),
        )
    ),
)
async def device_list_returns_the_live_remembered_rows_newest_use_first(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, name="Old phone", last_used_at=T0 - DAY)
    await w.trust(ref, OTHER, last_used_at=T0 - 2 * DAY)
    await w.trust(ref, THIRD, name="Tablet", last_used_at=T0 - HOUR)
    await w.trust(ref, "revoked-device", revoked=True)
    await w.trust(ref, "session-device", remembered=False)
    await w.trust(ref, "idle-device", last_used_at=T0 - 90 * DAY)
    await w.trust(ref, "ended-device", expires_at=T0)
    await w.device_list(ref, device=OTHER)


@case(
    "devices",
    check=lambda o: _expect(o.last.detail == ((TRUSTED, None, T0, T0, False),)),
)
async def device_list_shows_only_the_callers_own_rows(w: World) -> None:
    ref = await standard(w)
    other = await w.add_account(email="second@example.com", phone="0722000111")
    await w.trust(other, "second-device", name="Second phone")
    await w.device_list(ref, device=UNTRUSTED)


@case("devices", check=lambda o: _expect(o.last.detail == ()))
async def device_list_of_a_person_without_devices_is_empty(w: World) -> None:
    ref = await w.add_account()
    await w.device_list(ref)


@case("devices", check=lambda o: _expect(o.last.detail == ()))
async def device_list_of_an_unknown_user_is_empty(w: World) -> None:
    await standard(w)
    await w.device_list(STRANGER)


@case("device_revoked", check=_check_device_revoked)
async def device_remove_ends_the_row_its_tokens_and_codes(w: World) -> None:
    ref = await standard(w)
    await w.trust(ref, OTHER)
    await w.store_token(ref, TRUSTED, "t1")
    await w.store_token(ref, OTHER, "o1")
    await w.store_code(ref, CodePurpose.PIN_RESET, TRUSTED, created_at=T0 - 5 * MINUTE)
    await w.store_code(ref, CodePurpose.PIN_RESET, OTHER, created_at=T0 - 4 * MINUTE)
    await w.device_remove(ref, await w.row_id(ref, TRUSTED))


@case(
    "device_revoked",
    check=lambda o: _expect(
        o.account.device(TRUSTED) == row(TRUSTED, remembered=False, revoked=True)
        and o.account.live_tokens == ()
    ),
)
async def device_remove_ends_a_session_only_row_too(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, remembered=False)
    await w.store_token(ref, TRUSTED, "t1")
    await w.device_remove(ref, await w.row_id(ref, TRUSTED))


def _check_other_persons_row_untouched(obs: Observation) -> None:
    other = obs.accounts[1]
    assert other.device(TRUSTED) == row(TRUSTED)
    assert other.live_tokens == ((TRUSTED, 1),)


@case("not_found", check=_check_other_persons_row_untouched)
async def device_remove_of_another_persons_row_is_not_found(w: World) -> None:
    ref = await standard(w)
    other = await w.add_account(email="second@example.com", phone="0722000111")
    await w.trust(other, TRUSTED)
    await w.store_token(other, TRUSTED, "o1")
    await w.device_remove(ref, await w.row_id(other, TRUSTED))


@case("not_found")
async def device_remove_of_an_unknown_row_is_not_found(w: World) -> None:
    ref = await standard(w)
    await w.device_remove(ref, UUID(int=2))


@case("not_found")
async def device_remove_for_an_unknown_user_is_not_found(w: World) -> None:
    ref = await standard(w)
    await w.device_remove(STRANGER, await w.row_id(ref, TRUSTED))


@case("not_found", check=lambda o: _expect(o.account.device(TRUSTED) == row(TRUSTED, revoked=True)))
async def device_remove_of_a_revoked_row_is_not_found(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, revoked=True)
    await w.device_remove(ref, await w.row_id(ref, TRUSTED))


@case("not_found")
async def device_remove_of_a_row_unused_for_90_days_is_not_found(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, last_used_at=T0 - 90 * DAY)
    await w.device_remove(ref, await w.row_id(ref, TRUSTED))


# --- 3.6 refresh ----------------------------------------------------------------------------


@case("refused", "token_unknown", check=lambda o: _expect(o.account.tokens_total == 1))
async def refresh_with_an_unknown_token_is_refused(w: World) -> None:
    ref = await standard(w)
    await w.store_token(ref, TRUSTED, "t1")
    await w.refresh("missing")


@case(
    "refused",
    "token_unknown",
    check=lambda o: _expect(o.account.live(TRUSTED) == 1 and o.account.tokens_total == 1),
)
async def refresh_from_another_device_is_refused(w: World) -> None:
    ref = await standard(w)
    await w.trust(ref, OTHER)
    await w.store_token(ref, TRUSTED, "t1")
    await w.refresh("t1", device=OTHER)


@case("refused", "inactive", check=lambda o: _expect(o.account.live_tokens == ()))
async def refresh_of_a_removed_user_revokes_every_token(w: World) -> None:
    ref = await standard(w, status="removed")
    await w.trust(ref, OTHER)
    await w.store_token(ref, TRUSTED, "t1")
    await w.store_token(ref, OTHER, "t2")
    await w.refresh("t1")


def _check_rotation(obs: Observation) -> None:
    account = obs.account
    assert account.live_tokens == ((TRUSTED, 1),)
    assert account.tokens_total == 2
    assert obs.last.refresh_expires_at == LATER
    assert account.device(TRUSTED) == row(TRUSTED, used=T0)
    assert account.last_signed_in_at is None


@case("authenticated", check=_check_rotation)
async def refresh_rotates_the_presented_token_and_marks_the_device_used(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, last_used_at=T0 - 5 * DAY)
    await w.store_token(ref, TRUSTED, "t1")
    await w.refresh("t1")


def _check_replay(obs: Observation) -> None:
    account = obs.account
    assert account.live(TRUSTED) == 0 and account.live(OTHER) == 1
    assert account.device(TRUSTED) == row(TRUSTED)


@case("refused", "token_replayed", check=_check_replay)
async def refresh_replay_revokes_the_live_tokens_of_that_device_only(w: World) -> None:
    ref = await standard(w)
    await w.trust(ref, OTHER)
    await w.store_token(ref, TRUSTED, "t1")
    await w.store_token(ref, OTHER, "o1")
    await w.refresh("t1", new="t2")
    await w.refresh("t1")


@case("refused", "token_replayed", check=lambda o: _expect(o.account.live_tokens == ()))
async def refresh_replay_of_a_rotated_token_kills_its_successor(w: World) -> None:
    ref = await standard(w)
    await w.store_token(ref, TRUSTED, "t1")
    await w.refresh("t1", new="t2")
    await w.refresh("t1", new="t3")


@case("refused", "token_expired", check=lambda o: _expect(o.account.live(TRUSTED) == 1))
async def refresh_of_a_token_expiring_now_is_refused(w: World) -> None:
    ref = await standard(w)
    await w.store_token(ref, TRUSTED, "t1", expires_at=T0)
    await w.refresh("t1")


@case("refused", "token_replayed")
async def refresh_reports_a_replay_before_an_expiry(w: World) -> None:
    ref = await standard(w)
    await w.store_token(ref, TRUSTED, "t1", expires_at=lapsed(), revoked=True)
    await w.refresh("t1")


@case(
    "refused",
    "locked",
    check=lambda o: _expect(o.account.live(TRUSTED) == 1 and o.account.failed_attempts == 5),
)
async def refresh_while_locked_on_every_device_is_refused(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=5)
    await w.store_token(ref, TRUSTED, "t1")
    await w.refresh("t1")


@case(
    "authenticated",
    check=lambda o: _expect(
        (o.account.failed_attempts, o.account.untrusted_failed_attempts) == (0, 5)
    ),
)
async def refresh_is_not_refused_by_a_lock_for_new_devices_only(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, untrusted_failed_attempts=5)
    await w.store_token(ref, TRUSTED, "t1")
    await w.refresh("t1")


@case("refused", "device_untrusted", check=lambda o: _expect(o.account.live(OTHER) == 1))
async def refresh_on_an_untrusted_device_is_refused(w: World) -> None:
    ref = await standard(w)
    await w.store_token(ref, OTHER, "o1")
    await w.refresh("o1", device=OTHER)


@case("refused", "device_untrusted")
async def refresh_on_a_device_whose_trust_ended_is_refused(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, expires_at=T0)
    await w.store_token(ref, TRUSTED, "t1")
    await w.refresh("t1")


@case("refused", "device_untrusted", check=lambda o: _expect(o.account.live(TRUSTED) == 1))
async def refresh_on_a_device_unused_for_90_days_is_refused(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, last_used_at=T0 - 90 * DAY)
    await w.store_token(ref, TRUSTED, "t1")
    await w.refresh("t1")


@case("authenticated")
async def refresh_on_a_session_only_device_succeeds(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, remembered=False)
    await w.store_token(ref, TRUSTED, "t1")
    await w.refresh("t1")


@case("refused", "inactive", check=lambda o: _expect(o.account.live(TRUSTED) == 1))
async def refresh_without_a_membership_keeps_the_token(w: World) -> None:
    ref = await standard(w, membership=False)
    await w.store_token(ref, TRUSTED, "t1")
    await w.refresh("t1")


def _check_fresh_claims(obs: Observation) -> None:
    step = obs.last
    assert (step.access_token_minutes, step.security_version) == (5, 3)
    assert step.refresh_expires_at == T0 + 10 * DAY
    assert obs.steps[0].access_token_minutes == 10


@case("authenticated", check=_check_fresh_claims)
async def refresh_reads_fresh_claims_each_time(w: World) -> None:
    ref = await standard(w)
    await w.store_token(ref, TRUSTED, "t1")
    await w.refresh("t1", new="t2")
    await w.set_policy(ref, access_token_minutes=5, refresh_token_days=10)
    await w.set_user(ref, security_version=3)
    await w.refresh("t2")


# --- 3.7 sign-out ---------------------------------------------------------------------------


def _check_sign_out(obs: Observation) -> None:
    account = obs.account
    assert account.live(TRUSTED) == 0 and account.live(OTHER) == 1
    assert account.device(TRUSTED) == row(TRUSTED)


@case("signed_out", check=_check_sign_out)
async def sign_out_revokes_the_live_tokens_of_the_device_only(w: World) -> None:
    ref = await standard(w)
    await w.trust(ref, OTHER)
    await w.store_token(ref, TRUSTED, "t1")
    await w.store_token(ref, TRUSTED, "t2")
    await w.store_token(ref, OTHER, "o1")
    await w.sign_out("t1")


@case(
    "signed_out",
    check=lambda o: _expect(
        o.account.device(TRUSTED) == row(TRUSTED, remembered=False, revoked=True)
        and o.account.device(OTHER) == row(OTHER, remembered=False)
        and o.account.live_tokens == ((OTHER, 1),)
    ),
)
async def sign_out_also_revokes_the_row_of_a_session_only_device(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, remembered=False)
    await w.trust(ref, OTHER, remembered=False)
    await w.store_token(ref, TRUSTED, "t1")
    await w.store_token(ref, OTHER, "o1")
    await w.sign_out("t1")


@case("signed_out", "token_unknown", check=lambda o: _expect(o.account.live(TRUSTED) == 1))
async def sign_out_with_an_unknown_token_changes_nothing(w: World) -> None:
    ref = await standard(w)
    await w.store_token(ref, TRUSTED, "t1")
    await w.sign_out("missing")


@case(
    "signed_out",
    "token_unknown",
    check=lambda o: _expect(
        o.account.live(TRUSTED) == 1 and o.account.device(TRUSTED) == row(TRUSTED, remembered=False)
    ),
)
async def sign_out_from_another_device_changes_nothing(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, remembered=False)
    await w.store_token(ref, TRUSTED, "t1")
    await w.sign_out("t1", device=OTHER)


@case("signed_out", check=lambda o: _expect(o.last.refusal is None and o.account.live_tokens == ()))
async def sign_out_with_a_spent_token_still_revokes_the_live_ones(w: World) -> None:
    ref = await standard(w)
    await w.store_token(ref, TRUSTED, "t1", revoked=True)
    await w.store_token(ref, TRUSTED, "t2")
    await w.sign_out("t1")


# --- 3.8 revoke a device --------------------------------------------------------------------


@case("device_revoked", check=_check_device_revoked)
async def revoke_device_ends_trust_tokens_and_codes_of_that_device(w: World) -> None:
    ref = await standard(w)
    await w.trust(ref, OTHER)
    await w.store_token(ref, TRUSTED, "t1")
    await w.store_token(ref, OTHER, "o1")
    await w.store_code(ref, CodePurpose.PIN_RESET, TRUSTED, created_at=T0 - 5 * MINUTE)
    await w.store_code(ref, CodePurpose.PIN_RESET, OTHER, created_at=T0 - 4 * MINUTE)
    await w.revoke_device(ref)


@case("device_revoked")
async def revoke_device_of_an_unknown_user_still_answers(w: World) -> None:
    await standard(w)
    await w.revoke_device(STRANGER)


@case("device_revoked", check=lambda o: _expect(o.account.devices == (row(TRUSTED),)))
async def revoke_device_of_an_unknown_device_creates_nothing(w: World) -> None:
    ref = await standard(w)
    await w.revoke_device(ref, device="never-seen")


# --- 3.9 and 3.10 session resolution --------------------------------------------------------


@case("session", check=lambda o: _expect(o.last.role == "Owner" and o.last.organization_matches))
async def resolve_session_returns_the_organization_and_role(w: World) -> None:
    ref = await standard(w)
    await w.resolve(ref)


@case("session_invalid")
async def resolve_session_of_an_unknown_user_is_refused(w: World) -> None:
    await standard(w)
    await w.resolve(STRANGER)


@case("session_invalid")
async def resolve_session_of_a_removed_user_is_refused(w: World) -> None:
    ref = await standard(w, status="removed")
    await w.resolve(ref)


@case("session_invalid")
async def resolve_session_with_a_moved_security_version_is_refused(w: World) -> None:
    ref = await standard(w)
    await w.resolve(ref, version=1)


@case("session_invalid")
async def resolve_session_after_a_pin_change_is_refused(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, security_version=1)
    await w.resolve(ref, version=0)


@case("session_invalid")
async def resolve_session_from_an_untrusted_device_is_refused(w: World) -> None:
    ref = await standard(w)
    await w.resolve(ref, device=UNTRUSTED)


@case("session_invalid")
async def resolve_session_from_a_revoked_device_is_refused(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, revoked=True)
    await w.resolve(ref)


@case("session_invalid")
async def resolve_session_from_a_device_whose_trust_ended_is_refused(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, expires_at=T0)
    await w.resolve(ref)


@case("session")
async def resolve_session_from_a_device_trusted_beyond_now_is_accepted(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, expires_at=T0 + timedelta(seconds=1))
    await w.resolve(ref)


@case("session_invalid")
async def resolve_session_from_a_device_unused_for_90_days_is_refused(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, last_used_at=T0 - 90 * DAY)
    await w.resolve(ref)


@case("session")
async def resolve_session_from_a_device_used_just_inside_90_days_is_accepted(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, last_used_at=T0 - 90 * DAY + timedelta(seconds=1))
    await w.resolve(ref)


@case("session")
async def resolve_session_from_a_session_only_device_is_accepted(w: World) -> None:
    ref = await w.add_account()
    await w.trust(ref, TRUSTED, remembered=False)
    await w.resolve(ref)


@case("session")
async def resolve_session_from_a_tokened_device_needs_no_token(w: World) -> None:
    ref = await tokened(w)
    await w.resolve(ref)


@case("session")
async def resolve_session_does_not_check_the_lock(w: World) -> None:
    ref = await standard(w)
    await w.set_user(ref, failed_attempts=5, untrusted_failed_attempts=5)
    await w.resolve(ref)


@case(
    "session", check=lambda o: _expect(o.last.role is None and o.last.organization_matches is None)
)
async def resolve_session_without_a_membership_has_no_organization(w: World) -> None:
    ref = await standard(w, membership=False)
    await w.resolve(ref)


@case(
    "session", check=lambda o: _expect(o.last.role is None and o.last.organization_matches is True)
)
async def resolve_session_without_a_role_keeps_the_organization(w: World) -> None:
    ref = await standard(w, role=None)
    await w.resolve(ref)


# --- withdrawing a code ---------------------------------------------------------------------


def _check_reissue(obs: Observation) -> None:
    first, _, third = obs.steps
    assert first.code_id_set and third.code_issued
    live, withdrawn = obs.account.codes
    assert withdrawn[3] is True and withdrawn[5] == 0
    assert live[3] is False and live[5] == 600


@case("check_email", check=_check_reissue)
async def withdrawing_a_code_lets_the_next_request_through_without_a_cooldown(w: World) -> None:
    await standard(w)
    issued = await w.request_code(CodePurpose.PIN_RESET)
    assert issued.code_id is not None
    await w.withdraw(issued.code_id)
    await w.request_code(CodePurpose.PIN_RESET)


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def withdrawing_a_sign_in_code_lets_the_next_sign_in_issue_another(w: World) -> None:
    ref = await standard(w)
    issued = await w.sign_in(ref, device=UNTRUSTED)
    assert issued.code_id is not None
    await w.withdraw(issued.code_id)
    await w.sign_in(ref, device=UNTRUSTED)


@case("verification_required", check=lambda o: _expect(o.last.code_issued is True))
async def withdrawing_a_number_step_code_lets_the_next_number_step_issue_another(
    w: World,
) -> None:
    await standard(w, pin=False)
    issued = await w.start()
    assert issued.code_id is not None
    await w.withdraw(issued.code_id)
    await w.start()


def _check_withdraw_leaves_used_codes(obs: Observation) -> None:
    used, open_code = obs.account.codes
    assert used[3] is True and used[5] == 600
    assert open_code[3] is True and open_code[5] == 0


@case("withdrawn", check=_check_withdraw_leaves_used_codes)
async def withdrawing_leaves_a_used_code_alone_and_ends_an_open_one(w: World) -> None:
    ref = await standard(w)
    used = await w.store_code(
        ref, CodePurpose.PIN_RESET, OTHER, created_at=T0 - 5 * MINUTE, consumed=True
    )
    open_code = await w.store_code(ref, CodePurpose.PIN_RESET, OTHER, created_at=T0 - 4 * MINUTE)
    await w.withdraw(used)
    await w.withdraw(open_code)


@case("withdrawn", check=lambda o: _expect(o.account.codes[0][3] is False))
async def withdrawing_an_unknown_code_changes_nothing(w: World) -> None:
    ref = await standard(w)
    await w.store_code(ref, CodePurpose.PIN_RESET, OTHER)
    await w.withdraw(STRANGER)
