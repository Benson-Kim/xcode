"""Manual clock for time-controlled tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

FIXED_INSTANT = datetime(2026, 10, 7, 9, 0, 0, tzinfo=UTC)


class ManualClock:
    def __init__(self, start: datetime = FIXED_INSTANT) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
