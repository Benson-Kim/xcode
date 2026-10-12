"""Refusal vocabulary of the business domain.

Nothing in this module knows about HTTP. The HTTP layer maps each refusal to a status
and a body (``http/errors.py``); the database raises SQLSTATE codes that the gateway
translates into these same types (``db/errors.py``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class DomainRefusal(Exception):  # noqa: N818 - domain vocabulary fixed by docs/01-architecture.md
    """A request the domain refuses.

    ``code`` is a stable snake_case identifier that callers and tests may depend on;
    ``detail`` carries structured context (never secrets) for the problem body.
    """

    code: str = "refused"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        if code is not None:
            self.code = code
        super().__init__(message or self.code)
        self.detail: Mapping[str, Any] = dict(detail or {})


class SessionInvalid(DomainRefusal):
    code = "session_invalid"


class Forbidden(DomainRefusal):
    code = "forbidden"


class NotFound(DomainRefusal):
    code = "not_found"


class Conflict(DomainRefusal):
    code = "conflict"


class RuleViolation(DomainRefusal):
    code = "rule_violation"


class CapExceeded(DomainRefusal):
    code = "cap_exceeded"
