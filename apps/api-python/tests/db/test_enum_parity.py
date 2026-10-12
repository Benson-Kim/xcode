"""Each domain enumeration against the database that stores it (``docs/04-schema.md`` section 2).

Code tables hold exactly the ``IntEnum`` members (code, name, label); every ``CHECK (column IN
(...))`` list equals its ``StrEnum``; the permission catalogue equals ``Permission`` and the
inventory table (``tests/support/permission_catalogue.json``), the keys outside it equal
``RetiredPermission`` and the hidden key, and their sources and the grant translation equal
the inventory.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql

from xcode_api.db.schema_spec import CHECK_LIST_ENUMS, CODE_TABLE_ENUMS, SPECIFIED_SCHEMAS
from xcode_api.domain.tenancy import ORGANIZATION_MANAGE, Permission, RetiredPermission, RoleName

pytestmark = pytest.mark.structure

Conn = psycopg.Connection[dict[str, Any]]

_CATALOGUE = Path(__file__).resolve().parent.parent / "support" / "permission_catalogue.json"
_IN_LIST = re.compile(r"^CHECK \(\((\w+) = ANY \(ARRAY\[(.*)\]\)\)\)$")
_LITERAL = re.compile(r"'((?:[^']|'')*)'::text")


def _code_table_rows(conn: Conn, qualified: str) -> list[tuple[int, str, str]]:
    query = sql.SQL("SELECT code, name, label FROM {} ORDER BY code").format(
        sql.Identifier(*qualified.split(".", 1))
    )
    return [(r["code"], r["name"], r["label"]) for r in conn.execute(query).fetchall()]


@pytest.mark.parametrize("qualified", sorted(CODE_TABLE_ENUMS))
def test_code_table_holds_exactly_the_enum_members(owner_conn: Conn, qualified: str) -> None:
    enum = CODE_TABLE_ENUMS[qualified]
    expected = [(m.value, m.name.lower(), m.label) for m in enum]
    assert _code_table_rows(owner_conn, qualified) == expected


def test_every_code_table_has_an_enum(owner_conn: Conn) -> None:
    rows = owner_conn.execute(
        """
        SELECT table_schema || '.' || table_name AS qualified
        FROM information_schema.columns
        WHERE table_schema = ANY(%s) AND column_name IN ('code', 'name', 'label')
        GROUP BY table_schema, table_name
        HAVING count(*) = 3
        """,
        (list(SPECIFIED_SCHEMAS),),
    ).fetchall()
    assert {r["qualified"] for r in rows} == set(CODE_TABLE_ENUMS)


def _check_lists(conn: Conn) -> dict[str, list[str]]:
    rows = conn.execute(
        """
        SELECT n.nspname AS schema_name, c.relname AS table_name, k.conname,
               pg_get_constraintdef(k.oid) AS definition
        FROM pg_constraint k
        JOIN pg_class c ON c.oid = k.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE k.contype = 'c' AND n.nspname = ANY(%s)
        """,
        (list(SPECIFIED_SCHEMAS),),
    ).fetchall()
    lists: dict[str, list[str]] = {}
    for r in rows:
        match = _IN_LIST.match(r["definition"])
        if match:
            values = [v.replace("''", "'") for v in _LITERAL.findall(match[2])]
            lists[f"{r['schema_name']}.{r['table_name']}.{r['conname']}"] = values
    return lists


@pytest.mark.parametrize("constraint", sorted(CHECK_LIST_ENUMS))
def test_check_list_equals_its_enum(owner_conn: Conn, constraint: str) -> None:
    enum = CHECK_LIST_ENUMS[constraint]
    assert _check_lists(owner_conn).get(constraint) == [m.value for m in enum]


def test_every_check_list_has_an_enum(owner_conn: Conn) -> None:
    assert set(_check_lists(owner_conn)) == set(CHECK_LIST_ENUMS)


def test_permission_enum_is_the_catalogue_in_order(owner_conn: Conn) -> None:
    rows = owner_conn.execute(
        "SELECT key FROM tenancy.permissions WHERE catalogue ORDER BY group_order, item_order"
    ).fetchall()
    assert [r["key"] for r in rows] == [p.value for p in Permission]
    assert len(Permission) == 59


def test_the_keys_outside_the_catalogue_are_the_retired_and_the_hidden_ones(
    owner_conn: Conn,
) -> None:
    rows = owner_conn.execute(
        "SELECT key, section FROM tenancy.permissions WHERE NOT catalogue "
        "ORDER BY group_order, item_order"
    ).fetchall()
    assert [r["key"] for r in rows] == [*(p.value for p in RetiredPermission), ORGANIZATION_MANAGE]
    assert {r["section"] for r in rows} == {None}


def test_catalogue_rows_equal_the_inventory(owner_conn: Conn) -> None:
    fixture = json.loads(_CATALOGUE.read_text(encoding="utf-8"))
    expected = [
        (item["key"], group["name"], item["label"], group_order, item_order, item["section"])
        for group_order, group in enumerate(fixture["groups"], start=1)
        for item_order, item in enumerate(group["items"], start=1)
    ]
    rows = owner_conn.execute(
        "SELECT key, group_name, label, group_order, item_order, section "
        "FROM tenancy.permissions WHERE catalogue ORDER BY group_order, item_order"
    ).fetchall()
    assert [
        (
            r["key"],
            r["group_name"],
            r["label"],
            r["group_order"],
            r["item_order"],
            r["section"],
        )
        for r in rows
    ] == expected


def test_dependencies_equal_the_inventory_in_catalogue_order(owner_conn: Conn) -> None:
    """``needs`` has no order column: listing it in catalogue order gives the wire order."""
    fixture = json.loads(_CATALOGUE.read_text(encoding="utf-8"))
    expected = {
        item["key"]: item["needs"] for group in fixture["groups"] for item in group["items"]
    }
    rows = owner_conn.execute(
        """
        SELECT p.key, coalesce(array_agg(d.needs ORDER BY n.group_order, n.item_order)
                               FILTER (WHERE d.needs IS NOT NULL), '{}') AS needs
        FROM tenancy.permissions p
        LEFT JOIN tenancy.permission_dependencies d ON d.permission = p.key
        LEFT JOIN tenancy.permissions n ON n.key = d.needs
        WHERE p.catalogue
        GROUP BY p.key
        """
    ).fetchall()
    assert {r["key"]: list(r["needs"]) for r in rows} == expected
    outside = owner_conn.execute(
        "SELECT count(*) AS n FROM tenancy.permission_dependencies d "
        "JOIN tenancy.permissions p ON p.key IN (d.permission, d.needs) WHERE NOT p.catalogue"
    ).fetchone()
    assert outside is not None and outside["n"] == 0


def test_sources_and_translations_equal_the_inventory(owner_conn: Conn) -> None:
    fixture = json.loads(_CATALOGUE.read_text(encoding="utf-8"))
    sources = owner_conn.execute(
        "SELECT permission, source FROM tenancy.permission_sources"
    ).fetchall()
    assert {(r["permission"], r["source"]) for r in sources} == {
        (item["key"], source) for item in fixture["retired"] for source in item["sources"]
    }
    translations = owner_conn.execute(
        "SELECT old_key, new_key FROM tenancy.permission_translations"
    ).fetchall()
    assert {(r["old_key"], r["new_key"]) for r in translations} == {
        (old, new) for old, targets in fixture["translations"].items() for new in targets
    }


def test_role_defaults_equal_the_inventory(owner_conn: Conn) -> None:
    fixture = json.loads(_CATALOGUE.read_text(encoding="utf-8"))
    every_key = {item["key"] for group in fixture["groups"] for item in group["items"]}
    expected: dict[str, set[str]] = {}
    for role, keys in fixture["role_defaults"].items():
        if isinstance(keys, dict):
            expected[role] = (every_key - set(keys["all_except"])) | set(keys["hidden"])
        else:
            expected[role] = set(keys)
    rows = owner_conn.execute("SELECT role_name, permission FROM tenancy.role_defaults").fetchall()
    actual: dict[str, set[str]] = {}
    for r in rows:
        actual.setdefault(r["role_name"], set()).add(r["permission"])
    assert actual == expected
    assert set(actual) == {role.value for role in RoleName}
    assert len(expected["Owner"]) == 60
