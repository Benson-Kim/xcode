"""``GET /auth/session``: the verified token's own claims, echoed (the one place claims are
read back; authorization never relies on them)."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.identity import SessionView, TokenClaims


@dataclass(frozen=True, slots=True)
class GetSessionQuery:
    claims: TokenClaims


class GetSession:
    async def execute(self, query: GetSessionQuery) -> SessionView:
        claims = query.claims
        return SessionView(
            user_id=claims.user_id,
            first_name=claims.first_name,
            last_name=claims.last_name,
            role=claims.role,
            permissions=claims.permissions,
        )
