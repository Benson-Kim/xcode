"""Identity vocabulary: users, devices, sign-in attempts, the account state routines return,
and the commands and outcomes of the ``api.auth_*`` and operator user routines.

The enumeration values are the strings the ``identity`` tables constrain with ``CHECK``;
``tests/db/test_enum_parity.py`` proves each enum equals its constraint. Digests and
addresses are kept out of ``repr`` so a logged command or outcome carries neither.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class UserStatus(StrEnum):
    ACTIVE = "active"
    REMOVED = "removed"


class CodePurpose(StrEnum):
    FIRST_SETUP = "first_setup"
    NEW_DEVICE = "new_device"
    PIN_RESET = "pin_reset"


class SignInOperation(StrEnum):
    SIGN_IN = "sign_in"
    VERIFY_DEVICE = "verify_device"
    REQUEST_CODE = "request_code"
    VERIFY_CODE = "verify_code"
    COMPLETE_PIN = "complete_pin"
    REFRESH = "refresh"
    SIGN_OUT = "sign_out"
    REVOKE_DEVICE = "revoke_device"
    START = "start"
    PIN = "pin"
    CODE = "code"
    RESEND_CODE = "resend_code"
    FORGOT_PIN = "forgot_pin"
    NEW_PIN = "new_pin"
    CHANGE_PIN = "change_pin"
    REMOVE_DEVICE = "remove_device"


class SignInOutcome(StrEnum):
    AUTHENTICATED = "authenticated"
    VERIFICATION_REQUIRED = "verification_required"
    CHECK_EMAIL = "check_email"
    CODE_VERIFIED = "code_verified"
    PAUSED = "paused"
    REFUSED = "refused"
    SIGNED_OUT = "signed_out"
    DEVICE_REVOKED = "device_revoked"
    PIN_REQUIRED = "pin_required"
    PIN_LOCKED = "pin_locked"
    BLOCKED = "blocked"
    CODE_RESENT = "code_resent"
    PIN_CHANGED = "pin_changed"


class SignInRefusal(StrEnum):
    UNKNOWN_NUMBER = "unknown_number"
    INACTIVE = "inactive"
    NO_PIN = "no_pin"
    WRONG_PIN = "wrong_pin"
    PAUSED_UNTRUSTED = "paused_untrusted"
    UNTRUSTED_CAP = "untrusted_cap"
    WRONG_CODE = "wrong_code"
    CODE_EXPIRED = "code_expired"
    TOKEN_UNKNOWN = "token_unknown"  # noqa: S105 - a refusal code
    TOKEN_REPLAYED = "token_replayed"  # noqa: S105 - a refusal code
    TOKEN_EXPIRED = "token_expired"  # noqa: S105 - a refusal code
    DEVICE_UNTRUSTED = "device_untrusted"
    POLICY_PIN_LENGTH = "policy_pin_length"
    LOCKED = "locked"
    RESET_REQUIRED = "reset_required"
    PIN_RULE = "pin_rule"
    VERDICT_VOID = "verdict_void"


class PinProblem(StrEnum):
    """Why a new PIN is refused (``docs/07-auth.md`` 12.4); the step envelope's ``pinProblem``."""

    LENGTH = "length"
    WEAK = "weak"
    UNCHANGED = "unchanged"


class SignInStatus(StrEnum):
    """``identity.sign_in_status``: the people status of the sign-in state."""

    ACTIVE = "active"
    NOT_SIGNED_IN = "not_signed_in"
    PIN_RESET_DUE = "pin_reset_due"
    LOCKED = "locked"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class User:
    """``identity.users`` without the PIN hash, which only ``AccountState`` carries."""

    id: UUID
    email: str
    phone_number: str
    status: UserStatus
    security_version: int
    failed_attempts: int
    untrusted_failed_attempts: int
    pin_reset_required: bool
    last_signed_in_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TrustedDevice:
    """``identity.trusted_devices``: ``token_hash`` is ``None`` for a device trusted by its
    ``device_id`` alone (v2.11) and for one trusted for a session only."""

    id: UUID
    user_id: UUID
    device_id: str
    revoked: bool
    trust_expires_at: datetime | None
    token_hash: str | None = field(repr=False)
    name: str | None
    trusted_at: datetime
    last_used_at: datetime
    remembered: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SignInAttempt:
    id: int
    occurred_at: datetime
    operation: SignInOperation
    outcome: SignInOutcome
    refusal: SignInRefusal | None
    user_id: UUID | None
    phone_digest: str
    device_id: str
    request_id: str | None


