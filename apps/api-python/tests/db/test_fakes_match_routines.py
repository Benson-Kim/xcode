"""``FakeIdentityRepository`` answers exactly as the ``api.auth_*`` routines do, and the
tenancy, setup, revenue and petty-cash fakes as theirs do on their parity cases.

Every case of ``tests/support/auth_cases.py`` runs against the fake and against
``IdentityRoutines`` on PostgreSQL. Each run must meet the case's stated outcome kind and
refusal, and the two observations (every outcome, plus the account state the calls changed)
must be equal: where they differ, the routine is right and the fake is wrong.
"""

from __future__ import annotations

import pytest
from psycopg_pool import AsyncConnectionPool

from xcode_api.application.repositories import (
    IdentityRepository,
    PettyCashRepository,
    RevenueRepository,
    SetupRepository,
    TenancyRepository,
)
from xcode_api.db.routines.identity import IdentityRoutines
from xcode_api.db.routines.pettycash import PettyCashRoutines
from xcode_api.db.routines.revenue import RevenueRoutines
from xcode_api.db.routines.setup import SetupRoutines
from xcode_api.db.routines.tenancy import TenancyRoutines

from ..support.auth_cases import (
    CASES,
    Case,
    DatabaseWorld,
    FakeWorld,
    Observation,
    World,
    standard,
)
from ..support.fakes import (
    FakeIdentityRepository,
    FakePettyCashRepository,
    FakeRevenueRepository,
    FakeSetupRepository,
    FakeTenancyRepository,
)
from ..support.pettycash_cases import CASES as PETTYCASH_CASES
from ..support.pettycash_cases import PettyCashCase
from ..support.pettycash_cases import database_world as pettycash_database_world
from ..support.pettycash_cases import fake_world as pettycash_fake_world
from ..support.revenue_cases import CASES as REVENUE_CASES
from ..support.revenue_cases import RevenueCase
from ..support.revenue_cases import database_world as revenue_database_world
from ..support.revenue_cases import fake_world as revenue_fake_world
from ..support.scenario import Conn
from ..support.setup_cases import CASES as SETUP_CASES
from ..support.setup_cases import SetupCase
from ..support.setup_cases import database_world as setup_database_world
from ..support.setup_cases import fake_world as setup_fake_world
from ..support.tenancy_cases import CASES as TENANCY_CASES
from ..support.tenancy_cases import TenancyCase, database_world, fake_world, normalised


async def _run(case: Case, world: World) -> Observation:
    await case.run(world)
    observation = await world.observe()
    assert observation.steps, f"{case.name} made no repository call"
    last = observation.last
    assert (last.kind, last.refusal) == (case.kind, case.refusal)
    if case.check is not None:
        case.check(observation)
    return observation


def test_the_table_covers_every_branch_with_unique_names() -> None:
    names = [case.name for case in CASES]
    assert len(names) == len(set(names))
    assert len(CASES) >= 40


def test_the_fake_is_an_identity_repository() -> None:
    assert isinstance(FakeIdentityRepository(), IdentityRepository)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_the_fake_meets_the_case(case: Case) -> None:
    await _run(case, FakeWorld())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
async def test_the_routines_meet_the_case_and_the_fake_observes_the_same(
    case: Case,
    pool: AsyncConnectionPool[object],
    owner_conn: Conn,
    operator_conn: Conn,
) -> None:
    routines = await _run(case, DatabaseWorld(IdentityRoutines(pool), operator_conn, owner_conn))
    fake = await _run(case, FakeWorld())
    assert fake == routines


async def test_the_fake_records_each_method_it_finishes() -> None:
    calls: list[str] = []
    world = FakeWorld(calls=calls)
    ref = await standard(world)
    await world.lookup()
    await world.sign_in(ref)
    await world.resolve(ref, version=1)
    await world.sign_out("missing")
    assert calls == ["account_lookup", "sign_in", "resolve_session", "sign_out"]


# --- tenancy: access, people, the change log and organization settings --------------------


def test_the_tenancy_fake_is_a_tenancy_repository() -> None:
    assert isinstance(FakeTenancyRepository(), TenancyRepository)


@pytest.mark.parametrize("case", TENANCY_CASES, ids=lambda case: case.name)
async def test_the_tenancy_fake_answers_as_the_routines_do(
    case: TenancyCase, pool: AsyncConnectionPool[object], operator_conn: Conn
) -> None:
    routines = database_world(TenancyRoutines(pool), operator_conn)
    await case.run(routines)
    fake = fake_world()
    await case.run(fake)
    assert routines.seen, f"{case.name} made no repository call"
    assert normalised(fake.seen) == normalised(routines.seen)


# --- setup: companies, vehicles, scheduled items, investment -----------------------------


def test_the_setup_fake_is_a_setup_repository() -> None:
    assert isinstance(FakeSetupRepository(), SetupRepository)


@pytest.mark.parametrize("case", SETUP_CASES, ids=lambda case: case.name)
async def test_the_setup_fake_answers_as_the_routines_do(
    case: SetupCase, pool: AsyncConnectionPool[object], operator_conn: Conn
) -> None:
    routines = setup_database_world(SetupRoutines(pool), TenancyRoutines(pool), operator_conn)
    await case.run(routines)
    fake = setup_fake_world()
    await case.run(fake)
    assert routines.seen, f"{case.name} made no repository call"
    assert normalised(fake.seen) == normalised(routines.seen)


# --- revenue: capture, the week grid, the dashboard ---------------------------------------


def test_the_revenue_fake_is_a_revenue_repository() -> None:
    assert isinstance(FakeRevenueRepository(), RevenueRepository)


@pytest.mark.parametrize("case", REVENUE_CASES, ids=lambda case: case.name)
async def test_the_revenue_fake_answers_as_the_routines_do(
    case: RevenueCase, pool: AsyncConnectionPool[object], operator_conn: Conn
) -> None:
    routines = revenue_database_world(
        RevenueRoutines(pool), SetupRoutines(pool), TenancyRoutines(pool), operator_conn
    )
    await case.run(routines)
    fake = revenue_fake_world()
    await case.run(fake)
    assert any(step[0] == "detail" for step in routines.seen if isinstance(step, tuple))
    assert normalised(fake.seen) == normalised(routines.seen)


# --- petty cash: entries, reviews, the overview, list, options and dashboard --------------


def test_the_pettycash_fake_is_a_pettycash_repository() -> None:
    assert isinstance(FakePettyCashRepository(), PettyCashRepository)


@pytest.mark.parametrize("case", PETTYCASH_CASES, ids=lambda case: case.name)
async def test_the_pettycash_fake_answers_as_the_routines_do(
    case: PettyCashCase, pool: AsyncConnectionPool[object], operator_conn: Conn
) -> None:
    routines = pettycash_database_world(
        PettyCashRoutines(pool), SetupRoutines(pool), TenancyRoutines(pool), operator_conn
    )
    await case.run(routines)
    fake = pettycash_fake_world()
    await case.run(fake)
    details = [step for step in routines.seen if isinstance(step, tuple) and step[0] == "detail"]
    assert any("current" in step[1] for step in details)
    assert any("balance_after" in step[1] for step in details)
    assert normalised(fake.seen) == normalised(routines.seen)
