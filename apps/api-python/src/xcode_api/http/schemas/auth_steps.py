"""Wire shapes of the number-first sign-in routes (``docs/06-http-contract.md`` 2.12.1).

Every request model is strict: strings are strings, ``trustDevice`` a JSON boolean, a missing
string is ``""`` (an absent ``deviceToken`` or ``deviceName``), and an explicit ``null`` is
refused by the router as ``invalid_request``. The step envelope always writes its eleven
properties, in order, with nulls.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from ...domain.identity import AuthEnvelope, CodePurpose, EnvelopeStatus, PinProblem
from ...domain.identity import TrustedDeviceView as TrustedDeviceRecord
from ...domain.values import DeviceId, DeviceName, DeviceToken, PhoneNumber, Pin, VerificationCode
from .auth import storable
from .common import ApiModel, Instant

_PURPOSES = frozenset(p.value for p in CodePurpose)
_NEW_PIN_PURPOSES = frozenset({CodePurpose.FIRST_SETUP.value, CodePurpose.PIN_RESET.value})


class _StepFields(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="ignore", strict=True)

    phone_number: str = ""
    device_id: str = ""
    device_name: str = ""

    def _base_valid(self, *values: str) -> bool:
        if not all(
            storable(v) for v in (self.phone_number, self.device_id, self.device_name, *values)
        ):
            return False
        try:
            DeviceName.parse(self.device_name)
        except ValueError:
            return False
        return (
            1 <= len(self.device_id) <= DeviceId.MAX_LENGTH
            and len(self.phone_number) <= PhoneNumber.MAX_INPUT_LENGTH
        )

    @property
    def name(self) -> str | None:
        return DeviceName.parse(self.device_name)


class _TokenFields(_StepFields):
    device_token: str = ""

    def _token_valid(self) -> bool:
        return self.device_token == "" or DeviceToken.valid(self.device_token)

    @property
    def token(self) -> str | None:
        return self.device_token or None


class StartRequest(_TokenFields):
    """``POST /auth/start``: ``phoneNumber``, ``deviceId``, ``deviceToken?``, ``deviceName?``."""

    def shape_valid(self) -> bool:
        return self._base_valid(self.device_token) and self._token_valid()


class PinRequest(_TokenFields):
    """``POST /auth/pin``: the number step's fields and the ``pin``."""

    pin: str = ""

    def shape_valid(self) -> bool:
        return (
            self._base_valid(self.device_token, self.pin)
            and self._token_valid()
            and len(self.pin) <= Pin.MAX_LENGTH
        )


class CodeStepRequest(_StepFields):
    """``POST /auth/code``: ``purpose``, ``code`` and ``trustDevice`` (default true)."""

    purpose: str = ""
    code: str = ""
    trust_device: bool = True

    def shape_valid(self) -> bool:
        return (
            self._base_valid(self.purpose, self.code)
            and self.purpose in _PURPOSES
            and len(self.code) <= VerificationCode.MAX_LENGTH
        )


class ResendRequest(_StepFields):
    """``POST /auth/code/resend``: the ``purpose`` of the code to send again."""

    purpose: str = ""

    def shape_valid(self) -> bool:
        return self._base_valid(self.purpose) and self.purpose in _PURPOSES


class ForgotPinRequest(_StepFields):
    """``POST /auth/pin/forgot``."""

    def shape_valid(self) -> bool:
        return self._base_valid()


class NewPinRequest(_StepFields):
    """``POST /auth/pin/new``: ``purpose`` (``first_setup`` or ``pin_reset``), ``code``, the
    new ``pin`` and ``trustDevice`` (default true)."""

    purpose: str = ""
    code: str = ""
    pin: str = ""
    trust_device: bool = True

    def shape_valid(self) -> bool:
        return (
            self._base_valid(self.purpose, self.code, self.pin)
            and self.purpose in _NEW_PIN_PURPOSES
            and len(self.code) <= VerificationCode.MAX_LENGTH
            and len(self.pin) <= Pin.MAX_LENGTH
        )


class ChangePinRequest(BaseModel):
    """``POST /auth/pin/change`` (bearer): ``currentPin`` and ``newPin``."""

    model_config = ConfigDict(alias_generator=to_camel, extra="ignore", strict=True)

    current_pin: str = ""
    new_pin: str = ""

    def shape_valid(self) -> bool:
        return (
            storable(self.current_pin)
            and storable(self.new_pin)
            and len(self.current_pin) <= Pin.MAX_LENGTH
            and len(self.new_pin) <= Pin.MAX_LENGTH
        )


class StepResponse(BaseModel):
    """The step envelope: the seven properties of the released envelope, then ``purpose``,
    ``triesLeft``, ``pinProblem`` and ``deviceToken``."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    status: EnvelopeStatus
    access_token: str | None = None
    refresh_token: str | None = None
    retry_after_seconds: int | None = None
    development_code: str | None = None
    masked_email: str | None = None
    minimum_pin_length: int | None = None
    purpose: CodePurpose | None = None
    tries_left: int | None = None
    pin_problem: PinProblem | None = None
    device_token: str | None = None

    @classmethod
    def from_envelope(cls, envelope: AuthEnvelope) -> StepResponse:
        return cls(
            status=envelope.status,
            access_token=envelope.access_token,
            refresh_token=envelope.refresh_token,
            retry_after_seconds=envelope.retry_after_seconds,
            development_code=envelope.development_code,
            masked_email=envelope.masked_email,
            minimum_pin_length=envelope.minimum_pin_length,
            purpose=envelope.purpose,
            tries_left=envelope.tries_left,
            pin_problem=envelope.pin_problem,
            device_token=envelope.device_token,
        )


class TrustedDeviceResponse(ApiModel):
    """``TrustedDevice``: ``{id, name, trustedAt, lastUsedAt, thisDevice}``."""

    id: UUID
    name: str | None
    trusted_at: Instant
    last_used_at: Instant
    this_device: bool

    @classmethod
    def from_view(cls, view: TrustedDeviceRecord) -> TrustedDeviceResponse:
        return cls(
            id=view.id,
            name=view.name,
            trusted_at=view.trusted_at,
            last_used_at=view.last_used_at,
            this_device=view.this_device,
        )
