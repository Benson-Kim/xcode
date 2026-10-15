"""Record a vehicle's revenue, or a no-earnings reason, for one day; the phones replay their
offline queue through the same call."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ...domain.revenue import CaptureResult, RevenueCapture
from ..caller import Caller
from ..ports import Clock
from ..repositories import RevenueRepository


@dataclass(frozen=True, slots=True)
class CaptureRevenueCommand:
    caller: Caller
    vehicle_id: UUID
    day: date
    amount: Decimal | None
    reason: str | None
    note: str | None
    version: int | None
    captured_at: datetime | None = None


class CaptureRevenue:
    def __init__(self, revenue: RevenueRepository, clock: Clock) -> None:
        self._revenue = revenue
        self._clock = clock

    async def execute(self, command: CaptureRevenueCommand) -> CaptureResult:
        return await self._revenue.capture(
            RevenueCapture(
                command.caller.context(self._clock),
                command.vehicle_id,
                command.day,
                command.amount,
                command.reason,
                command.note,
                command.version,
                command.captured_at,
            )
        )
