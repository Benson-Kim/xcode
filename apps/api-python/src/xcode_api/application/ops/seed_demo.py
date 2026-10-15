"""Seed the demo organization (development only; ``db/seeds/README.md``).

The PINs of the demo logins are the .NET ``DemoSeed`` ones; they are hashed here, as every
PIN is, and the routine stores a hash only on a user it creates, so a PIN changed during
development survives a reseed. The routine refuses any environment but development
itself; the CLI and the settings refuse earlier.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.identity import DemoSeeding, SeededDemo
from ..ports import Clock, PinHasher
from ..repositories import OpsRepository

DEMO_PINS = {
    "antony.maina@shamayah.co.ke": "4826",
    "peter.otieno@zurigenesis.co.ke": "1379",
    "wanjiru.kamau@zurigenesis.co.ke": "2580",
}


@dataclass(frozen=True, slots=True)
class SeedDemoCommand:
    operator: str
    request_id: str
    environment: str


class SeedDemo:
    def __init__(self, ops: OpsRepository, clock: Clock, pins: PinHasher) -> None:
        self._ops = ops
        self._clock = clock
        self._pins = pins

    async def execute(self, command: SeedDemoCommand) -> SeededDemo:
        hashes = {email: await self._pins.hash(pin) for email, pin in DEMO_PINS.items()}
        return await self._ops.seed_demo(
            DemoSeeding(
                operator=command.operator,
                request_id=command.request_id,
                environment=command.environment,
                pin_hashes=hashes,
                now=self._clock.now(),
            )
        )
