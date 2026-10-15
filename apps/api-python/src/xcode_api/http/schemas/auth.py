"""Wire shapes of the ``/auth`` routes (``docs/06-http-contract.md`` sections 1.6 A and 2.1).

Every request model carries the same six string fields the clients send (a missing field
is ``""``; an explicit ``null`` or a non-string is refused by the router as
``invalid_request``), so the pre-validation bounds apply to all six on every route. The
response envelope always writes its seven properties, in order, with nulls.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from ...domain.identity import AuthEnvelope, EnvelopeStatus, SessionView
from ...domain.values import DeviceId, Email, PhoneNumber, Pin, RefreshToken, VerificationCode


class AuthRequestFields(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="ignore", strict=True)

    email: str = ""
    phone_number: str = ""
    pin: str = ""
    device_id: str = ""
    code: str = ""
    refresh_token: str = ""

    def shape_valid(self) -> bool:
        """The pre-validation: bounds in code points, a valid address when an email is sent,
        and text PostgreSQL can store (no U+0000, no unpaired surrogate)."""
        values = (
            self.email,
            self.phone_number,
            self.pin,
            self.device_id,
            self.code,
            self.refresh_token,
        )
        return (
            all(storable(value) for value in values)
            and 1 <= len(self.device_id) <= DeviceId.MAX_LENGTH
            and len(self.phone_number) <= PhoneNumber.MAX_INPUT_LENGTH
            and len(self.email) <= Email.MAX_LENGTH
            and (self.email == "" or Email.parse(self.email) is not None)
            and len(self.pin) <= Pin.MAX_LENGTH
            and len(self.code) <= VerificationCode.MAX_LENGTH
            and len(self.refresh_token) <= RefreshToken.MAX_LENGTH
        )


def storable(value: str) -> bool:
    """Text PostgreSQL can store: no U+0000, no unpaired surrogate."""
    if chr(0) in value:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


class SignInRequest(AuthRequestFields):
    """Uses ``phoneNumber``, ``pin``, ``deviceId``."""


class UnlockRequest(AuthRequestFields):
    """Uses ``phoneNumber``, ``pin``, ``deviceId``."""


class VerifyDeviceRequest(AuthRequestFields):
    """Uses ``phoneNumber``, ``code``, ``deviceId``."""


class SetupPinCodeRequest(AuthRequestFields):
    """Uses ``phoneNumber``, ``deviceId``."""


class SetupPinVerifyRequest(AuthRequestFields):
    """Uses ``phoneNumber``, ``code``, ``deviceId``."""


class SetupPinCompleteRequest(AuthRequestFields):
    """Uses ``phoneNumber``, ``pin`` (the new PIN), ``code``, ``deviceId``."""


class PinResetCodeRequest(AuthRequestFields):
    """Uses ``phoneNumber``, ``deviceId``."""


class PinResetVerifyRequest(AuthRequestFields):
    """Uses ``phoneNumber``, ``code``, ``deviceId``."""


class PinResetCompleteRequest(AuthRequestFields):
    """Uses ``phoneNumber``, ``pin`` (the new PIN), ``code``, ``deviceId``."""


class RefreshRequest(AuthRequestFields):
    """Uses ``refreshToken``, ``deviceId``."""


class SignOutRequest(AuthRequestFields):
    """Uses ``refreshToken``, ``deviceId``."""


class AuthResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    status: EnvelopeStatus
    access_token: str | None = None
    refresh_token: str | None = None
    retry_after_seconds: int | None = None
    development_code: str | None = None
    masked_email: str | None = None
    minimum_pin_length: int | None = None

    @classmethod
    def from_envelope(cls, envelope: AuthEnvelope) -> AuthResponse:
        return cls(
            status=envelope.status,
            access_token=envelope.access_token,
            refresh_token=envelope.refresh_token,
            retry_after_seconds=envelope.retry_after_seconds,
            development_code=envelope.development_code,
            masked_email=envelope.masked_email,
            minimum_pin_length=envelope.minimum_pin_length,
        )


class AuthSessionResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    user_id: UUID
    first_name: str
    last_name: str
    role: str
    permissions: list[str]

    @classmethod
    def from_view(cls, view: SessionView) -> AuthSessionResponse:
        return cls(
            user_id=view.user_id,
            first_name=view.first_name,
            last_name=view.last_name,
            role=view.role,
            permissions=list(view.permissions),
        )
