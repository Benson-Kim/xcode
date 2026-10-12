"""SQLSTATE translation: the single table from ``docs/03-database.md`` section 5.

A routine signals an expected failure with ``RAISE ... USING ERRCODE = '<code>',
MESSAGE = '<machine_code>', DETAIL = '<json>'``. :func:`translate` turns a psycopg error
into the typed exception the use-case boundary expects, copying ``MESSAGE`` onto ``code``
and the parsed ``DETAIL`` JSON onto ``detail``. This mapping lives here and nowhere else.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg

from ..application.errors import IntegrityBug, TransientFailure
from ..domain.errors import (
    CapExceeded,
    Conflict,
    DomainRefusal,
    Forbidden,
    NotFound,
    RuleViolation,
    SessionInvalid,
)

# XC* codes raised deliberately by routines.
_XC_REFUSALS: dict[str, type[DomainRefusal]] = {
    "XC401": SessionInvalid,
    "XC403": Forbidden,
    "XC404": NotFound,
    "XC409": Conflict,
    "XC422": RuleViolation,
    "XC429": CapExceeded,
}

# Native SQLSTATEs mapped to a 409 conflict, under one code.
_CONFLICT_SQLSTATES = frozenset({"23505"})
UNIQUE_CONFLICT = "unique_conflict"

# Native SQLSTATEs that mean a routine let an integrity rule reach the database (a bug).
_INTEGRITY_SQLSTATES = frozenset({"23503", "23514", "23502"})

# Transient failures the gateway retries for idempotent calls before surfacing them.
_TRANSIENT_SQLSTATES = frozenset({"40001", "40P01", "57P01"})
_TRANSIENT_CLASSES = frozenset({"08"})


def is_transient(sqlstate: str | None) -> bool:
    """True for the SQLSTATEs the gateway may retry for an idempotent call."""
    if not sqlstate:
        return False
    return sqlstate in _TRANSIENT_SQLSTATES or sqlstate[:2] in _TRANSIENT_CLASSES


def is_transient_error(error: psycopg.Error) -> bool:
    """True when the failure is transient: a listed SQLSTATE, or a connection-level
    ``OperationalError`` that carries no SQLSTATE at all (pool timeout, pool closed,
    connection refused or lost before the server could answer)."""
    if is_transient(error.sqlstate):
        return True
    return isinstance(error, psycopg.OperationalError) and error.sqlstate is None


def translate(error: psycopg.Error) -> Exception:
    """Return the typed exception a psycopg error maps to; never raises itself."""
    sqlstate = error.sqlstate
    message, detail = _message_and_detail(error)

    if is_transient_error(error):
        return TransientFailure(f"transient database failure {sqlstate or type(error).__name__}")

    if sqlstate in _XC_REFUSALS:
        refusal = _XC_REFUSALS[sqlstate](message or None, detail=detail)
        if message:
            refusal.code = message
        return refusal

    if sqlstate in _CONFLICT_SQLSTATES:
        # The message is PostgreSQL's own text; the contract names every such conflict one way.
        return Conflict(code=UNIQUE_CONFLICT)

    if sqlstate in _INTEGRITY_SQLSTATES:
        return IntegrityBug(f"integrity violation {sqlstate}: {message}")

    # Anything else is an unexpected database error: surfaced as a bug, logged at the edge.
    return IntegrityBug(f"unexpected database error {sqlstate}: {message}")


def _message_and_detail(error: psycopg.Error) -> tuple[str, dict[str, Any]]:
    diag = error.diag
    message = (diag.message_primary or "").strip() if diag is not None else ""
    raw_detail = (diag.message_detail or "").strip() if diag is not None else ""
    detail: dict[str, Any] = {}
    if raw_detail:
        try:
            parsed = json.loads(raw_detail)
        except (ValueError, TypeError):
            detail = {}
        else:
            if isinstance(parsed, dict):
                detail = parsed
    return message, detail
