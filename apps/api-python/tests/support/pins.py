"""PIN hashers for the HTTP tests. ``HasherAtCapacity`` refuses every derivation with
``TransientFailure``, as ``Pbkdf2PinHasher`` refuses one past its workers and queue, to prove
that a full hasher stops a request before any decision routine runs. ``HasherWithPause`` runs
a test's coroutine just before a real verification, which is where a sign-in waits between
its lookup and its decision routine."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from xcode_api.application.errors import TransientFailure
from xcode_api.security.pins import Pbkdf2PinHasher


class HasherAtCapacity(Pbkdf2PinHasher):
    async def hash(self, pin: str) -> str:
        raise TransientFailure("PIN hashing is at capacity")

    async def verify(self, pin: str, stored: str) -> bool:
        raise TransientFailure("PIN hashing is at capacity")


class HasherWithPause(Pbkdf2PinHasher):
    def __init__(self, iterations: int) -> None:
        super().__init__(iterations)
        self.before_verify: Callable[[], Awaitable[None]] | None = None

    async def verify(self, pin: str, stored: str) -> bool:
        pause, self.before_verify = self.before_verify, None
        if pause is not None:
            await pause()
        return await super().verify(pin, stored)
