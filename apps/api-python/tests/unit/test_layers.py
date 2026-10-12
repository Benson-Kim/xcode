"""The dependency rule of docs/01-architecture.md section 2, enforced by an ast walk."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import xcode_api

PACKAGE_ROOT = Path(xcode_api.__file__).resolve().parent

STDLIB_OK = "<stdlib>"

FIRST_PARTY_ROOTS = {
    "domain",
    "application",
    "http",
    "db",
    "security",
    "infra",
    "settings",
    "container",
    "main",
    "cli",
}

# Allowed first-party and third-party import roots per package (docs/01-architecture.md s2).
ALLOWED: dict[str, set[str]] = {
    "domain": {STDLIB_OK},
    "application": {STDLIB_OK, "domain"},
    "http": {
        STDLIB_OK,
        "application",
        "domain",
        "settings",
        "container",
        "fastapi",
        "starlette",
        "pydantic",
        "structlog",
    },
    "db": {
        STDLIB_OK,
        "domain",
        "settings",
        "application",
        "psycopg",
        "psycopg_pool",
        # the gateway and runner log db.routine / db.migrate (docs/08-operability.md section 2)
        "structlog",
    },
    "security": {STDLIB_OK, "domain", "settings", "application", "jwt"},
    "infra": {
        STDLIB_OK,
        "domain",
        "settings",
        "application",
        "structlog",
        "aiosmtplib",
        "prometheus_client",
    },
    "settings": {STDLIB_OK, "pydantic", "pydantic_settings"},
    # composition root may import everything
    "main": {"*"},
    "container": {"*"},
    "cli": {"*"},
}

THIRD_PARTY_ROOTS = {
    "fastapi",
    "starlette",
    "pydantic",
    "pydantic_settings",
    "psycopg",
    "psycopg_pool",
    "jwt",
    "structlog",
    "aiosmtplib",
    "prometheus_client",
    "uvicorn",
}

ROUTINE_SQL_ALLOWED = re.compile(r"^SELECT \* FROM api\.[a-z_]+\(")


def _modules() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def _package_of(path: Path) -> str:
    rel = path.relative_to(PACKAGE_ROOT)
    parts = rel.parts
    if len(parts) == 1:
        return rel.stem  # settings, main, container, __init__
    return parts[0]


def _root_of(module: str) -> str:
    parts = module.split(".")
    if parts[0] == "xcode_api":
        # absolute self-import: the sub-package is what the rule is about
        return parts[1] if len(parts) > 1 else "xcode_api"
    return parts[0]


def _relative_root(path: Path, level: int, module: str) -> str:
    """Resolve ``from ..x.y import`` against the importing file's package and return the
    top-level sub-package it lands in (``settings`` for the top-level module)."""
    package_parts = list(path.relative_to(PACKAGE_ROOT).parent.parts)
    base = package_parts[: len(package_parts) - (level - 1)] if level > 1 else package_parts
    target = [*base, *module.split(".")]
    return target[0]


def _import_roots(tree: ast.AST, path: Path) -> set[tuple[str, int]]:
    roots: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add((_root_of(alias.name), node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                # ``from .. import settings`` names the module in the alias.
                for alias in node.names:
                    roots.add((_relative_root(path, node.level, alias.name), node.lineno))
            elif node.level:
                roots.add((_relative_root(path, node.level, node.module), node.lineno))
            else:
                roots.add((_root_of(node.module), node.lineno))
    return roots


def _classify(root: str) -> str:
    """First-party roots by name, the standard library by Python's own list, and anything
    else is third party and must be allowed explicitly."""
    if root in FIRST_PARTY_ROOTS or root == "xcode_api":
        return root
    if root in sys.stdlib_module_names or root in sys.builtin_module_names:
        return STDLIB_OK
    return root


def test_dependency_rule_holds() -> None:
    violations: list[str] = []
    for path in _modules():
        if path.name == "__init__.py":
            continue
        package = _package_of(path)
        allowed = ALLOWED.get(package)
        if allowed is None or "*" in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for root, lineno in _import_roots(tree, path):
            label = _classify(root)
            if label in (STDLIB_OK, package):
                continue
            if label not in allowed:
                rel = path.relative_to(PACKAGE_ROOT)
                violations.append(f"{rel}:{lineno} package '{package}' may not import '{label}'")
    assert not violations, "dependency rule violations:\n" + "\n".join(violations)


def test_domain_imports_only_stdlib() -> None:
    domain_dir = PACKAGE_ROOT / "domain"
    bad: list[str] = []
    for path in domain_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for root, lineno in _import_roots(tree, path):
            if _classify(root) not in (STDLIB_OK, "domain"):
                bad.append(f"{path.name}:{lineno} imports {root}")
    assert not bad, bad


def test_only_db_and_tests_import_psycopg() -> None:
    offenders: list[str] = []
    for path in _modules():
        package = _package_of(path)
        if package == "db":
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"\bimport psycopg\b|\bfrom psycopg\b", text):
            offenders.append(str(path.relative_to(PACKAGE_ROOT)))
    assert not offenders, offenders


def test_routine_sql_literals_are_api_calls_only() -> None:
    routines_dir = PACKAGE_ROOT / "db" / "routines"
    bad: list[str] = []
    for path in routines_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                literal = node.value.strip()
                if literal.upper().startswith("SELECT") and not ROUTINE_SQL_ALLOWED.match(literal):
                    bad.append(f"{path.name}:{node.lineno} {literal[:40]!r}")
    assert not bad, bad


def test_relative_package_imports_are_checked() -> None:
    tree = ast.parse("from .. import settings\nfrom . import policies\n")
    roots = {root for root, _ in _import_roots(tree, PACKAGE_ROOT / "domain" / "values.py")}
    assert roots == {"settings", "domain"}
