"""The role files are re-runnable on a migrated database without changing any table grant.

``db/roles/README.md`` lets a DBA apply ``010`` to ``030`` again (a new role, a changed
setting); doing so must not hand ``xcode_api_executor`` back the ``UPDATE`` and ``DELETE``
that the migrations withheld from the append-only tables and the catalogue.
"""

from __future__ import annotations

from typing import Any

import psycopg

from xcode_api.db import verify
from xcode_api.db.migrate import find_db_dir

Conn = psycopg.Connection[dict[str, Any]]

_GRANTS = """
SELECT n.nspname || '.' || c.relname AS relation,
       pg_catalog.pg_get_userbyid(a.grantee) AS grantee,
       a.privilege_type
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
CROSS JOIN LATERAL aclexplode(c.relacl) AS a
WHERE n.nspname IN ('identity', 'tenancy', 'setup', 'revenue', 'pettycash', 'expenses', 'ops')
  AND a.grantee <> c.relowner
ORDER BY 1, 2, 3
"""


def _grants(conn: Conn) -> list[tuple[str, str, str]]:
    return [
        (str(r["relation"]), str(r["grantee"]), str(r["privilege_type"]))
        for r in conn.execute(_GRANTS).fetchall()
    ]


def test_reapplying_the_grants_file_leaves_every_table_grant_unchanged(owner_conn: Conn) -> None:
    before = _grants(owner_conn)
    owner_conn.execute((find_db_dir() / "roles" / "030_grants.sql").read_text(encoding="utf-8"))
    after = _grants(owner_conn)

    assert sorted(set(after) - set(before)) == []
    assert after == before
    assert ("tenancy.change_log", "xcode_api_executor", "DELETE") not in after
    assert ("ops.operator_actions", "xcode_api_executor", "UPDATE") not in after
    failing = {name for name, check in verify._CHECKS if check(owner_conn)}
    assert failing == set()
