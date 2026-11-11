"""Invitations: a person added without a PIN gets a link token and a six-digit code by email.
Only their digests reach the database; the raw values exist once, in the message."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from .identity import SignInRefusal


@dataclass(frozen=True, slots=True)
class InvitationHashes:
    """The stored form of an invitation's secrets: the SHA-256 of the link token and the keyed
    digest of the code, both upper-case hex."""

    token_hash: str
    code_hash: str


@dataclass(frozen=True, slots=True)
class PendingInvitation:
    """What one invitation email needs, from ``api.invite_delivery_start`` or one element of
    ``api.invite_claim_undelivered`` (which adds ``pair_index``, the hash pair it was given)."""

    invitation_id: UUID
    email: str = field(repr=False)
    first_name: str
    organization_name: str
    inviter_name: str | None
    support_email: str | None = field(repr=False)
    expires_at: datetime
    time_zone: str
    pair_index: int | None = None


@dataclass(frozen=True, slots=True)
class InvitationRedeem:
    """``api.auth_invite_redeem``: the link's token digest, the number the person typed, and
    the digest of the server-made first-setup code to store for this device."""

    request_id: str
    token_hash: str
    phone: str = field(repr=False)
    device_id: str
    code_hash: str
    now: datetime


class InviteProblem(StrEnum):
    """Why a redeem was refused, told only once both the token and the number matched."""

    EXPIRED = "expired"
    USED = "used"
    REVOKED = "revoked"


_PROBLEMS = MappingProxyType(
    {
        SignInRefusal.INVITE_EXPIRED: InviteProblem.EXPIRED,
        SignInRefusal.INVITE_USED: InviteProblem.USED,
        SignInRefusal.INVITE_REVOKED: InviteProblem.REVOKED,
    }
)


def invite_problem(refusal: SignInRefusal | None) -> InviteProblem | None:
    """The problem a refusal may tell; ``invite_invalid`` (unknown token, wrong number or
    another person's token) and every other refusal tell nothing."""
    return None if refusal is None else _PROBLEMS.get(refusal)
