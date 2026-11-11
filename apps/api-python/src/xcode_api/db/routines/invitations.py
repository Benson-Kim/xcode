"""``InvitationRoutines``: the real ``InvitationRepository``, over the three invitation outbox
routines. None is retried: each counts a delivery attempt."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg_pool import AsyncConnectionPool

from ...application.errors import IntegrityBug
from ...domain.invitations import PendingInvitation
from ..session import call

_FIELDS = frozenset(
    {
        "invitation_id",
        "email",
        "first_name",
        "organization_name",
        "inviter_name",
        "support_email",
        "expires_at",
        "time_zone",
    }
)


class InvitationRoutines:
    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    async def start_delivery(self, token_hash: str, now: datetime) -> PendingInvitation | None:
        routine = "invite_delivery_start"
        value = _value(await call(self._pool, routine, token_hash, now), routine)
        return None if value is None else pending_invitation(value, routine, paired=False)

    async def record_delivery(self, token_hash: str, sent: bool, now: datetime) -> None:
        await call(self._pool, "invite_delivery_result", token_hash, sent, now)

    async def claim_undelivered(
        self, now: datetime, limit: int, token_hashes: list[str], code_hashes: list[str]
    ) -> list[PendingInvitation]:
        routine = "invite_claim_undelivered"
        value = _value(
            await call(self._pool, routine, now, limit, token_hashes, code_hashes), routine
        )
        if not isinstance(value, list):
            raise IntegrityBug(f"api.{routine} returned no array")
        return [pending_invitation(item, routine, paired=True) for item in value]


def pending_invitation(document: Any, source: str, *, paired: bool) -> PendingInvitation:
    """One delivery document to :class:`PendingInvitation`; any drift in its keys is a bug."""
    expected = _FIELDS | {"pair_index"} if paired else _FIELDS
    if not isinstance(document, Mapping) or set(document) != expected:
        raise IntegrityBug(f"api.{source} drifted from the invitation delivery shape")
    return PendingInvitation(
        invitation_id=UUID(document["invitation_id"]),
        email=document["email"],
        first_name=document["first_name"] or "",
        organization_name=document["organization_name"],
        inviter_name=document["inviter_name"],
        support_email=document["support_email"],
        expires_at=datetime.fromisoformat(document["expires_at"]),
        time_zone=document["time_zone"],
        pair_index=int(document["pair_index"]) if paired else None,
    )


def _value(rows: list[dict[str, Any]], routine: str) -> Any:
    if len(rows) != 1 or routine not in rows[0]:
        raise IntegrityBug(f"api.{routine} returned no single value")
    return rows[0][routine]
