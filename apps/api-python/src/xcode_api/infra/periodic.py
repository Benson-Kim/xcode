"""A job the process runs on a fixed interval while it serves (the invitation sweep)."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

import structlog

logger = structlog.get_logger("xcode_api.periodic")


class PeriodicJob:
    """Runs ``job`` every ``interval_seconds`` on the event loop, first after one interval,
    until :meth:`stop`. A failed run logs ``job.failed`` and the next run still happens; a
    run never overlaps the one before it. Safe on several instances only when the job is
    (the invitation sweep claims with ``SKIP LOCKED``)."""

    def __init__(
        self, name: str, interval_seconds: float, job: Callable[[], Awaitable[object]]
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._name = name
        self._interval = interval_seconds
        self._job = job
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"periodic:{self._name}")

    async def stop(self) -> None:
        """Cancel the loop, including a run in progress; the job must tolerate that."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self._job()
            except Exception as exc:
                logger.error("job.failed", job=self._name, error=type(exc).__name__)
