"""PIN hashing with the .NET parameters: format, verification, malformed stored values, the
dummy hash, the full iteration count proven against an independent derivation, and the
bounded pool that keeps a burst of sign-ins from growing the process's threads."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import subprocess
import sys
import threading
from collections.abc import Callable

import pytest

from xcode_api.application.errors import IntegrityBug, TransientFailure
from xcode_api.security.pins import (
    DUMMY_PIN,
    KEY_BYTES,
    PIN_ITERATIONS,
    PIN_WAITING,
    PIN_WORKERS,
    SALT_BYTES,
    Pbkdf2PinHasher,
)

LOW = 1_000

# RFC 7914 section 11: PBKDF2-HMAC-SHA256, P="passwd", S="salt", c=1, first 32 bytes.
RFC_7914_KEY = bytes.fromhex("55ac046e56e3089fec1691c22544b605f94185216dde0465e68b9d57c20dacbc")


def _stored(pin: str, salt: bytes, iterations: int) -> str:
    key = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations, KEY_BYTES)
    return f"{base64.b64encode(salt).decode()}.{base64.b64encode(key).decode()}"


def test_parameters_are_the_dotnet_ones() -> None:
    assert PIN_ITERATIONS == 210_000
    assert SALT_BYTES == 16
    assert KEY_BYTES == 32
    assert DUMMY_PIN == "5826"


async def test_known_answer_vector() -> None:
    stored = f"{base64.b64encode(b'salt').decode()}.{base64.b64encode(RFC_7914_KEY).decode()}"
    hasher = Pbkdf2PinHasher(1)
    assert await hasher.verify("passwd", stored) is True
    assert await hasher.verify("passwe", stored) is False


async def test_hash_format_is_base64_salt_dot_base64_key() -> None:
    hasher = Pbkdf2PinHasher(LOW)
    stored = await hasher.hash("5826")
    salt_text, key_text = stored.split(".")
    salt = base64.b64decode(salt_text, validate=True)
    key = base64.b64decode(key_text, validate=True)
    assert len(salt) == SALT_BYTES
    assert len(key) == KEY_BYTES
    assert stored == _stored("5826", salt, LOW)
    assert await hasher.hash("5826") != stored


async def test_verify_accepts_the_pin_and_refuses_another() -> None:
    hasher = Pbkdf2PinHasher(LOW)
    stored = await hasher.hash("5826")
    assert await hasher.verify("5826", stored) is True
    assert await hasher.verify("5827", stored) is False
    assert await hasher.verify("", stored) is False


async def test_a_key_of_another_length_never_matches() -> None:
    salt = b"s" * SALT_BYTES
    short = f"{base64.b64encode(salt).decode()}.{base64.b64encode(b'k' * 16).decode()}"
    assert await Pbkdf2PinHasher(LOW).verify("5826", short) is False


@pytest.mark.parametrize(
    "stored",
    ["", "nodot", "a.b.c", "!!!!.AAAA", "AAAA.!!!!", "AAA.AAAA"],
)
async def test_a_malformed_stored_value_raises_integrity_bug(stored: str) -> None:
    with pytest.raises(IntegrityBug) as caught:
        await Pbkdf2PinHasher(LOW).verify("5826", stored)
    assert "5826" not in str(caught.value)


async def test_dummy_hash_is_the_dummy_pin_and_computed_once() -> None:
    hasher = Pbkdf2PinHasher(LOW)
    first = hasher.dummy_hash
    assert await hasher.verify(DUMMY_PIN, first) is True
    assert await hasher.dummy_verify(DUMMY_PIN) is True
    assert await hasher.dummy_verify("1234") is False
    assert hasher.dummy_hash == first


def test_dummy_hash_differs_per_process() -> None:
    script = (
        "from xcode_api.security.pins import Pbkdf2PinHasher; print(Pbkdf2PinHasher(1).dummy_hash)"
    )
    hashes = {
        subprocess.run(  # noqa: S603 - the interpreter running the tests, a fixed script
            [sys.executable, "-c", script], capture_output=True, text=True, check=True
        ).stdout.strip()
        for _ in range(2)
    }
    assert len(hashes) == 2


@pytest.mark.slow
async def test_the_full_count_matches_an_independent_derivation_off_the_event_loop() -> None:
    salt = b"0123456789abcdef"
    stored = _stored("5826", salt, PIN_ITERATIONS)
    hasher = Pbkdf2PinHasher()
    assert hasher.iterations == PIN_ITERATIONS

    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.005)
            ticks += 1

    task = asyncio.create_task(ticker())
    try:
        assert await hasher.verify("5826", stored) is True
    finally:
        task.cancel()
    assert ticks > 3, "the derivation blocked the event loop"
    assert await Pbkdf2PinHasher(LOW).verify("5826", stored) is False


class _GatedHasher(Pbkdf2PinHasher):
    """Each derivation reports that it started and then waits for ``gate``, so a test decides
    how long the workers stay busy. Construction derives the dummy hash with the gate open."""

    def __init__(self, *, workers: int, waiting: int) -> None:
        self.gate = threading.Event()
        self.started = threading.Event()
        self.gate.set()
        super().__init__(LOW, workers=workers, waiting=waiting)
        self.gate.clear()
        self.started.clear()

    def _derive(self, pin: str, salt: bytes) -> bytes:
        self.started.set()
        self.gate.wait(timeout=10)
        return super()._derive(pin, salt)


async def _until(condition: Callable[[], bool]) -> None:
    for _ in range(2_000):
        if condition():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("the condition was never reached")


STORED_LOW = _stored("5826", b"s" * SALT_BYTES, LOW)


def test_the_pool_is_two_threads_with_sixteen_waiting() -> None:
    assert (PIN_WORKERS, PIN_WAITING) == (2, 16)


@pytest.mark.parametrize(("workers", "waiting"), [(0, 1), (-1, 0), (1, -1)])
def test_pool_sizes_are_validated(workers: int, waiting: int) -> None:
    with pytest.raises(ValueError, match="workers"):
        Pbkdf2PinHasher(LOW, workers=workers, waiting=waiting)


async def test_a_burst_runs_on_a_bounded_pool_and_the_overflow_is_refused() -> None:
    before = set(threading.enumerate())
    hasher = _GatedHasher(workers=2, waiting=3)
    tasks = [asyncio.create_task(hasher.verify("5826", STORED_LOW)) for _ in range(100)]
    await asyncio.sleep(0)

    admitted = [t for t in tasks if not t.done()]
    refused = [t for t in tasks if t.done()]
    assert len(admitted) == 5
    assert all(isinstance(t.exception(), TransientFailure) for t in refused)

    hasher.gate.set()
    assert await asyncio.gather(*admitted) == [True] * 5
    new_threads = [t for t in threading.enumerate() if t not in before]
    assert new_threads, "the derivations ran on no thread of the hasher's own"
    assert all(t.name.startswith("pin-hash") for t in new_threads), new_threads
    assert len(new_threads) <= 2

    again = await asyncio.gather(*(hasher.verify("5826", STORED_LOW) for _ in range(5)))
    assert again == [True] * 5, "the slots came back once the derivations ended"


async def test_a_running_derivation_keeps_its_slot_after_its_caller_leaves() -> None:
    hasher = _GatedHasher(workers=1, waiting=0)
    running = asyncio.create_task(hasher.verify("5826", STORED_LOW))
    await _until(hasher.started.is_set)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    with pytest.raises(TransientFailure):
        await hasher.verify("5826", STORED_LOW)

    hasher.gate.set()
    admitted = False
    for _ in range(2_000):
        try:
            admitted = await hasher.verify("5826", STORED_LOW)
            break
        except TransientFailure:
            await asyncio.sleep(0.005)
    assert admitted is True


async def test_a_queued_derivation_frees_its_slot_when_its_caller_leaves() -> None:
    hasher = _GatedHasher(workers=1, waiting=1)
    running = asyncio.create_task(hasher.verify("5826", STORED_LOW))
    await _until(hasher.started.is_set)
    queued = asyncio.create_task(hasher.verify("5826", STORED_LOW))
    await asyncio.sleep(0)
    with pytest.raises(TransientFailure):
        await hasher.verify("5826", STORED_LOW)

    queued.cancel()
    with pytest.raises(asyncio.CancelledError):
        await queued
    third = asyncio.create_task(hasher.verify("5826", STORED_LOW))
    await asyncio.sleep(0)
    assert not third.done(), "the cancelled queued derivation still held its slot"

    hasher.gate.set()
    assert await running is True
    assert await third is True


async def test_hashing_a_new_pin_is_refused_the_same_way_at_capacity() -> None:
    hasher = _GatedHasher(workers=1, waiting=0)
    running = asyncio.create_task(hasher.hash("5826"))
    await _until(hasher.started.is_set)
    with pytest.raises(TransientFailure):
        await hasher.hash("2468")
    with pytest.raises(TransientFailure):
        await hasher.dummy_verify("2468")
    hasher.gate.set()
    assert await hasher.verify("5826", await running) is True
