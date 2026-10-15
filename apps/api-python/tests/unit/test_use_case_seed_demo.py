"""``SeedDemo``: the demo PINs reach the routine only as hashes that verify, the environment is
passed through for the routine's own check, and a refusal comes back as the domain one."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from xcode_api.application.ops.seed_demo import DEMO_PINS, SeedDemo, SeedDemoCommand
from xcode_api.domain.errors import Forbidden
from xcode_api.security.pins import Pbkdf2PinHasher

from ..support.clock import ManualClock
from ..support.fakes import FakeOpsRepository

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


async def test_the_demo_pins_are_sent_hashed_and_verify() -> None:
    ops = FakeOpsRepository()
    pins = Pbkdf2PinHasher(1)
    seeded = await SeedDemo(ops, ManualClock(NOW), pins).execute(
        SeedDemoCommand("dev", "request-1", "development")
    )
    assert seeded.created is True
    assert set(ops.demo_pin_hashes) == set(DEMO_PINS)
    for email, pin in DEMO_PINS.items():
        stored = ops.demo_pin_hashes[email]
        assert pin not in stored
        assert await pins.verify(pin, stored)
    again = await SeedDemo(ops, ManualClock(NOW), pins).execute(
        SeedDemoCommand("dev", "request-2", "development")
    )
    assert again.created is False
    assert [a["action"] for a in ops.operator_actions] == ["seed-demo", "seed-demo"]


@pytest.mark.parametrize("environment", ["testing", "production"])
async def test_outside_development_the_refusal_is_the_routines(environment: str) -> None:
    ops = FakeOpsRepository()
    with pytest.raises(Forbidden) as refusal:
        await SeedDemo(ops, ManualClock(NOW), Pbkdf2PinHasher(1)).execute(
            SeedDemoCommand("dev", "request-1", environment)
        )
    assert refusal.value.code == "seed_development_only"
    assert ops.demo_seeded is False
