"""Every operation the app serves has its row in ``docs/06-http-contract.md`` section 2, with
the same method, path and operation id, so the catalogue cannot silently fall behind the
routers. Rows for routes not built yet are allowed; a served route without a row is not."""

from __future__ import annotations

import re
from pathlib import Path

from xcode_api.container import build_container
from xcode_api.db.pool import open_pool
from xcode_api.main import create_app
from xcode_api.settings import Settings

DOC = Path(__file__).resolve().parents[2] / "docs" / "06-http-contract.md"
_ROUTE = re.compile(r"`(GET|POST|PUT|DELETE|PATCH) (/[^`?]*)")


def _shape(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


def catalogue(text: str) -> dict[tuple[str, str], tuple[str, str | None]]:
    rows: dict[tuple[str, str], tuple[str, str | None]] = {}
    header: list[str] = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] == "ID":
            header = cells
            continue
        route = _ROUTE.match(cells[1]) if len(cells) > 1 else None
        if not re.fullmatch(r"[A-Z]\d\d", cells[0]) or route is None:
            continue
        operation_id = None
        if "operationId" in header:
            operation_id = cells[header.index("operationId")].strip("`") or None
        rows[(route.group(1), _shape(route.group(2)))] = (cells[0], operation_id)
    return rows


def served() -> dict[tuple[str, str], str | None]:
    settings = Settings.for_tests(openapi_enabled=True)
    document = create_app(settings, build_container(settings, open_pool(settings))).openapi()
    return {
        (method.upper(), _shape(path)): operation.get("operationId")
        for path, operations in document["paths"].items()
        for method, operation in operations.items()
    }


def mismatches(text: str, operations: dict[tuple[str, str], str | None]) -> list[str]:
    rows = catalogue(text)
    problems = []
    for key, operation_id in sorted(operations.items()):
        if key not in rows:
            problems.append(f"{key[0]} {key[1]} has no row")
        elif operation_id is not None and rows[key][1] not in (None, operation_id):
            problems.append(f"{rows[key][0]} names {rows[key][1]}, the app serves {operation_id}")
    return problems


def test_every_served_operation_has_its_catalogue_row() -> None:
    assert mismatches(DOC.read_text(encoding="utf-8"), served()) == []


def test_a_served_route_without_a_row_or_with_another_operation_id_is_reported() -> None:
    text = DOC.read_text(encoding="utf-8")
    operations = served()
    without_row = re.sub(r"^\| S12 \|.*\n", "", text, flags=re.M)
    renamed = text.replace("`ListSetupCompanies`", "`ListCompanies`")

    assert mismatches(without_row, operations) == ["GET /setup/companies has no row"]
    assert mismatches(renamed, operations) == [
        "S12 names ListCompanies, the app serves ListSetupCompanies"
    ]
