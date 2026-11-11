"""The periodic job behind the invitation sweep: interval, failure isolation, stop."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import pytest
from structlog.testing import capture_logs

from xcode_api import main
from xcode_api.infra.periodic import PeriodicJob

TICK = 0.01


async def _until(predicate: Callable[[], bool], budget: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + budget
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(TICK)


async def test_runs_after_one_interval_not_at_start() -> None:
    runs: list[int] = []

    async def job() -> None:
        runs.append(1)

    periodic = PeriodicJob("probe", 60.0, job)
    periodic.start()
    await asyncio.sleep(TICK * 3)
    assert runs == []
    assert periodic.running
    await periodic.stop()
    assert not periodic.running


async def test_runs_repeatedly() -> None:
    runs: list[int] = []

    async def job() -> None:
        runs.append(1)

    periodic = PeriodicJob("probe", TICK, job)
    periodic.start()
    await _until(lambda: len(runs) >= 3)
    await periodic.stop()


async def test_a_failed_run_is_logged_and_the_next_still_runs() -> None:
    runs: list[int] = []

    async def job() -> None:
        runs.append(1)
        if len(runs) == 1:
            raise RuntimeError("database away")

    periodic = PeriodicJob("probe", TICK, job)
    with capture_logs() as logs:
        periodic.start()
        await _until(lambda: len(runs) >= 2)
        await periodic.stop()
    failed = [e for e in logs if e["event"] == "job.failed"]
    assert failed == [
        {"event": "job.failed", "job": "probe", "error": "RuntimeError", "log_level": "error"}
    ]


async def test_stop_cancels_a_run_in_progress() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def job() -> None:
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    periodic = PeriodicJob("probe", TICK, job)
    periodic.start()
    await asyncio.wait_for(started.wait(), 2)
    await periodic.stop()
    assert cancelled.is_set()
    assert not periodic.running


async def test_runs_never_overlap() -> None:
    active = 0
    most = 0
    runs = 0

    async def job() -> None:
        nonlocal active, most, runs
        active += 1
        most = max(most, active)
        await asyncio.sleep(TICK * 3)
        active -= 1
        runs += 1

    periodic = PeriodicJob("probe", TICK, job)
    periodic.start()
    await _until(lambda: runs >= 3)
    await periodic.stop()
    assert most == 1


async def test_stop_without_start_and_twice_is_harmless() -> None:
    async def job() -> None:
        return None

    periodic = PeriodicJob("probe", TICK, job)
    await periodic.stop()
    periodic.start()
    periodic.start()
    await periodic.stop()
    await periodic.stop()
    assert not periodic.running


@pytest.mark.parametrize("interval", [0, -1.0])
def test_interval_must_be_positive(interval: float) -> None:
    async def job() -> None:
        return None

    with pytest.raises(ValueError, match="positive"):
        PeriodicJob("probe", interval, job)


async def test_the_sweep_asks_for_its_limit_and_logs_only_a_claim() -> None:
    limits: list[int] = []
    counts = [0, 2]

    async def sweep(limit: int) -> int:
        limits.append(limit)
        return counts.pop(0)

    container = cast(Any, SimpleNamespace(invitation_delivery=SimpleNamespace(sweep=sweep)))
    with capture_logs() as logs:
        await main._sweep_invitations(container)
        await main._sweep_invitations(container)
    assert limits == [main.INVITATION_SWEEP_LIMIT] * 2
    assert [e for e in logs if e["event"] == "invitation.sweep"] == [
        {"event": "invitation.sweep", "claimed": 2, "log_level": "info"}
    ]
