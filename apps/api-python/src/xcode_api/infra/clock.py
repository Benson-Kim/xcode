"""System clock adapter."""

from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    """The real clock. ``now()`` returns a timezone-aware UTC ``datetime``.

    Tests use ``ManualClock`` from ``tests/support`` instead.
    """

    def now(self) -> datetime:
        return datetime.now(UTC)
