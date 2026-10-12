"""Every routine file carries the header of ``docs/05-routines.md`` section 1.1, and its
``Raises:`` line matches the ``tenancy.refuse(`` calls of its body. Also the file-level
invariants: ``tenancy.refuse`` is the only RAISE site, no body reads ``now()``, no routine
takes a PIN, code or token in clear text, and the only ``SECURITY DEFINER`` functions outside
``api`` are the allow-listed cross-tenant lookups."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest

from xcode_api.db.migrate import find_db_dir

ROUTINES = find_db_dir() / "routines"
PROJECT = ROUTINES.parent.parent
LABELS = ("Purpose:", "Callers:", "Reads:", "Writes:", "Raises:", "Tests:")
# Cross-tenant lookups that read past row-level security as the table owner (docs/05-routines.md
# section 2.2); each returns ids only and is executable by xcode_api_executor alone.
DEFINER_HELPERS = {"identity.active_organization", "tenancy.organization_ids"}

_ENTRY = re.compile(r"(XC\d{3}) ([a-z0-9_]+)(?: via ([a-z_]+\.[a-z_]+))?")
_REFUSE = re.compile(r"tenancy\.refuse\(\s*'([a-z0-9_]+)'(?:\s*,\s*'(XC\d{3})')?")
_CREATE = re.compile(
    r"CREATE OR REPLACE (?:FUNCTION|PROCEDURE) ([a-z_]+\.[a-z_]+)\(", re.IGNORECASE
)


@dataclass(frozen=True)
class RoutineFile:
    path: Path
    name: str
    header: dict[str, str]
    body: str

    @property
    def raises(self) -> str:
        return self.header["Raises:"]


def _parse(path: Path) -> RoutineFile:
    lines = path.read_text(encoding="utf-8").splitlines()
    header_lines: list[str] = []
    for line in lines:
        if not line.startswith("--"):
            break
        header_lines.append(line[2:].strip())
    body = "\n".join(lines[len(header_lines) :])
    fields: dict[str, str] = {}
    current: str | None = None
    for text in header_lines[1:]:
        label = next((lab for lab in LABELS if text.startswith(lab)), None)
        if label is not None:
            current = label
            value = text[len(label) :].strip()
            # "Reads: ... Writes: ..." on one line
            if label == "Reads:" and "Writes:" in value:
                value, writes = value.split("Writes:", 1)
                fields["Writes:"] = writes.strip()
            fields[label] = value.strip()
        elif current is not None:
            fields[current] = f"{fields[current]} {text}".strip()
    name = header_lines[0].split("(")[0].split(" ")[0] if header_lines else ""
    return RoutineFile(path=path, name=name, header=fields, body=body)


def _files() -> list[RoutineFile]:
    return [_parse(p) for p in sorted(ROUTINES.rglob("*.sql"))]


def _ids() -> list[str]:
    return [p.relative_to(ROUTINES).as_posix() for p in sorted(ROUTINES.rglob("*.sql"))]


def _code_only(body: str) -> str:
    return re.sub(r"--[^\n]*", "", body)


def _declared(raises: str) -> list[tuple[str, str, str | None]]:
    return [(m.group(1), m.group(2), m.group(3)) for m in _ENTRY.finditer(raises)]


def _refused(body: str) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    for match in _REFUSE.finditer(_code_only(body)):
        entry = (match.group(2) or "XC422", match.group(1))
        if entry not in seen:
            seen.append(entry)
    return seen


BY_NAME = {f.name: f for f in _files()}


@pytest.mark.parametrize("routine", _files(), ids=_ids())
def test_every_routine_file_has_the_header_lines(routine: RoutineFile) -> None:
    assert re.fullmatch(r"[a-z_]+\.[a-z_]+", routine.name), "first line names schema.routine"
    for label in LABELS:
        assert routine.header.get(label), f"{routine.path.name} lacks {label}"
    created = _CREATE.findall(routine.body)
    if created:
        assert created == [routine.name], "one routine per file, named in the header"
        assert routine.path.stem == routine.name.split(".")[1]
    else:
        assert "CREATE TYPE" in routine.body
        assert routine.path.stem == routine.name.replace(".", "_")
    for test_module in re.findall(r"tests/[a-z_/]+\.py", routine.header["Tests:"]):
        assert (PROJECT / test_module).exists(), f"{test_module} does not exist"


@pytest.mark.parametrize("routine", _files(), ids=_ids())
def test_raises_matches_the_refusals_of_the_body(routine: RoutineFile) -> None:
    if routine.name == "tenancy.refuse":
        return
    declared = _declared(routine.raises)
    direct = [(sqlstate, code) for sqlstate, code, via in declared if via is None]
    assert direct == _refused(routine.body), "Raises: lists the body's refusals in order"
    if not declared:
        assert routine.raises.lower().startswith("none"), routine.raises
    for sqlstate, code, via in declared:
        if via is None:
            continue
        helper = BY_NAME.get(via)
        assert helper is not None, f"{via} has no routine file"
        assert (sqlstate, code) in [(s, c) for s, c, _ in _declared(helper.raises)]


def test_auth_routines_raise_nothing_but_session_resolution_and_device_removal() -> None:
    auth = [f for f in _files() if f.name.startswith("api.auth_")]
    assert len(auth) == 19
    for routine in auth:
        if routine.name == "api.auth_resolve_session":
            assert _declared(routine.raises) == [("XC401", "session_invalid", None)]
        elif routine.name == "api.auth_device_remove":
            assert _declared(routine.raises) == [("XC404", "not_found", None)]
        else:
            assert routine.raises == "none.", routine.name


@pytest.mark.parametrize("routine", _files(), ids=_ids())
def test_bodies_raise_only_through_refuse_and_never_read_now(routine: RoutineFile) -> None:
    code = _code_only(routine.body)
    if routine.name != "tenancy.refuse":
        assert not re.search(r"\bRAISE\b", code, re.IGNORECASE)
    assert not re.search(r"\bnow\s*\(", code, re.IGNORECASE)
    assert not re.search(r"\b(current_timestamp|clock_timestamp|statement_timestamp)\b", code)


@pytest.mark.parametrize("routine", _files(), ids=_ids())
def test_no_routine_takes_a_secret_in_clear_text(routine: RoutineFile) -> None:
    # Helpers name a refusal code p_code; the callable api.* surface has no code parameter at all.
    secrets = "pin|code|token|refresh_token|new_token|secret"
    if not routine.name.startswith("api."):
        secrets = "pin|token|refresh_token|new_token|secret"
    assert not re.search(rf"\bp_({secrets})\s+text\b", routine.body)


@pytest.mark.parametrize("routine", _files(), ids=_ids())
def test_security_definer_outside_api_is_only_the_allow_list(routine: RoutineFile) -> None:
    if not _CREATE.search(routine.body):
        return
    definer = re.search(r"^SECURITY DEFINER$", routine.body, re.MULTILINE) is not None
    if routine.name.startswith("api."):
        assert definer
    else:
        assert definer == (routine.name in DEFINER_HELPERS)


@pytest.mark.structure
def test_definer_helpers_are_owned_by_the_owner_and_executable_by_the_executor_only(
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    rows = owner_conn.execute(
        """
        SELECT n.nspname || '.' || p.proname AS name,
               pg_get_userbyid(p.proowner) AS owner,
               has_function_privilege('xcode_app', p.oid, 'EXECUTE') AS app,
               has_function_privilege('xcode_operator', p.oid, 'EXECUTE') AS operator,
               has_function_privilege('xcode_api_executor', p.oid, 'EXECUTE') AS executor
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE p.prosecdef AND n.nspname <> 'api'
        ORDER BY 1
        """
    ).fetchall()
    assert {r["name"] for r in rows} == DEFINER_HELPERS
    for row in rows:
        assert (row["owner"], row["app"], row["operator"], row["executor"]) == (
            "xcode_owner",
            False,
            False,
            True,
        )