@dataclass(frozen=True, slots=True)
class AccountPolicy:
    """``identity.policy``: the active membership's organization policy and identity."""

    organization_id: UUID
    pin_length: int
    lockout_threshold: int
    lockout_minutes: int
    access_token_minutes: int
    refresh_token_days: int
    role_name: str
    first_name: str
    last_name: str
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AccountState:
    """``api.account_state``: what a PIN check needs to verify the PIN in Python."""

    user_id: UUID
    status: UserStatus
    pin_hash: str | None
    phone_number: str = field(repr=False)
    security_version: int
    failed_attempts: int
    untrusted_failed_attempts: int
    pin_reset_required: bool
    device_trusted: bool
    policy: AccountPolicy | None


class AuthOutcomeKind(StrEnum):
    """The ``outcome`` of an ``api.auth_*`` routine (``docs/05-routines.md`` section 3.1)."""

    AUTHENTICATED = "authenticated"
    VERIFICATION_REQUIRED = "verification_required"
    CHECK_EMAIL = "check_email"
    SILENT = "silent"
    CODE_VERIFIED = "code_verified"
    INVALID_PIN = "invalid_pin"
    PAUSED = "paused"
    REFUSED = "refused"
    SIGNED_OUT = "signed_out"
    DEVICE_REVOKED = "device_revoked"
    PIN_REQUIRED = "pin_required"
    PIN_LOCKED = "pin_locked"
    BLOCKED = "blocked"
    CODE_RESENT = "code_resent"
    PIN_CHANGED = "pin_changed"


@dataclass(frozen=True, slots=True)
class AuthOutcome:
    """The decision of an ``api.auth_*`` routine; only the fields the outcome needs are set.

    ``authenticated`` carries the claim material the service signs (organization, role,
    names, permissions, security version, lifetimes); an issued code carries its id and the
    stored address it is mailed to; the steps of the number-first flow add the code's
    ``purpose``, the ``tries_left`` of a refused PIN or code, the ``pin_problem`` of a refused
    new PIN and whether a device token was stored.
    """

    outcome: AuthOutcomeKind
    refusal: SignInRefusal | None = None
    retry_after_seconds: int | None = None
    masked_email: str | None = None
    code_issued: bool | None = None
    code_id: UUID | None = None
    email: str | None = field(default=None, repr=False)
    minimum_pin_length: int | None = None
    user_id: UUID | None = None
    organization_id: UUID | None = None
    role: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    permissions: tuple[str, ...] | None = None
    security_version: int | None = None
    access_token_minutes: int | None = None
    refresh_expires_at: datetime | None = None
    purpose: CodePurpose | None = None
    tries_left: int | None = None
    pin_problem: PinProblem | None = None
    device_token_issued: bool | None = None


class EnvelopeStatus(StrEnum):
    """The ``status`` of the wire envelope every ``/auth`` route answers with; the last five
    belong to the routes of the number-first flow only."""

    AUTHENTICATED = "authenticated"
    VERIFICATION_REQUIRED = "verification_required"
    CHECK_EMAIL = "check_email"
    CODE_VERIFIED = "code_verified"
    PAUSED = "paused"
    AUTHENTICATION_FAILED = "authentication_failed"
    INVALID_PIN = "invalid_pin"
    INVALID_REQUEST = "invalid_request"
    SIGNED_OUT = "signed_out"
    DEVICE_REVOKED = "device_revoked"
    SERVICE_UNAVAILABLE = "service_unavailable"
    PIN_REQUIRED = "pin_required"
    PIN_LOCKED = "pin_locked"
    BLOCKED = "blocked"
    CODE_RESENT = "code_resent"
    PIN_CHANGED = "pin_changed"


