"""The permission keys and revenue statuses the server owns and the clients mirror (the .NET
``PermissionKeysTests``): the domain enumerations, the catalogue fixture, the rights of the
design prototype and the shared lists in ``packages/shared/src`` must not drift. The shared
files and the prototype are read from the repository root; when the project is checked out
alone those checks skip."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from xcode_api.domain.revenue import CellStatus
from xcode_api.domain.tenancy import ORGANIZATION_MANAGE, Permission, RetiredPermission

API_ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = API_ROOT / "tests" / "support" / "permission_catalogue.json"
SHARED = API_ROOT.parents[1] / "packages" / "shared" / "src"
PROTOTYPE = API_ROOT.parents[1] / "docs" / "design" / "XCODE_Web_v2.3.html"

needs_shared = pytest.mark.skipif(
    not SHARED.is_dir(), reason="packages/shared is not checked out beside apps/api-python"
)
needs_prototype = pytest.mark.skipif(
    not PROTOTYPE.is_file(), reason="docs/design is not checked out beside apps/api-python"
)


def _catalogue() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    return loaded


def _catalogue_keys() -> list[str]:
    return [item["key"] for group in _catalogue()["groups"] for item in group["items"]]


def _shared_list(file_name: str, constant: str) -> list[str]:
    text = (SHARED / file_name).read_text(encoding="utf-8")
    match = re.search(rf"export const {constant} = \[(.*?)\] as const", text, re.DOTALL)
    assert match is not None, f"{constant} not found in {file_name}"
    return re.findall(r'"([^"]+)"', match.group(1))


def _prototype_modules() -> list[tuple[str, list[tuple[str, str]]]]:
    text = PROTOTYPE.read_text(encoding="utf-8")
    block = re.search(r"var MODS = \[(.*?)\n\];", text, re.DOTALL)
    assert block is not None, "MODS not found in the prototype"
    modules = []
    for match in re.finditer(
        r"\{id:'[^']+',name:'([^']+)'.*?rights:\[(.*?)\]\}", block.group(1), re.DOTALL
    ):
        rights = re.findall(r"\['([^']+)','([^']+)'", match.group(2))
        modules.append((match.group(1), rights))
    return modules


def test_the_permission_enumeration_equals_the_catalogue_in_order() -> None:
    keys = _catalogue_keys()
    assert [permission.value for permission in Permission] == keys
    assert len(set(keys)) == len(keys) == 59
    assert len(_catalogue()["groups"]) == 12


def test_retired_and_hidden_keys_stay_outside_the_catalogue() -> None:
    catalogue = _catalogue()
    keys = set(_catalogue_keys())
    retired = [item["key"] for item in catalogue["retired"]]
    assert [permission.value for permission in RetiredPermission] == retired
    assert len(retired) == 20
    assert [item["key"] for item in catalogue["hidden"]] == [ORGANIZATION_MANAGE]
    assert not keys & {*retired, ORGANIZATION_MANAGE}
    for item in catalogue["retired"]:
        assert set(item["sources"]) <= keys, item["key"]


def test_dependencies_and_role_defaults_name_only_catalogue_keys() -> None:
    catalogue = _catalogue()
    keys = set(_catalogue_keys())
    for group in catalogue["groups"]:
        for item in group["items"]:
            assert set(item["needs"]) <= keys, item["key"]
    for role, defaults in catalogue["role_defaults"].items():
        if isinstance(defaults, dict):
            assert set(defaults["all_except"]) <= keys, role
            assert defaults["hidden"] == [ORGANIZATION_MANAGE], role
        else:
            assert set(defaults) <= keys, role


def test_every_old_grant_translates_to_catalogue_rights() -> None:
    catalogue = _catalogue()
    keys = set(_catalogue_keys())
    translations: dict[str, list[str]] = catalogue["translations"]
    assert sum(len(targets) for targets in translations.values()) == 58
    for old, targets in translations.items():
        assert set(targets) <= keys, old


@needs_prototype
def test_the_catalogue_has_the_rights_of_the_prototype_one_to_one() -> None:
    modules = _prototype_modules()
    groups = _catalogue()["groups"]
    assert [name for name, _ in modules] == [group["name"] for group in groups]
    for (_, rights), group in zip(modules, groups, strict=True):
        assert [right for right, _ in rights] == [item["prototype"] for item in group["items"]]
        assert [label.replace("\u2019", "'") for _, label in rights] == [
            item["label"] for item in group["items"]
        ]


@needs_shared
def test_released_clients_read_only_keys_the_server_still_issues() -> None:
    shared = set(_shared_list("permissions.ts", "PERMISSION_KEYS"))
    keys = set(_catalogue_keys())
    outside = {item["key"] for item in _catalogue()["retired"]} | {ORGANIZATION_MANAGE}
    assert shared <= keys | outside
    assert outside <= shared
    assert (len(shared), len(shared & keys), len(outside)) == (40, 19, 21)
    assert set(_catalogue()["translations"]) == shared


def test_cell_statuses_keep_their_wire_values() -> None:
    assert [status.value for status in CellStatus] == [
        "none",
        "future",
        "missing",
        "amount",
        "reason",
    ]
    assert CellStatus("missing") is CellStatus.MISSING


@needs_shared
def test_cell_statuses_match_the_clients() -> None:
    assert _shared_list("revenue.ts", "REVENUE_STATUSES") == [s.value for s in CellStatus]
