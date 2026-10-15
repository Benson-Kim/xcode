"""The deferred share-sum trigger is fired by the routine that writes the shares.

At commit a deferred trigger runs as the session role, ``xcode_app``, which cannot use the
``setup`` schema, so a routine that inserted versions or allocations and left the check
deferred would fail at commit (``docs/04-schema.md`` section 5.8).
"""

from __future__ import annotations

import re

from xcode_api.db.migrate import find_db_dir

_WRITES = re.compile(
    r"\b(INSERT\s+INTO|UPDATE)\s+setup\.recurring_(versions|allocations)\b", re.IGNORECASE
)
_FIRES = re.compile(r"SET\s+CONSTRAINTS\s+setup\.check_allocation_sum\s+IMMEDIATE", re.IGNORECASE)


def test_every_routine_writing_shares_fires_the_check_before_commit() -> None:
    writers = [
        path
        for path in sorted((find_db_dir() / "routines").rglob("*.sql"))
        if _WRITES.search(path.read_text(encoding="utf-8"))
    ]

    assert writers, "no routine writes setup.recurring_versions or recurring_allocations"
    missing = [path.name for path in writers if not _FIRES.search(path.read_text(encoding="utf-8"))]
    assert missing == []
