"""The routine-contract version this package expects.

Bumped in lockstep with ``api.meta_contract_version()`` whenever a routine signature
changes (``docs/05-routines.md`` section 1.1). Startup refuses a database whose version
differs from this constant.
"""

from __future__ import annotations

EXPECTED_CONTRACT_VERSION = 5
