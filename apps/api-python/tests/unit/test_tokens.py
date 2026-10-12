"""Access tokens: the exact header and claims, issue-time lifetimes, previous-key
verification, and every tampering refused."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest

from xcode_api.domain.errors import SessionInvalid
from xcode_api.domain.identity import AccessGrant, TokenClaims
from xcode_api.security.tokens import JwtTokenIssuer

KEY = "a-signing-key-of-at-least-32-bytes!!"
OLD_KEY = "the-previous-signing-key-32-bytes-or-more"
OTHER_KEY = "an-unrelated-key-of-32-bytes-or-more!!"
NOW = datetime(2026, 10, 7, 9, 0, 0, 750_000, tzinfo=UTC)
ISSUED = 1_791_363_600  # NOW in whole seconds
USER = UUID("3f2b8c1e-5d4a-4b6f-9a0c-1e2d3c4b5a69")
ORG = UUID("9b1d7c2a-0e4f-4a6b-8c3d-2e1f0a9b8c7d")


def _grant(permissions: tuple[str, ...] = ("revenue.view", "revenue.capture")) -> AccessGrant:
    return AccessGrant(
        user_id=USER,
        device_id="phone-1",
        security_version=3,
        organization_id=ORG,
        role="Owner",
        first_name="Jane",
        last_name="Doe",
        permissions=permissions,
        lifetime_minutes=10,
    )


def _issuer(previous: tuple[str, ...] = ()) -> JwtTokenIssuer:
    return JwtTokenIssuer(
        signing_key=KEY, previous_keys=previous, issuer="xcode-api", audience="xcode-clients"
    )


def _expected_claims(permission: object) -> dict[str, object]:
    claims: dict[str, object] = {
        "sub": str(USER),
        "device": "phone-1",
        "version": "3",
        "org": str(ORG),
        "role": "Owner",
        "first_name": "Jane",
        "last_name": "Doe",
    }
    if permission is not None:
        claims["permission"] = permission
    claims.update(nbf=ISSUED, exp=ISSUED + 600, iss="xcode-api", aud="xcode-clients")
    return claims


def _segment(token: str, index: int) -> dict[str, object]:
    part = token.split(".")[index]
    decoded: dict[str, object] = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    return decoded


@pytest.mark.parametrize(
    ("permissions", "claim"),
    [
        (("revenue.view", "revenue.capture"), ["revenue.view", "revenue.capture"]),
        (("revenue.view",), "revenue.view"),
        ((), None),
    ],
)
def test_token_equals_one_built_by_hand_byte_for_byte(
    permissions: tuple[str, ...], claim: object
) -> None:
    token = _issuer().issue(_grant(permissions), now=NOW)
    by_hand = jwt.encode(_expected_claims(claim), KEY, algorithm="HS256")
    assert token == by_hand
    assert _segment(token, 0) == {"alg": "HS256", "typ": "JWT"}
    payload = _segment(token, 1)
    assert list(payload) == list(_expected_claims(claim))
    assert "iat" not in payload
    assert "jti" not in payload


def test_verify_returns_the_claims() -> None:
    issuer = _issuer()
    token = issuer.issue(_grant(), now=NOW)
    assert issuer.verify(token, now=NOW) == TokenClaims(
        user_id=USER,
        device_id="phone-1",
        security_version=3,
        organization_id=ORG,
        role="Owner",
        first_name="Jane",
        last_name="Doe",
        permissions=("revenue.view", "revenue.capture"),
    )


def test_lifetime_is_checked_against_the_given_clock_with_zero_leeway() -> None:
    issuer = _issuer()
    token = issuer.issue(_grant(), now=NOW)
    issued = datetime.fromtimestamp(ISSUED, tz=UTC)
    assert issuer.verify(token, now=issued).device_id == "phone-1"
    assert issuer.verify(token, now=issued + timedelta(seconds=600)).device_id == "phone-1"
    with pytest.raises(SessionInvalid):
        issuer.verify(token, now=issued + timedelta(seconds=600, microseconds=1))
    with pytest.raises(SessionInvalid):
        issuer.verify(token, now=issued - timedelta(microseconds=1))


def test_tokens_signed_with_a_previous_key_still_verify() -> None:
    old = JwtTokenIssuer(signing_key=OLD_KEY, issuer="xcode-api", audience="xcode-clients")
    token = old.issue(_grant(), now=NOW)
    assert _issuer(previous=(OLD_KEY,)).verify(token, now=NOW).user_id == USER
    with pytest.raises(SessionInvalid):
        _issuer().verify(token, now=NOW)


def test_a_previous_key_never_signs() -> None:
    token = _issuer(previous=(OLD_KEY,)).issue(_grant(), now=NOW)
    jwt.decode(
        token,
        KEY,
        algorithms=["HS256"],
        audience="xcode-clients",
        options={"verify_exp": False, "verify_nbf": False},
    )
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(
            token,
            OLD_KEY,
            algorithms=["HS256"],
            audience="xcode-clients",
            options={"verify_exp": False, "verify_nbf": False},
        )


def _forged(claims: dict[str, object], *, key: str = KEY, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, key, algorithm=algorithm)


def _without(name: str) -> dict[str, object]:
    claims = _expected_claims(["a", "b"])
    del claims[name]
    return claims


def _with(**changes: object) -> dict[str, object]:
    claims = _expected_claims(["a", "b"])
    claims.update(changes)
    return claims


def _none_algorithm_token() -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(_expected_claims("a")).encode()).rstrip(b"=")
    return f"{header}.{body.decode()}."


def _flipped_signature() -> str:
    token = _issuer().issue(_grant(), now=NOW)
    head, body, signature = token.split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
    return f"{head}.{body}.{flipped}"


def _swapped_payload() -> str:
    token = _issuer().issue(_grant(), now=NOW)
    head, _, signature = token.split(".")
    other = _forged(_with(sub=str(ORG))).split(".")[1]
    return f"{head}.{other}.{signature}"


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(_forged(_expected_claims("a"), key=OTHER_KEY), id="unknown-key"),
        pytest.param(_forged(_expected_claims("a"), algorithm="HS512"), id="hs512"),
        pytest.param(_forged(_expected_claims("a"), algorithm="HS384"), id="hs384"),
        pytest.param(_none_algorithm_token(), id="alg-none"),
        pytest.param(_flipped_signature(), id="signature-flipped"),
        pytest.param(_swapped_payload(), id="payload-swapped"),
        pytest.param(_forged(_with(iss="someone-else")), id="wrong-issuer"),
        pytest.param(_forged(_with(aud="someone-else")), id="wrong-audience"),
        pytest.param(_forged(_without("iss")), id="no-issuer"),
        pytest.param(_forged(_without("aud")), id="no-audience"),
        pytest.param(_forged(_without("exp")), id="no-exp"),
        pytest.param(_forged(_without("nbf")), id="no-nbf"),
        pytest.param(_forged(_without("sub")), id="no-sub"),
        pytest.param(_forged(_without("device")), id="no-device"),
        pytest.param(_forged(_without("version")), id="no-version"),
        pytest.param(_forged(_with(sub="not-a-uuid")), id="sub-not-uuid"),
        pytest.param(_forged(_with(version=3)), id="version-not-string"),
        pytest.param(_forged(_with(version="03")), id="version-not-canonical"),
        pytest.param(_forged(_with(version="-1")), id="version-negative"),
        pytest.param(_forged(_with(device="")), id="device-empty"),
        pytest.param(_forged(_with(org="not-a-uuid")), id="org-not-uuid"),
        pytest.param(_forged(_with(permission=[1, 2])), id="permission-not-text"),
        pytest.param(_forged(_with(exp=float(ISSUED + 600))), id="exp-not-integer"),
        pytest.param("not.a.token", id="garbage"),
        pytest.param("", id="empty"),
    ],
)
def test_every_tampering_is_refused(token: str) -> None:
    with pytest.raises(SessionInvalid):
        _issuer().verify(token, now=NOW)
