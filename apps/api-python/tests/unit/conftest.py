"""The auth use-case kit: the identity fake and port doubles sharing one ``calls`` list, so a
test can assert the order in which a use case told its ports."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import pytest

from xcode_api.application.auth.change_pin import ChangePin
from xcode_api.application.auth.common import CodeDelivery
from xcode_api.application.auth.complete_pin import CompletePin
from xcode_api.application.auth.enter_code import EnterCode
from xcode_api.application.auth.enter_pin import EnterPin
from xcode_api.application.auth.refresh import Refresh
from xcode_api.application.auth.request_code import RequestCode
from xcode_api.application.auth.resolve_session import ResolveSession
from xcode_api.application.auth.revoke_device import RevokeDevice
from xcode_api.application.auth.sign_in import SignIn
from xcode_api.application.auth.sign_out import SignOut
from xcode_api.application.auth.start_sign_in import StartSignIn
from xcode_api.application.auth.verify_code import VerifyCode
from xcode_api.application.auth.verify_device import VerifyDevice
from xcode_api.security.device_tokens import RandomDeviceTokens
from xcode_api.security.digests import KeyedDigester
from xcode_api.security.pins import Pbkdf2PinHasher
from xcode_api.security.tokens import JwtTokenIssuer

from ..support.clock import ManualClock
from ..support.fakes import CodeMailerSpy, FakeIdentityRepository, FixedSecrets, PinHasherSpy

SIGNING_KEY = "a-signing-key-of-at-least-32-bytes!!"
PIN = "5826"
TRUSTED = "phone-1"
LOW_ITERATIONS = 1_000


@dataclass
class AuthKit:
    calls: list[str] = field(default_factory=list)
    clock: ManualClock = field(default_factory=ManualClock)
    hasher: Pbkdf2PinHasher = field(default_factory=lambda: Pbkdf2PinHasher(LOW_ITERATIONS))
    digests: KeyedDigester = field(default_factory=lambda: KeyedDigester(SIGNING_KEY))
    secrets: FixedSecrets = field(default_factory=FixedSecrets)
    tokens: JwtTokenIssuer = field(
        default_factory=lambda: JwtTokenIssuer(
            signing_key=SIGNING_KEY, issuer="xcode-api", audience="xcode-clients"
        )
    )

    def __post_init__(self) -> None:
        self.identity = FakeIdentityRepository(calls=self.calls)
        self.pins = PinHasherSpy(self.hasher, self.calls)
        self.mail = CodeMailerSpy(self.calls)
        self.device_tokens = RandomDeviceTokens()

    @property
    def delivery(self) -> CodeDelivery:
        return CodeDelivery(self.identity, self.clock, self.mail)

    async def account(
        self, *, pin: str | None = PIN, trusted: tuple[str, ...] = (TRUSTED,), **fields: object
    ) -> UUID:
        pin_hash = None if pin is None else await self.hasher.hash(pin)
        user_id = self.identity.add_account(pin_hash=pin_hash, **fields)  # type: ignore[arg-type]
        for device in trusted:
            self.identity.trust(user_id, device)
        return user_id

    def digest(self, value: str) -> str:
        return self.digests.digest(value)

    def sign_in(self, *, development_codes: bool = False) -> SignIn:
        return SignIn(
            self.identity,
            self.clock,
            pins=self.pins,
            digests=self.digests,
            secrets=self.secrets,
            tokens=self.tokens,
            delivery=self.delivery,
            development_codes=development_codes,
        )

    def verify_device(self, *, trust_days: int | None = None) -> VerifyDevice:
        return VerifyDevice(
            self.identity,
            self.clock,
            self.digests,
            self.secrets,
            self.tokens,
            delivery=self.delivery,
            trust_days=trust_days,
        )

    def request_code(self, *, development_codes: bool = False) -> RequestCode:
        return RequestCode(
            self.identity,
            self.clock,
            self.digests,
            self.secrets,
            self.delivery,
            development_codes=development_codes,
        )

    def verify_code(self) -> VerifyCode:
        return VerifyCode(self.identity, self.clock, self.digests, self.secrets, self.delivery)

    def complete_pin(self, *, trust_days: int | None = None) -> CompletePin:
        return CompletePin(
            self.identity,
            self.clock,
            pins=self.pins,
            digests=self.digests,
            secrets=self.secrets,
            device_tokens=self.device_tokens,
            tokens=self.tokens,
            trust_days=trust_days,
        )

    def start_sign_in(self, *, development_codes: bool = False) -> StartSignIn:
        return StartSignIn(
            self.identity,
            self.clock,
            digests=self.digests,
            secrets=self.secrets,
            device_tokens=self.device_tokens,
            delivery=self.delivery,
            development_codes=development_codes,
        )

    def enter_pin(self, *, development_codes: bool = False) -> EnterPin:
        return EnterPin(
            self.identity,
            self.clock,
            pins=self.pins,
            digests=self.digests,
            secrets=self.secrets,
            device_tokens=self.device_tokens,
            tokens=self.tokens,
            delivery=self.delivery,
            development_codes=development_codes,
        )

    def enter_code(self, *, trust_days: int | None = None) -> EnterCode:
        return EnterCode(
            self.identity,
            self.clock,
            digests=self.digests,
            secrets=self.secrets,
            device_tokens=self.device_tokens,
            tokens=self.tokens,
            delivery=self.delivery,
            trust_days=trust_days,
        )

    def change_pin(self) -> ChangePin:
        return ChangePin(self.identity, self.clock, pins=self.pins)

    def refresh(self) -> Refresh:
        return Refresh(self.identity, self.clock, self.digests, self.secrets, self.tokens)

    def sign_out(self) -> SignOut:
        return SignOut(self.identity, self.clock, self.digests)

    def revoke_device(self) -> RevokeDevice:
        return RevokeDevice(self.identity, self.clock)

    def resolve_session(self) -> ResolveSession:
        return ResolveSession(self.tokens, self.identity, self.clock)


@pytest.fixture
def kit() -> AuthKit:
    return AuthKit()