@dataclass(frozen=True, slots=True)
class AuthEnvelope:
    """The envelope properties; only those the status needs are set. The released routes
    serialise the first seven, the number-first routes all eleven."""

    status: EnvelopeStatus
    access_token: str | None = field(default=None, repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    retry_after_seconds: int | None = None
    development_code: str | None = field(default=None, repr=False)
    masked_email: str | None = None
    minimum_pin_length: int | None = None
    purpose: CodePurpose | None = None
    tries_left: int | None = None
    pin_problem: PinProblem | None = None
    device_token: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class AccessGrant:
    """What an access token states, valid for ``lifetime_minutes`` from its issue time."""

    user_id: UUID
    device_id: str
    security_version: int
    organization_id: UUID
    role: str
    first_name: str
    last_name: str
    permissions: tuple[str, ...]
    lifetime_minutes: int


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """The claims of an access token whose signature, issuer, audience and lifetime held."""

    user_id: UUID
    device_id: str
    security_version: int
    organization_id: UUID | None
    role: str
    first_name: str
    last_name: str
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Principal:
    """The caller of a bearer route after session resolution: identity from the token,
    organization and role as the database resolved them for this request."""

    user_id: UUID
    device_id: str
    security_version: int
    organization_id: UUID | None
    role: str | None
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SessionView:
    """``GET /auth/session``: the token's own claims, echoed."""

    user_id: UUID
    first_name: str
    last_name: str
    role: str
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SessionContext:
    """What session resolution returns for the log context of a bearer request."""

    organization_id: UUID | None
    role: str | None


@dataclass(frozen=True, slots=True)
class TrustedDeviceView:
    """One of the signed-in person's own trusted devices (``GET /auth/trusted-devices``)."""

    id: UUID
    name: str | None
    trusted_at: datetime
    last_used_at: datetime
    this_device: bool


@dataclass(frozen=True, slots=True)
class AccountLookup:
    """``api.auth_account_lookup``: statement one of a PIN check. ``device_token_hash`` is
    ``None`` on the released routes (trust by ``device_id``) and ``""`` on a new route that
    sent no token; ``pin_try`` records an unknown number as a PIN try."""

    request_id: str
    phone: str
    device_id: str
    now: datetime
    device_token_hash: str | None = field(default=None, repr=False)
    pin_try: bool = True


@dataclass(frozen=True, slots=True)
class UserLookup:
    """``api.auth_account_lookup_user``: the signed-in person's account state (N07)."""

    request_id: str
    user_id: UUID
    device_id: str
    now: datetime


@dataclass(frozen=True, slots=True)
class PinVerdict:
    """``api.auth_sign_in``: the service's PIN verdict, the stored hash it was checked against
    (``None`` for the dummy hash), plus the code and refresh-token digests the routine stores
    if its decision needs them (``user_id`` is ``None`` when the lookup found no account)."""

    request_id: str
    user_id: UUID | None
    device_id: str
    pin_ok: bool
    checked_pin_hash: str | None = field(repr=False)
    code_hash: str | None = field(repr=False)
    refresh_token_hash: str = field(repr=False)
    skip_cooldown: bool
    now: datetime


@dataclass(frozen=True, slots=True)
class NumberCheck:
    """``api.auth_start``: the number step (N01)."""

    request_id: str
    phone: str
    device_id: str
    device_token_hash: str | None = field(repr=False)
    code_hash: str = field(repr=False)
    skip_cooldown: bool
    now: datetime


@dataclass(frozen=True, slots=True)
class PinCheck:
    """``api.auth_pin``: the PIN step's verdict (N02), with the digests the routine stores if
    its decision needs them."""

    request_id: str
    phone: str
    device_id: str
    device_token_hash: str | None = field(repr=False)
    pin_ok: bool
    checked_pin_hash: str | None = field(repr=False)
    code_hash: str = field(repr=False)
    refresh_token_hash: str = field(repr=False)
    skip_cooldown: bool
    now: datetime


@dataclass(frozen=True, slots=True)
class CodeEntry:
    """``api.auth_check_code``: the code step (N03). ``device_token_hash`` is stored only when
    the device is trusted (``trust``)."""

    request_id: str
    phone: str
    device_id: str
    purpose: CodePurpose
    code_hash: str = field(repr=False)
    replacement_code_hash: str = field(repr=False)
    device_name: str | None
    trust: bool
    device_token_hash: str | None = field(repr=False)
    refresh_token_hash: str = field(repr=False)
    trust_days: int | None
    now: datetime


@dataclass(frozen=True, slots=True)
class CodeResend:
    """``api.auth_resend_code``: "Send a new code" (N04)."""

    request_id: str
    phone: str
    device_id: str
    purpose: CodePurpose
    code_hash: str = field(repr=False)
    skip_cooldown: bool
    now: datetime


@dataclass(frozen=True, slots=True)
class DeviceVerification:
    """``api.auth_verify_device``; ``trust_days`` ``None`` trusts the device without expiry."""

    request_id: str
    phone: str
    device_id: str
    code_hash: str = field(repr=False)
    replacement_code_hash: str = field(repr=False)
    refresh_token_hash: str = field(repr=False)
    trust_days: int | None
    now: datetime


@dataclass(frozen=True, slots=True)
class CodeRequest:
    """``api.auth_request_code`` for ``first_setup`` or ``pin_reset``."""

    request_id: str
    phone: str
    device_id: str
    purpose: CodePurpose
    code_hash: str = field(repr=False)
    skip_cooldown: bool
    now: datetime


@dataclass(frozen=True, slots=True)
class CodeCheck:
    """``api.auth_verify_code``."""

    request_id: str
    phone: str
    device_id: str
    purpose: CodePurpose
    code_hash: str = field(repr=False)
    replacement_code_hash: str = field(repr=False)
    now: datetime


@dataclass(frozen=True, slots=True)
class PinCompletion:
    """``api.auth_complete_pin``: the new PIN arrives hashed. On a reset, ``new_pin_is_current``
    is the verdict of the new PIN against the stored hash ``checked_pin_hash`` (``None`` for the
    dummy hash and on a first PIN). The released routes trust the device without a token."""

    request_id: str
    phone: str
    device_id: str
    purpose: CodePurpose
    code_hash: str = field(repr=False)
    new_pin_is_current: bool
    checked_pin_hash: str | None = field(repr=False)
    pin_hash: str = field(repr=False)
    device_name: str | None
    trust: bool
    device_token_hash: str | None = field(repr=False)
    refresh_token_hash: str = field(repr=False)
    trust_days: int | None
    now: datetime


@dataclass(frozen=True, slots=True)
class PinChange:
    """``api.auth_change_pin``: the current PIN's verdict against ``checked_pin_hash`` and the
    new PIN's hash (N07)."""

    request_id: str
    user_id: UUID
    device_id: str
    current_ok: bool
    checked_pin_hash: str | None = field(repr=False)
    pin_hash: str = field(repr=False)
    now: datetime


@dataclass(frozen=True, slots=True)
class TokenRefresh:
    """``api.auth_refresh``: the presented token's digest and the digest of its replacement."""

    request_id: str
    token_hash: str = field(repr=False)
    device_id: str
    new_token_hash: str = field(repr=False)
    now: datetime


@dataclass(frozen=True, slots=True)
class TokenSignOut:
    """``api.auth_sign_out``."""

    request_id: str
    token_hash: str = field(repr=False)
    device_id: str
    now: datetime


@dataclass(frozen=True, slots=True)
class DeviceRevocation:
    """``api.auth_revoke_device`` for the caller's own device."""

    request_id: str
    user_id: UUID
    device_id: str
    now: datetime


@dataclass(frozen=True, slots=True)
class DeviceListing:
    """``api.auth_device_list``: the signed-in person's own devices, marking ``device_id``."""

    user_id: UUID
    device_id: str
    now: datetime


@dataclass(frozen=True, slots=True)
class DeviceRemoval:
    """``api.auth_device_remove``: one of the signed-in person's own device rows, by row id."""

    request_id: str
    user_id: UUID
    row_id: UUID
    now: datetime


@dataclass(frozen=True, slots=True)
class CodeWithdrawal:
    """``api.auth_withdraw_code`` after a code's mail could not be sent."""

    request_id: str
    code_id: UUID
    now: datetime


@dataclass(frozen=True, slots=True)
class SessionCheck:
    """``api.auth_resolve_session``: the verified token's subject, device and version claim."""

    user_id: UUID
    device_id: str
    security_version: int
    now: datetime


@dataclass(frozen=True, slots=True)
class UserProvisioning:
    """``api.ops_provision_user``; optional fields are ``None`` when the operator left them out."""

    operator: str
    request_id: str
    email: str = field(repr=False)
    phone: str = field(repr=False)
    role: str | None
    first_name: str | None
    last_name: str | None
    organization_name: str | None
    now: datetime


@dataclass(frozen=True, slots=True)
class OperatorRequest:
    """The operator user routines that act on one account found by email."""

    operator: str
    request_id: str
    email: str = field(repr=False)
    now: datetime


@dataclass(frozen=True, slots=True)
class ProvisionedUser:
    user_id: UUID
    organization_id: UUID
    created_user: bool
    created_organization: bool
    reactivated: bool


@dataclass(frozen=True, slots=True)
class RemovedUser:
    user_id: UUID
    removed: bool
    tokens: int


@dataclass(frozen=True, slots=True)
class ClearedPause:
    """``api.ops_clear_pause``: whether either lock scope was at five before it was cleared."""

    user_id: UUID
    was_locked: bool


@dataclass(frozen=True, slots=True)
class RevokedSessions:
    user_id: UUID
    devices: int
    tokens: int


@dataclass(frozen=True, slots=True)
class AccountSummary:
    """``api.ops_account_state``: what a support call needs; never a hash or digest."""

    user_id: UUID
    status: UserStatus
    has_pin: bool
    pin_reset_required: bool
    sign_in_status: SignInStatus
    last_signed_in_at: datetime | None
    failed_attempts: int
    untrusted_failed_attempts: int
    trusted_devices: int
    live_refresh_tokens: int
    active_membership: bool


@dataclass(frozen=True, slots=True)
class DemoSeeding:
    """``api.ops_seed_demo``: the environment the routine checks itself and the PIN hashes
    of the demo logins that have one, keyed by email (set only on the users the run
    creates)."""

    operator: str
    request_id: str
    environment: str
    pin_hashes: Mapping[str, str] = field(repr=False)
    now: datetime


@dataclass(frozen=True, slots=True)
class SeededDemo:
    organization_id: UUID
    created: bool
