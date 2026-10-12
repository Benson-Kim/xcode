"""``GetSession``: the verified claims echoed, permissions in token order."""

from __future__ import annotations

from uuid import uuid4

from xcode_api.application.auth.get_session import GetSession, GetSessionQuery
from xcode_api.domain.identity import SessionView, TokenClaims


async def test_the_claims_are_echoed_in_token_order() -> None:
    user_id = uuid4()
    claims = TokenClaims(
        user_id=user_id,
        device_id="phone-1",
        security_version=2,
        organization_id=uuid4(),
        role="Fleet manager",
        first_name="Jane",
        last_name="Doe",
        permissions=("revenue.view", "dash.float", "revenue.capture"),
    )
    view = await GetSession().execute(GetSessionQuery(claims))
    assert view == SessionView(
        user_id=user_id,
        first_name="Jane",
        last_name="Doe",
        role="Fleet manager",
        permissions=("revenue.view", "dash.float", "revenue.capture"),
    )
