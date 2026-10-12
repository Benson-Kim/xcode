"""Failures of the data layer surfaced at the use-case boundary.

These are not domain refusals (``domain/errors.py``): they say the command could not be
carried out, not that the domain refused it. ``http/errors.py`` maps ``TransientFailure``
to 503 and ``IntegrityBug`` to 500.
"""

from __future__ import annotations


class TransientFailure(Exception):  # noqa: N818 - domain name fixed by docs/01-architecture.md
    """A temporary failure (pool exhausted, serialization failure after retries, connection
    lost, PIN hashing at capacity). The caller may retry later; the HTTP layer answers 503
    with ``Retry-After: 1``."""


class IntegrityBug(Exception):  # noqa: N818 - domain name fixed by docs/01-architecture.md
    """A response from the database that violates an invariant the application relies on
    (a routine that should return exactly one row returned none, a code table disagreed
    with a domain enum). Never reaches the client as detail; the HTTP layer answers 500."""
