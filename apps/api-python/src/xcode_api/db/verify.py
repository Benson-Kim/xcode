"""Structural assertions shared by ``xcode-api db verify`` and ``tests/db/test_structure.py``.

Every generic item of ``docs/03-database.md`` sections 2, 3, 7 and 9 is a named check here,
and the table-by-table items of ``docs/04-schema.md`` are checked against the declarations
in ``db/schema_spec.py``. ``run_checks`` runs them all against an owner connection and returns
one :class:`CheckResult` per check; the CLI prints one line each and exits 1 on any failure,
the structure tests assert each result passed. Adding an object kind means adding a check
here, in one place.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg import sql

from .schema_spec import (
    CODE_TABLE_ENUMS,
    INDEXES,
    SPECIFIED_SCHEMAS,
    TABLES,
    IndexSpec,
    TableKind,
)

DATA_SCHEMAS = ("identity", "tenancy", "setup", "revenue", "pettycash", "ops")
ALL_SCHEMAS = (*DATA_SCHEMAS, "api")

# Secret-ish column names forbidden unless the name ends in _hash or _digest. The code
# tables' ``code`` key is an enumeration integer, not a secret, and is exempt by table.
_SECRET_COLUMN_NAMES = ("pin", "code", "token", "secret", "password")
_SECRET_NAME_EXEMPT = frozenset(
    (t.schema, t.name, "code") for t in TABLES if t.kind is TableKind.CODE
)

# Audit tables that must carry no UPDATE or DELETE grant for xcode_api_executor.
AUDIT_TABLES = (
    ("ops", "operator_actions"),
    *((t.schema, t.name) for t in TABLES if t.kind is TableKind.AUDIT),
)

# Extensions allowed to be installed. plpgsql is always present; btree_gist backs the
# away-period exclusion constraint.
EXTENSION_ALLOW_LIST = frozenset({"plpgsql", "pgcrypto", "btree_gist"})

# Routines (schema.name) whose body may legitimately contain EXECUTE or format( (none
# yet); the check reads every plpgsql and sql function in the routine schemas.
DYNAMIC_SQL_ALLOW_LIST: frozenset[str] = frozenset()

# api.* routines that take p_organization_id without entering it through
# tenancy.enter_organization (none: identity-level routines take no organization).
TENANT_GUARD_ALLOW_LIST: frozenset[str] = frozenset()

# Schemas xcode_readonly may never enter; it reads code tables in tenancy, setup, revenue.
_READONLY_CLOSED_SCHEMAS = ("identity", "ops", "api", "pettycash")

_CONSTRAINED_ROLES = ("xcode_app", "xcode_operator", "xcode_readonly")

# Role settings that bound every session of the two roles that run statements.
_TIMED_ROLES = ("xcode_app", "xcode_operator")
_ROLE_TIMEOUTS = ("statement_timeout", "lock_timeout", "idle_in_transaction_session_timeout")
_ZERO_SETTING = re.compile(r"0+(\.0+)?\s*[a-z]*")

# The roles statements run as outside migrations: every api.* routine runs as the executor,
# and the three logins connect. Row-level security must bind all of them.
SERVICE_ROLES = ("xcode_api_executor", *_CONSTRAINED_ROLES)


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    failures: list[str] = field(default_factory=list)


Conn = psycopg.Connection[dict[str, Any]]
Check = Callable[[Conn], list[str]]


def run_checks(conn: Conn) -> list[CheckResult]:
    results: list[CheckResult] = []
    for name, check in _CHECKS:
        failures = check(conn)
        results.append(CheckResult(name=name, ok=not failures, failures=failures))
    return results


def _rows(
    conn: Conn, query: str | sql.Composed, params: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    cur = conn.execute(query, params)
    return list(cur.fetchall())


# --- individual checks ----------------------------------------------------------------


def check_schemas_exist(conn: Conn) -> list[str]:
    present = {
        str(r["nspname"])
        for r in _rows(
            conn,
            "SELECT nspname FROM pg_catalog.pg_namespace WHERE nspname = ANY(%s)",
            (list(ALL_SCHEMAS),),
        )
    }
    return [f"schema {name} does not exist" for name in ALL_SCHEMAS if name not in present]


def check_roles_exist(conn: Conn) -> list[str]:
    expected = {
        "xcode_owner",
        "xcode_api_executor",
        "xcode_app",
        "xcode_operator",
        "xcode_readonly",
    }
    present = {
        str(r["rolname"])
        for r in _rows(conn, "SELECT rolname FROM pg_roles WHERE rolname LIKE %s", ("xcode\\_%",))
    }
    missing = expected - present
    return [f"role {r} does not exist" for r in sorted(missing)]


def check_role_attributes(conn: Conn) -> list[str]:
    failures: list[str] = []
    rows = _rows(
        conn,
        "SELECT rolname, rolbypassrls, rolconnlimit FROM pg_roles WHERE rolname = ANY(%s)",
        (list(_CONSTRAINED_ROLES),),
    )
    found = {str(r["rolname"]): r for r in rows}
    for role in _CONSTRAINED_ROLES:
        r = found.get(role)
        if r is None:
            failures.append(f"role {role} does not exist")
            continue
        if r["rolbypassrls"]:
            failures.append(f"role {role} must not have BYPASSRLS")
        if int(r["rolconnlimit"]) < 0:
            failures.append(f"role {role} must have a connection limit (rolconnlimit)")
    effective: dict[str, dict[str, str]] = {role: {} for role in _TIMED_ROLES}
    for r in _rows(
        conn,
        """
        SELECT r.rolname, s.setconfig
        FROM pg_catalog.pg_db_role_setting s
        JOIN pg_catalog.pg_roles r ON r.oid = s.setrole
        WHERE r.rolname = ANY(%s)
          AND s.setdatabase IN (
            0, (SELECT oid FROM pg_catalog.pg_database WHERE datname = current_database())
          )
        ORDER BY r.rolname, s.setdatabase
        """,
        (list(_TIMED_ROLES),),
    ):
        for entry in r["setconfig"] or []:
            name, _, setting = str(entry).partition("=")
            effective[str(r["rolname"])][name] = setting
    for role in _TIMED_ROLES:
        for name in _ROLE_TIMEOUTS:
            value = effective[role].get(name)
            if value is None or _ZERO_SETTING.fullmatch(value.strip()):
                failures.append(f"role {role} must have a non-zero {name} role setting")
    return failures


def check_row_security_binds_the_service_roles(conn: Conn) -> list[str]:
    """No service role can skip row-level security: none is a superuser or has BYPASSRLS,
    and none is, or is a member of, the owner of a table that has it. PostgreSQL exempts a
    table's owner from its policies, and no table forces them, because migrations and the
    two cross-organization helpers run as the owner on purpose; so a deployment that connects
    the service as the table owner, or makes the executor a member of it, fails here."""
    return row_security_failures(conn, SERVICE_ROLES)


def row_security_failures(conn: Conn, roles: tuple[str, ...]) -> list[str]:
    failures: list[str] = []
    for r in _rows(
        conn,
        "SELECT rolname, rolsuper, rolbypassrls FROM pg_catalog.pg_roles "
        "WHERE rolname = ANY(%s) ORDER BY rolname",
        (list(roles),),
    ):
        if r["rolsuper"]:
            failures.append(f"role {r['rolname']} is a superuser, which skips row-level security")
        if r["rolbypassrls"]:
            failures.append(f"role {r['rolname']} has BYPASSRLS")
    owners = _rows(
        conn,
        """
        SELECT r.rolname AS role_name,
               pg_catalog.pg_get_userbyid(c.relowner) AS owner,
               count(*) AS tables,
               min(c.relnamespace::regnamespace::text || '.' || c.relname) AS example
        FROM pg_catalog.pg_class c
        CROSS JOIN pg_catalog.pg_roles r
        WHERE c.relkind IN ('r', 'p')
          AND c.relrowsecurity
          AND c.relnamespace::regnamespace::text = ANY(%s)
          AND r.rolname = ANY(%s)
          AND NOT r.rolsuper
          AND pg_catalog.pg_has_role(r.oid, c.relowner, 'MEMBER')
        GROUP BY r.rolname, c.relowner
        ORDER BY 1, 2
        """,
        (list(DATA_SCHEMAS), list(roles)),
    )
    for r in owners:
        failures.append(
            f"role {r['role_name']} acts as {r['owner']}, which owns {r['tables']} tables under "
            f"row-level security (for example {r['example']}), so their policies do not bind it"
        )
    return failures


def check_app_role_has_no_table_privileges(conn: Conn) -> list[str]:
    """Effective privileges, so grants through PUBLIC, role membership and single columns
    count as well as direct table grants; the only schema either role may use is ``api``."""
    failures: list[str] = []
    roles = ["xcode_app", "xcode_operator"]
    for r in _rows(
        conn,
        """
        SELECT r.rolname AS role_name, n.nspname AS schema_name,
               pg_catalog.has_schema_privilege(r.oid, n.oid, 'USAGE') AS can_use,
               pg_catalog.has_schema_privilege(r.oid, n.oid, 'CREATE') AS can_create
        FROM pg_catalog.pg_namespace n
        CROSS JOIN pg_catalog.pg_roles r
        WHERE r.rolname = ANY(%s)
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND left(n.nspname, 3) <> 'pg_'
        ORDER BY 1, 2
        """,
        (roles,),
    ):
        if r["can_create"]:
            failures.append(f"{r['role_name']} has CREATE on schema {r['schema_name']}")
        if r["can_use"] and r["schema_name"] != "api":
            failures.append(
                f"{r['role_name']} has USAGE on schema {r['schema_name']} (expected api only)"
            )
    for r in _rows(
        conn,
        """
        SELECT r.rolname AS role_name,
               n.nspname || '.' || c.relname AS relation,
               c.relkind = 'S' AS is_sequence,
               CASE WHEN c.relkind = 'S'
                    THEN pg_catalog.has_sequence_privilege(r.oid, c.oid, 'USAGE,SELECT,UPDATE')
                    ELSE pg_catalog.has_table_privilege(
                      r.oid, c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
               END AS whole,
               ARRAY(
                 SELECT a.attname::text FROM pg_catalog.pg_attribute a
                 WHERE c.relkind <> 'S' AND a.attrelid = c.oid AND a.attnum > 0
                   AND NOT a.attisdropped
                   AND pg_catalog.has_column_privilege(
                     r.oid, c.oid, a.attnum, 'SELECT,INSERT,UPDATE,REFERENCES')
                 ORDER BY a.attnum
               ) AS columns
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN pg_catalog.pg_roles r
        WHERE r.rolname = ANY(%s)
          AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND left(n.nspname, 3) <> 'pg_'
        ORDER BY 1, 2
        """,
        (roles,),
    ):
        kind = "sequence" if r["is_sequence"] else "table"
        if r["whole"]:
            failures.append(f"{r['role_name']} holds privileges on {kind} {r['relation']}")
        elif r["columns"]:
            failures.append(
                f"{r['role_name']} holds column privileges on {r['relation']} "
                f"({', '.join(r['columns'])})"
            )
    return failures


def check_app_cannot_execute_ops_routines(conn: Conn) -> list[str]:
    rows = _rows(
        conn,
        """
        SELECT p.proname AS name
        FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'api'
          AND p.proname LIKE %s
          AND has_function_privilege('xcode_app', p.oid, 'EXECUTE')
        """,
        ("ops\\_%",),
    )
    return [f"xcode_app can execute api.{r['name']} (an ops routine)" for r in rows]


def check_api_routine_properties(conn: Conn) -> list[str]:
    failures: list[str] = []
    rows = _rows(
        conn,
        """
        SELECT p.proname AS name,
               p.prosecdef AS security_definer,
               pg_catalog.pg_get_userbyid(p.proowner) AS owner,
               p.proconfig AS config,
               -- A NULL acl means the built-in default (PUBLIC may EXECUTE); an explicit acl
               -- with a grantee of 0 (PUBLIC) and EXECUTE also fails the check.
               (
                 p.proacl IS NULL
                 OR EXISTS (
                   SELECT 1 FROM aclexplode(p.proacl) a
                   WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE'
                 )
               ) AS public_execute
        FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'api'
        """,
    )
    for r in rows:
        name = f"api.{r['name']}"
        if not r["security_definer"]:
            failures.append(f"{name} is not SECURITY DEFINER")
        if str(r["owner"]) != "xcode_api_executor":
            failures.append(f"{name} is owned by {r['owner']}, not xcode_api_executor")
        config = r["config"] or []
        if not _has_fixed_search_path(config):
            failures.append(f"{name} does not set search_path=pg_catalog, pg_temp")
        if r["public_execute"]:
            failures.append(f"{name} is executable by PUBLIC")
    return failures


def _has_fixed_search_path(config: list[str]) -> bool:
    for entry in config:
        if entry.startswith("search_path="):
            value = entry.split("=", 1)[1].replace(" ", "")
            return value == "pg_catalog,pg_temp"
    return False


def check_public_schema_empty(conn: Conn) -> list[str]:
    tables = _rows(
        conn,
        "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'",
    )
    routines = _rows(
        conn,
        "SELECT p.proname AS name FROM pg_catalog.pg_proc p "
        "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public'",
    )
    failures = [f"public schema has table {r['tablename']}" for r in tables]
    failures += [f"public schema has routine {r['name']}" for r in routines]
    return failures


def check_tenant_tables_have_rls(conn: Conn) -> list[str]:
    """Every table with an organization_id column, and tenancy.organizations on id, has RLS
    enabled and exactly one policy: the permissive tenant_isolation for xcode_api_executor,
    with USING and WITH CHECK both matching the tenant column to the current organization.
    Declared non-tenant tables (identity, code tables, catalogue) have RLS off and no policy."""
    failures: list[str] = []
    rows = _rows(
        conn,
        """
        SELECT c.relnamespace::regnamespace::text AS schema_name,
               c.relname AS table_name
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
        WHERE c.relkind = 'r'
          AND a.attname = 'organization_id'
          AND a.attnum > 0
          AND NOT a.attisdropped
          AND c.relnamespace::regnamespace::text = ANY(%s)
        """,
        (list(DATA_SCHEMAS),),
    )
    tenant_tables = {f"{r['schema_name']}.{r['table_name']}": "organization_id" for r in rows}
    for spec in TABLES:
        if spec.tenant:
            tenant_tables[spec.qualified] = spec.tenant_column
    for qualified, column in sorted(tenant_tables.items()):
        failures += _tenant_policy_failures(conn, qualified, column)
    for spec in TABLES:
        if spec.tenant or spec.qualified in tenant_tables:
            continue
        state = _rls_state(conn, spec.schema, spec.name)
        if state is None:
            continue
        rls_enabled, policies = state
        if rls_enabled:
            failures.append(f"{spec.qualified} is not a tenant table but has RLS enabled")
        if policies:
            failures.append(f"{spec.qualified} is not a tenant table but has policies {policies}")
    return failures


def _rls_state(conn: Conn, schema: str, table: str) -> tuple[bool, list[str]] | None:
    found = _rows(
        conn,
        "SELECT c.relrowsecurity AS rls FROM pg_catalog.pg_class c "
        "WHERE c.relnamespace::regnamespace::text = %s AND c.relname = %s AND c.relkind = 'r'",
        (schema, table),
    )
    if not found:
        return None
    policies = _rows(
        conn,
        "SELECT policyname FROM pg_catalog.pg_policies WHERE schemaname = %s AND tablename = %s",
        (schema, table),
    )
    return bool(found[0]["rls"]), sorted(str(p["policyname"]) for p in policies)


def _tenant_policy_failures(conn: Conn, qualified: str, column: str) -> list[str]:
    schema, table = qualified.split(".", 1)
    state = _rls_state(conn, schema, table)
    if state is None:
        return []
    failures: list[str] = []
    rls_enabled, names = state
    if not rls_enabled:
        failures.append(f"{qualified} is a tenant table but RLS is not enabled")
    if names != ["tenant_isolation"]:
        failures.append(f"{qualified} must carry exactly the tenant_isolation policy, has {names}")
        if "tenant_isolation" not in names:
            return failures
    policy = _rows(
        conn,
        "SELECT permissive, roles::text[] AS roles, cmd, qual, with_check "
        "FROM pg_catalog.pg_policies "
        "WHERE schemaname = %s AND tablename = %s AND policyname = 'tenant_isolation'",
        (schema, table),
    )[0]
    expected = f"{column} = tenancy.current_organization()"
    if policy["permissive"] != "PERMISSIVE":
        failures.append(f"{qualified}.tenant_isolation is not permissive")
    if list(policy["roles"] or []) != ["xcode_api_executor"]:
        failures.append(f"{qualified}.tenant_isolation applies to {policy['roles']}")
    if policy["cmd"] != "ALL":
        failures.append(f"{qualified}.tenant_isolation covers {policy['cmd']}, not ALL")
    for clause in ("qual", "with_check"):
        if _strip_parens(str(policy[clause] or "")) != expected:
            failures.append(f"{qualified}.tenant_isolation {clause} is {policy[clause]!r}")
    return failures


def _strip_parens(text: str) -> str:
    text = text.strip()
    while text.startswith("(") and text.endswith(")") and _balanced(text[1:-1]):
        text = text[1:-1].strip()
    return text


def _balanced(text: str) -> bool:
    depth = 0
    for ch in text:
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth < 0:
            return False
    return depth == 0


def check_declared_tables(conn: Conn) -> list[str]:
    """Every table of docs/04-schema.md section 1 exists with its primary key, and every table
    in the specified schemas is declared (so privileges and RLS are never left unchecked)."""
    failures: list[str] = []
    rows = _rows(
        conn,
        """
        SELECT c.relnamespace::regnamespace::text AS schema_name,
               c.relname AS table_name,
               ARRAY(
                 SELECT a.attname::text
                 FROM pg_catalog.pg_constraint k
                 CROSS JOIN LATERAL unnest(k.conkey) WITH ORDINALITY AS u(attnum, position)
                 JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum = u.attnum
                 WHERE k.conrelid = c.oid AND k.contype = 'p'
                 ORDER BY u.position
               ) AS primary_key
        FROM pg_catalog.pg_class c
        WHERE c.relkind IN ('r', 'p')
          AND c.relnamespace::regnamespace::text = ANY(%s)
        """,
        (list(SPECIFIED_SCHEMAS),),
    )
    found = {f"{r['schema_name']}.{r['table_name']}": tuple(r["primary_key"]) for r in rows}
    declared = {spec.qualified: spec for spec in TABLES}
    for qualified, spec in declared.items():
        if qualified not in found:
            failures.append(f"table {qualified} does not exist")
        elif found[qualified] != spec.primary_key:
            failures.append(
                f"{qualified} primary key is {found[qualified]}, expected {spec.primary_key}"
            )
    for qualified in sorted(found.keys() - declared.keys()):
        failures.append(f"table {qualified} is not declared in db/schema_spec.py")
    return failures


_INDEX_DEF = re.compile(
    r"^CREATE (?P<unique>UNIQUE )?INDEX \S+ ON \S+ USING (?P<method>\w+) "
    r"\((?P<keys>.*?)\)(?: WHERE (?P<where>.*))?$"
)


def check_declared_indexes(conn: Conn) -> list[str]:
    rows = _rows(
        conn,
        """
        SELECT i.indrelid::regclass::text AS table_name,
               pg_catalog.pg_get_indexdef(i.indexrelid) AS definition
        FROM pg_catalog.pg_index i
        JOIN pg_catalog.pg_class c ON c.oid = i.indrelid
        WHERE c.relnamespace::regnamespace::text = ANY(%s)
        """,
        (list(SPECIFIED_SCHEMAS),),
    )
    present: set[IndexSpec] = set()
    for r in rows:
        match = _INDEX_DEF.match(str(r["definition"]))
        if match is None:
            continue
        where = match["where"]
        present.add(
            IndexSpec(
                table=str(r["table_name"]),
                keys=match["keys"],
                unique=match["unique"] is not None,
                where=_strip_parens(where) if where else None,
                method=match["method"],
            )
        )
    return [f"index missing: {_describe_index(spec)}" for spec in INDEXES if spec not in present]


def _describe_index(spec: IndexSpec) -> str:
    unique = "UNIQUE " if spec.unique else ""
    where = f" WHERE {spec.where}" if spec.where else ""
    return f"{unique}{spec.table} USING {spec.method} ({spec.keys}){where}"


def check_declared_privileges(conn: Conn) -> list[str]:
    """Per declared table: xcode_api_executor holds SELECT plus the "Writes" column and
    xcode_readonly holds SELECT on code tables and the catalogue only; no other role (and not
    PUBLIC) holds anything. Outside the declared tables xcode_readonly holds nothing."""
    failures: list[str] = []
    rows = _rows(
        conn,
        """
        SELECT c.relnamespace::regnamespace::text AS schema_name,
               c.relname AS table_name,
               CASE WHEN a.grantee = 0 THEN 'PUBLIC'
                    ELSE pg_catalog.pg_get_userbyid(a.grantee) END AS grantee,
               a.privilege_type
        FROM pg_catalog.pg_class c
        CROSS JOIN LATERAL aclexplode(c.relacl) AS a
        WHERE c.relkind IN ('r', 'p', 'v', 'm', 'S')
          AND c.relnamespace::regnamespace::text = ANY(%s)
          AND a.grantee <> c.relowner
        """,
        (list(ALL_SCHEMAS),),
    )
    held: dict[tuple[str, str], set[str]] = {}
    for r in rows:
        key = (f"{r['schema_name']}.{r['table_name']}", str(r["grantee"]))
        held.setdefault(key, set()).add(str(r["privilege_type"]))
    declared = {spec.qualified: spec for spec in TABLES}
    for spec in TABLES:
        for role, expected in (
            ("xcode_api_executor", spec.executor_privileges()),
            ("xcode_readonly", spec.readonly_privileges()),
        ):
            actual = held.get((spec.qualified, role), set())
            if actual != expected:
                failures.append(
                    f"{role} holds {sorted(actual)} on {spec.qualified}, "
                    f"expected {sorted(expected)}"
                )
    allowed_roles = {"xcode_api_executor", "xcode_readonly"}
    for (qualified, role), privileges in sorted(held.items()):
        if qualified in declared and role not in allowed_roles:
            failures.append(f"{role} holds {sorted(privileges)} on {qualified} (expected none)")
        if qualified not in declared and role in ("xcode_readonly", "PUBLIC"):
            failures.append(f"{role} holds {sorted(privileges)} on {qualified} (expected none)")
    return failures


def check_updated_at_triggers(conn: Conn) -> list[str]:
    rows = _rows(
        conn,
        """
        SELECT c.oid::regclass::text AS table_name,
               EXISTS (
                 SELECT 1 FROM pg_catalog.pg_trigger t
                 WHERE t.tgrelid = c.oid
                   AND t.tgfoid = 'ops.touch_updated_at()'::regprocedure
                   AND t.tgenabled <> 'D'
                   AND (t.tgtype & 1) = 1
                   AND (t.tgtype & 2) = 2
                   AND (t.tgtype & 16) = 16
               ) AS touched
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
        WHERE c.relkind = 'r'
          AND a.attname = 'updated_at'
          AND a.attnum > 0
          AND NOT a.attisdropped
          AND c.relnamespace::regnamespace::text = ANY(%s)
        """,
        (list(SPECIFIED_SCHEMAS),),
    )
    return [
        f"{r['table_name']} has updated_at but no BEFORE UPDATE ops.touch_updated_at() trigger"
        for r in rows
        if not r["touched"]
    ]


def check_tenant_foreign_keys(conn: Conn) -> list[str]:
    """Every tenant table references tenancy.organizations(id), and every foreign key from one
    tenant table to another starts with organization_id on both sides, so no row can point at
    another organization's row."""
    failures: list[str] = []
    rows = _rows(
        conn,
        """
        SELECT k.conname,
               k.conrelid::regclass::text AS source,
               k.confrelid::regclass::text AS target,
               ARRAY(
                 SELECT a.attname::text FROM unnest(k.conkey) WITH ORDINALITY AS u(n, p)
                 JOIN pg_catalog.pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = u.n
                 ORDER BY u.p
               ) AS source_columns,
               ARRAY(
                 SELECT a.attname::text FROM unnest(k.confkey) WITH ORDINALITY AS u(n, p)
                 JOIN pg_catalog.pg_attribute a ON a.attrelid = k.confrelid AND a.attnum = u.n
                 ORDER BY u.p
               ) AS target_columns
        FROM pg_catalog.pg_constraint k
        WHERE k.contype = 'f'
          AND k.connamespace::regnamespace::text = ANY(%s)
        """,
        (list(SPECIFIED_SCHEMAS),),
    )
    tenant = {spec.qualified for spec in TABLES if spec.tenant}
    tenant.discard("tenancy.organizations")
    to_organizations = {
        str(r["source"])
        for r in rows
        if r["target"] == "tenancy.organizations"
        and list(r["source_columns"]) == ["organization_id"]
        and list(r["target_columns"]) == ["id"]
    }
    for qualified in sorted(tenant - to_organizations):
        failures.append(
            f"{qualified} has no foreign key (organization_id) -> tenancy.organizations"
        )
    for r in rows:
        if r["source"] in tenant and r["target"] in tenant:
            if r["source_columns"][0] != "organization_id" or (
                r["target_columns"][0] != "organization_id"
            ):
                failures.append(
                    f"{r['source']}.{r['conname']} does not start with organization_id "
                    "on both sides"
                )
    return failures


def check_code_tables_match_domain(conn: Conn) -> list[str]:
    failures: list[str] = []
    for qualified, enum in CODE_TABLE_ENUMS.items():
        exists = _rows(conn, "SELECT to_regclass(%s) IS NOT NULL AS present", (qualified,))
        if not exists[0]["present"]:
            failures.append(f"code table {qualified} does not exist")
            continue
        query = sql.SQL("SELECT code, name, label FROM {}").format(
            sql.Identifier(*qualified.split(".", 1))
        )
        rows = _rows(conn, query)
        actual = {(int(r["code"]), str(r["name"]), str(r["label"])) for r in rows}
        expected = {(int(m), m.name.lower(), m.label) for m in enum}
        if actual != expected:
            failures.append(
                f"{qualified} holds {sorted(actual)}, domain {enum.__name__} is {sorted(expected)}"
            )
    return failures


def check_secret_column_names(conn: Conn) -> list[str]:
    failures: list[str] = []
    rows = _rows(
        conn,
        """
        SELECT table_schema, table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = ANY(%s)
        """,
        (list(ALL_SCHEMAS),),
    )
    for r in rows:
        column = str(r["column_name"])
        lowered = column.lower()
        if lowered.endswith("_hash") or lowered.endswith("_digest"):
            continue
        if (r["table_schema"], r["table_name"], lowered) in _SECRET_NAME_EXEMPT:
            continue
        if lowered in _SECRET_COLUMN_NAMES:
            failures.append(
                f"{r['table_schema']}.{r['table_name']}.{column} is a secret-ish name "
                "and does not end in _hash or _digest"
            )
    return failures


def check_no_dynamic_sql(conn: Conn) -> list[str]:
    """No plpgsql or sql function in any routine schema builds SQL at run time."""
    failures: list[str] = []
    rows = _rows(
        conn,
        """
        SELECT n.nspname || '.' || p.proname AS name, p.prosrc AS body
        FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_catalog.pg_language l ON l.oid = p.prolang
        WHERE n.nspname = ANY(%s) AND l.lanname IN ('plpgsql', 'sql')
        """,
        (list(ALL_SCHEMAS),),
    )
    for r in rows:
        name = str(r["name"])
        if name in DYNAMIC_SQL_ALLOW_LIST:
            continue
        lowered = str(r["body"]).lower()
        if "execute " in lowered or "execute(" in lowered or "format(" in lowered:
            failures.append(f"{name} body contains EXECUTE or format( and is not allow-listed")
    return failures


def check_tenant_routines_enter_organization(conn: Conn) -> list[str]:
    """Every api.* routine that takes p_organization_id calls tenancy.enter_organization,
    so no tenant routine can read or write before the actor's membership is verified."""
    rows = _rows(
        conn,
        """
        SELECT p.proname AS name, p.prosrc AS body
        FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'api'
          AND 'p_organization_id' = ANY(coalesce(p.proargnames, '{}'::text[]))
        """,
    )
    return [
        f"api.{r['name']} takes p_organization_id but never calls tenancy.enter_organization"
        for r in rows
        if str(r["name"]) not in TENANT_GUARD_ALLOW_LIST
        and "tenancy.enter_organization(" not in str(r["body"])
    ]


def check_audit_tables_append_only(conn: Conn) -> list[str]:
    failures: list[str] = []
    for schema, table in AUDIT_TABLES:
        exists = _rows(
            conn,
            "SELECT 1 FROM pg_catalog.pg_tables WHERE schemaname = %s AND tablename = %s",
            (schema, table),
        )
        if not exists:
            continue
        rows = _rows(
            conn,
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'xcode_api_executor' AND table_schema = %s AND table_name = %s "
            "AND privilege_type IN ('UPDATE', 'DELETE')",
            (schema, table),
        )
        for r in rows:
            failures.append(
                f"audit table {schema}.{table} grants {r['privilege_type']} to xcode_api_executor"
            )
    return failures


def check_readonly_locked_out(conn: Conn) -> list[str]:
    failures: list[str] = []
    usable = _rows(
        conn,
        "SELECT nspname FROM pg_catalog.pg_namespace WHERE nspname = ANY(%s) "
        "AND has_schema_privilege('xcode_readonly', oid, 'USAGE')",
        (list(_READONLY_CLOSED_SCHEMAS),),
    )
    for r in usable:
        failures.append(f"xcode_readonly has USAGE on schema {r['nspname']} (expected none)")
    identity_grants = _rows(
        conn,
        "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
        "WHERE grantee = 'xcode_readonly' AND table_schema = 'identity'",
    )
    for r in identity_grants:
        failures.append(
            f"xcode_readonly has {r['privilege_type']} on "
            f"identity.{r['table_name']} (expected none)"
        )
    hash_grants = _rows(
        conn,
        """
        SELECT cg.table_schema, cg.table_name, cg.column_name
        FROM information_schema.column_privileges cg
        WHERE cg.grantee = 'xcode_readonly'
          AND (cg.column_name LIKE %s OR cg.column_name LIKE %s)
        """,
        ("%\\_hash", "%\\_digest"),
    )
    for r in hash_grants:
        failures.append(
            f"xcode_readonly has access to secret column "
            f"{r['table_schema']}.{r['table_name']}.{r['column_name']}"
        )
    return failures


def check_extensions_allow_list(conn: Conn) -> list[str]:
    rows = _rows(conn, "SELECT extname FROM pg_catalog.pg_extension")
    return [
        f"extension {r['extname']} is installed but not on the allow-list"
        for r in rows
        if str(r["extname"]) not in EXTENSION_ALLOW_LIST
    ]


_CHECKS: tuple[tuple[str, Check], ...] = (
    ("schemas exist", check_schemas_exist),
    ("roles exist", check_roles_exist),
    ("role attributes (connlimit, timeouts, not bypassrls)", check_role_attributes),
    ("row-level security binds every service role", check_row_security_binds_the_service_roles),
    (
        "xcode_app/xcode_operator have no table or sequence privileges",
        check_app_role_has_no_table_privileges,
    ),
    ("xcode_app cannot execute api.ops_*", check_app_cannot_execute_ops_routines),
    ("api.* routine properties", check_api_routine_properties),
    ("public schema is empty", check_public_schema_empty),
    ("declared tables exist with their primary keys", check_declared_tables),
    ("tenant tables have RLS and the tenant_isolation policy", check_tenant_tables_have_rls),
    ("declared indexes exist", check_declared_indexes),
    ("table privileges match the declared writes", check_declared_privileges),
    ("updated_at columns are touched by trigger", check_updated_at_triggers),
    ("tenant foreign keys start with organization_id", check_tenant_foreign_keys),
    ("code tables match the domain enums", check_code_tables_match_domain),
    ("no secret-named columns without _hash/_digest", check_secret_column_names),
    ("no dynamic SQL in routines", check_no_dynamic_sql),
    ("tenant routines enter their organization", check_tenant_routines_enter_organization),
    ("audit tables are append-only for the executor", check_audit_tables_append_only),
    ("xcode_readonly is locked out of identity and secret columns", check_readonly_locked_out),
    ("extensions within the allow-list", check_extensions_allow_list),
)
