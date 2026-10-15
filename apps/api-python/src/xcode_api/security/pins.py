"""PIN hashing with the .NET parameters (``docs/07-auth.md`` section 1).

PBKDF2-HMAC-SHA256 over the UTF-8 PIN, 16-byte random salt, 32-byte key, stored as
``base64(salt) + "." + base64(key)`` with padding and compared in constant time. The dummy
hash (of ``5826``, with a fresh salt) is computed once per hasher, which the container
builds once per process.

Derivations run on the hasher's own pool of ``PIN_WORKERS`` threads, never on asyncio's
default executor, so the event loop is never blocked and a burst of sign-ins cannot grow
the process's thread count (a shared host caps threads per account). At most
``PIN_WORKERS + PIN_WAITING`` derivations are admitted at once; past that the hasher raises
``TransientFailure`` (503 with ``Retry-After``) instead of queueing. A slot is freed when its
derivation ends, not when its caller gives up, so cancelled requests cannot pile up work.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import secrets
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from ..application.errors import IntegrityBug, TransientFailure

PIN_ITERATIONS = 210_000
SALT_BYTES = 16
KEY_BYTES = 32
DUMMY_PIN = "5826"
PIN_WORKERS = 2
PIN_WAITING = 16


class Pbkdf2PinHasher:
    __slots__ = ("_admitted", "_capacity", "_dummy_hash", "_executor", "_iterations", "_lock")

    def __init__(
        self,
        iterations: int = PIN_ITERATIONS,
        *,
        workers: int = PIN_WORKERS,
        waiting: int = PIN_WAITING,
    ) -> None:
        if iterations <= 0:
            raise ValueError("iterations must be positive")
        if workers <= 0 or waiting < 0:
            raise ValueError("workers must be positive and waiting must not be negative")
        self._iterations = iterations
        self._capacity = workers + waiting
        self._admitted = 0
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pin-hash")
        self._dummy_hash = self._hash_now(DUMMY_PIN)

    @property
    def iterations(self) -> int:
        return self._iterations

    @property
    def dummy_hash(self) -> str:
        return self._dummy_hash

    async def hash(self, pin: str) -> str:
        return await self._run(self._hash_now, pin)

    async def verify(self, pin: str, stored: str) -> bool:
        salt, expected = _split(stored)
        return await self._run(self._matches, pin, salt, expected)

    async def _run[T](self, work: Callable[..., T], *args: object) -> T:
        with self._lock:
            if self._admitted >= self._capacity:
                raise TransientFailure("PIN hashing is at capacity")
            self._admitted += 1
        try:
            future = self._executor.submit(work, *args)
        except BaseException:
            self._release()
            raise
        future.add_done_callback(self._release)
        return await asyncio.wrap_future(future)

    def _release(self, _future: object = None) -> None:
        with self._lock:
            self._admitted -= 1

    async def dummy_verify(self, pin: str) -> bool:
        return await self.verify(pin, self._dummy_hash)

    def _derive(self, pin: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, self._iterations, KEY_BYTES)

    def _hash_now(self, pin: str) -> str:
        salt = secrets.token_bytes(SALT_BYTES)
        key = self._derive(pin, salt)
        return f"{base64.b64encode(salt).decode('ascii')}.{base64.b64encode(key).decode('ascii')}"

    def _matches(self, pin: str, salt: bytes, expected: bytes) -> bool:
        return hmac.compare_digest(self._derive(pin, salt), expected)


def _split(stored: str) -> tuple[bytes, bytes]:
    parts = stored.split(".")
    if len(parts) != 2:
        raise IntegrityBug("stored PIN hash is not salt.key")
    try:
        salt = base64.b64decode(parts[0], validate=True)
        key = base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError):
        raise IntegrityBug("stored PIN hash is not Base64") from None
    return salt, key
