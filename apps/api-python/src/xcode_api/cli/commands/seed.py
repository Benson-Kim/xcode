"""``xcode-api seed-demo``: the demo organization, development only, idempotent.

Connects as ``xcode_operator`` through ``XCODE_DATABASE_OPERATOR_URL`` (exit 2 when it is
unset) and refuses with exit 1 outside ``XCODE_ENV=development`` before connecting; the
routine checks the environment again. A refusal of the routine is recorded in
``ops.operator_actions`` like the user commands' (``docs/08-operability.md`` section 8).
"""

from __future__ import annotations

import argparse
import uuid

from psycopg_pool import PoolTimeout

from ...application.errors import TransientFailure
from ...application.ops.seed_demo import SeedDemo, SeedDemoCommand
from ...db.pool import open_operator_pool
from ...db.routines.ops import OpsRoutines
from ...domain.errors import DomainRefusal
from ...infra.clock import SystemClock
from ...security.pins import Pbkdf2PinHasher
from ...settings import SettingsError, load_cli_settings
from .db import resolve_operator
from .users import CONNECT_TIMEOUT_SECONDS, _record_refusal, _run

NAME = "seed-demo"
HELP = "seed the demo organization (development only; a second run changes nothing)"
DEMO_TARGET = "demo-fleet"


def configure(parser: argparse.ArgumentParser) -> None:
    del parser


def run(args: argparse.Namespace) -> int:
    del args
    try:
        settings = load_cli_settings()
    except SettingsError as exc:
        for message in exc.messages:
            print(message)
        return 2
    if not settings.is_development:
        print("refused: seed_development_only")
        return 1
    if not settings.database_operator_url:
        print(f"XCODE_DATABASE_OPERATOR_URL is required for {NAME}")
        return 2
    return _run(
        seed(
            settings.database_operator_url,
            resolve_operator(settings),
            settings.env.value,
            settings.auth_pin_iterations,
        )
    )


async def seed(url: str, operator: str, environment: str, pin_iterations: int) -> int:
    request_id = uuid.uuid4().hex
    pool = open_operator_pool(url)
    try:
        await pool.open(wait=True, timeout=CONNECT_TIMEOUT_SECONDS)
    except PoolTimeout:
        print("could not connect to the database as the operator")
        await pool.close()
        return 1
    try:
        ops = OpsRoutines(pool)
        use_case = SeedDemo(ops, SystemClock(), Pbkdf2PinHasher(pin_iterations))
        try:
            seeded = await use_case.execute(SeedDemoCommand(operator, request_id, environment))
        except DomainRefusal as refusal:
            await _record_refusal(
                ops,
                operator=operator,
                action=NAME,
                email=DEMO_TARGET,
                refusal=refusal,
                request_id=request_id,
            )
            print(f"refused: {refusal.code}")
            return 1
        except TransientFailure:
            print("the database is not available right now")
            return 1
        created = "yes" if seeded.created else "no"
        print(f"organization_id={seeded.organization_id} created={created}")
        return 0
    finally:
        await pool.close()
