"""Access tokens: JWT HS256 with exactly the claims of ``docs/07-auth.md`` section 1.

Issue signs with the current key: header ``{"alg":"HS256","typ":"JWT"}``; claims ``sub``,
``device``, ``version`` (a string), ``org``, ``role``, ``first_name``, ``last_name``,
``permission`` (a string for one key, an array for several, absent for none), ``nbf`` (issue
time), ``exp``, ``iss``, ``aud``; integer seconds; no ``iat``, no ``jti``. Verify accepts the
current key, then each previous key; the algorithm is pinned, issuer and audience are
required, and the lifetime is checked against the caller's clock with zero leeway.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import jwt

from ..domain.errors import SessionInvalid
from ..domain.identity import AccessGrant, TokenClaims

ALGORITHM = "HS256"
_REQUIRED = ("sub", "device", "version", "nbf", "exp", "iss", "aud")


class JwtTokenIssuer:
    __slots__ = ("_audience", "_issuer", "_keys")

    def __init__(
        self,
        *,
        signing_key: str,
        previous_keys: Sequence[str] = (),
        issuer: str,
        audience: str,
    ) -> None:
        self._keys = (signing_key, *previous_keys)
        self._issuer = issuer
        self._audience = audience

    def issue(self, grant: AccessGrant, *, now: datetime) -> str:
        issued = int(now.timestamp())
        claims: dict[str, Any] = {
            "sub": str(grant.user_id),
            "device": grant.device_id,
            "version": str(grant.security_version),
            "org": str(grant.organization_id),
            "role": grant.role,
            "first_name": grant.first_name,
            "last_name": grant.last_name,
        }
        if len(grant.permissions) == 1:
            claims["permission"] = grant.permissions[0]
        elif grant.permissions:
            claims["permission"] = list(grant.permissions)
        claims["nbf"] = issued
        claims["exp"] = issued + grant.lifetime_minutes * 60
        claims["iss"] = self._issuer
        claims["aud"] = self._audience
        return jwt.encode(claims, self._keys[0], algorithm=ALGORITHM)

    def verify(self, token: str, *, now: datetime) -> TokenClaims:
        payload = self._decode(token)
        instant = now.timestamp()
        nbf, exp = payload["nbf"], payload["exp"]
        if not _is_int(nbf) or not _is_int(exp) or not nbf <= instant <= exp:
            raise SessionInvalid()
        return _claims(payload)

    def _decode(self, token: str) -> Mapping[str, Any]:
        for key in self._keys:
            try:
                payload: Mapping[str, Any] = jwt.decode(
                    token,
                    key,
                    algorithms=[ALGORITHM],
                    issuer=self._issuer,
                    audience=self._audience,
                    leeway=0,
                    options={
                        "require": list(_REQUIRED),
                        "verify_exp": False,
                        "verify_nbf": False,
                        "verify_iat": False,
                    },
                )
            except jwt.InvalidSignatureError:
                continue
            except jwt.PyJWTError:
                raise SessionInvalid() from None
            return payload
        raise SessionInvalid()


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _claims(payload: Mapping[str, Any]) -> TokenClaims:
    version = payload["version"]
    device = payload["device"]
    if not isinstance(version, str) or not version.isascii() or not version.isdigit():
        raise SessionInvalid()
    if str(int(version)) != version or not isinstance(device, str) or not device:
        raise SessionInvalid()
    try:
        user_id = UUID(str(payload["sub"]))
        organization = payload.get("org")
        organization_id = None if organization is None else UUID(str(organization))
    except ValueError:
        raise SessionInvalid() from None
    return TokenClaims(
        user_id=user_id,
        device_id=device,
        security_version=int(version),
        organization_id=organization_id,
        role=_text(payload.get("role")),
        first_name=_text(payload.get("first_name")),
        last_name=_text(payload.get("last_name")),
        permissions=_permissions(payload.get("permission")),
    )


def _text(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SessionInvalid()
    return value


def _permissions(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    raise SessionInvalid()
