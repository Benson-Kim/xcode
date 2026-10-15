from __future__ import annotations

from xcode_api.application.ops.check_readiness import CheckReadiness
from xcode_api.db.contract import EXPECTED_CONTRACT_VERSION

from ..support.fakes import FakeOpsRepository

EXPECTED = EXPECTED_CONTRACT_VERSION


def _use_case(ops: FakeOpsRepository, **kwargs: float) -> CheckReadiness:
    return CheckReadiness(ops, expected_contract_version=EXPECTED, **kwargs)


async def test_healthy_database_with_matching_contract_is_ready() -> None:
    report = await _use_case(FakeOpsRepository(healthy=True)).execute()
    assert report.ready is True
    assert report.reason is None


async def test_failing_database_is_not_ready_and_does_not_raise() -> None:
    report = await _use_case(FakeOpsRepository(healthy=False)).execute()
    assert report.ready is False
    assert report.reason


async def test_slow_database_times_out_within_budget() -> None:
    ops = FakeOpsRepository(ping_delay_seconds=0.2)
    report = await _use_case(ops, budget_seconds=0.05).execute()
    assert report.ready is False
    assert "timed out" in (report.reason or "")


async def test_contract_version_mismatch_is_not_ready() -> None:
    report = await _use_case(FakeOpsRepository(contract_version=EXPECTED + 1)).execute()
    assert report.ready is False
    assert "contract version" in (report.reason or "")


async def test_ping_and_contract_version_are_both_consulted() -> None:
    ops = FakeOpsRepository()
    await _use_case(ops).execute()
    assert ops.ping_calls == 1
    assert ops.contract_version_calls == 1
