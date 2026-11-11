"""``xcode-api review-account create``: the App Review login of the demo organization.

Unlike the other operator commands it validates the API's full ``Settings``: the fixed code
is stored as the keyed digest the API computes, so ``XCODE_AUTH_SIGNING_KEY`` must be the
API's own (exit 2 when it is unset), and a run after that key changes is needed for the
code to work again. Connects as ``xcode_operator`` through ``XCODE_DATABASE_OPERATOR_URL``
(exit 2 when unset). The login lives in the organization flagged as demo, which the first
run creates with made-up data when there is none; a refusal is recorded in
``ops.operator_actions`` and exits 1. The PIN and code are printed once, on
stdout, and never logged (``docs/08-operability.md`` section 8).
"""

from __future__ import annotations

import argparse
import uuid

from psycopg_pool import PoolTimeout

from ...application.errors import TransientFailure
from ...application.ops.create_review_account import (
    CreateReviewAccount,
    CreateReviewAccountCommand,
    ReviewAccount,
)
from ...db.pool import open_operator_pool
from ...db.routines.ops import OpsRoutines
from ...domain.errors import DomainRefusal
from ...infra.clock import SystemClock
from ...security.codes import new_pin
from ...security.digests import KeyedDigester
from ...security.pins import Pbkdf2PinHasher
from ...security.secret_source import RandomSecretSource
from ...settings import Settings, SettingsError, load_settings
from .db import resolve_operator
from .users import CONNECT_TIMEOUT_SECONDS, _record_refusal, _run

NAME = "review-account"
HELP = "create or renew the App Review login of the demo organization"
CREATE = "create"


def configure(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser(
        CREATE, help="a new PIN and fixed code for the login; the old ones stop working"
    )
    create.add_argument("--email", required=True)
    create.add_argument("--phone", required=True)


def run(args: argparse.Namespace) -> int:
    try:
        settings = load_settings()
    except SettingsError as exc:
        for message in exc.messages:
            print(message)
        return 2
    if not settings.database_operator_url:
        print(f"XCODE_DATABASE_OPERATOR_URL is required for {NAME}")
        return 2
    if settings.auth_signing_key_generated:
        print(f"XCODE_AUTH_SIGNING_KEY is required for {NAME}: the API digests codes with it")
        return 2
    return _run(create(settings, args.email, args.phone))


async def create(settings: Settings, email: str, phone: str) -> int:
    operator = resolve_operator(settings)
    request_id = uuid.uuid4().hex
    pool = open_operator_pool(settings.database_operator_url)
    try:
        await pool.open(wait=True, timeout=CONNECT_TIMEOUT_SECONDS)
    except PoolTimeout:
        print("could not connect to the database as the operator")
        await pool.close()
        return 1
    try:
        ops = OpsRoutines(pool)
        use_case = CreateReviewAccount(
            ops,
            SystemClock(),
            pins=Pbkdf2PinHasher(settings.auth_pin_iterations),
            codes=KeyedDigester(settings.auth_signing_key),
            secret_source=RandomSecretSource(),
            new_pin=new_pin,
        )
        command = CreateReviewAccountCommand(operator, request_id, email=email, phone=phone)
        try:
            review = await use_case.execute(command)
        except DomainRefusal as refusal:
            await _record_refusal(
                ops,
                operator=operator,
                action=NAME,
                email=email,
                refusal=refusal,
                request_id=request_id,
            )
            print(f"refused: {refusal.code}")
            return 1
        except TransientFailure:
            print("the database is not available right now")
            return 1
        print(_report(review))
        return 0
    finally:
        await pool.close()


def _report(review: ReviewAccount) -> str:
    created = "yes" if review.account.created_user else "no"
    organization = "yes" if review.account.created_organization else "no"
    return (
        f"user_id={review.account.user_id} organization_id={review.account.organization_id} "
        f"created_user={created} created_organization={organization}\n"
        f"pin={review.pin} code={review.code}\n"
        "Give both to App Review only: the code answers the new-device step after the PIN. "
        "A second run replaces both."
    )
