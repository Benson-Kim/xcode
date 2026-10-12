"""Every function a routine file creates is named in ``docs/05-routines.md``, so a routine or
helper cannot ship without its entry."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "05-routines.md"
_CREATE = re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+([a-z_]+\.\w+)", re.I)
_NAMED = re.compile(r"`([a-z_]+\.\w+)")


def created(routines: Path) -> set[str]:
    return {
        name.lower()
        for path in routines.rglob("*.sql")
        for name in _CREATE.findall(path.read_text(encoding="utf-8"))
    }


def undocumented(text: str, names: set[str]) -> list[str]:
    return sorted(names - set(_NAMED.findall(text)))


def test_every_routine_and_helper_is_named_in_the_routine_document() -> None:
    names = created(ROOT / "db" / "routines")
    assert len(names) > 100
    assert undocumented(DOC.read_text(encoding="utf-8"), names) == []


def test_a_routine_missing_from_the_document_is_reported() -> None:
    text = DOC.read_text(encoding="utf-8")
    names = {"identity.normalize_phone", "identity.normalize_email"}
    assert undocumented(text, names) == []
    without_row = text.replace("`identity.normalize_phone`", "")
    assert undocumented(without_row, names) == ["identity.normalize_phone"]
