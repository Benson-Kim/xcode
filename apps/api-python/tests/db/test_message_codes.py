"""Every refusal code the routines raise has a sentence in ``http/messages.py``, every entry
is raised somewhere, and each code's SQLSTATE agrees with the status the catalogue answers
(``docs/06-http-contract.md`` section 3). The scan reads the routine files, the trigger
functions of the migrations and the service's own refusals; the exceptions are listed below
with their reasons."""

from __future__ import annotations

import re

from xcode_api.db.migrate import find_db_dir
from xcode_api.http.messages import MESSAGES

DB = find_db_dir()
SRC = DB.parent / "src" / "xcode_api"

_REFUSE = re.compile(r"tenancy\.refuse\(\s*'([a-z0-9_]+)'(?:\s*,\s*'(XC\d{3})')?")
_CHECK_MONEY = re.compile(r"tenancy\.check_money\([^,()]+,\s*'([a-z0-9_]+)'")
_TRIGGER = re.compile(r"ERRCODE = '(XC\d{3})',\s*MESSAGE = '([a-z0-9_]+)'")
_SERVICE = re.compile(r'code="([a-z0-9_]+)"|UNIQUE_CONFLICT = "([a-z0-9_]+)"')

# Raised to the service or the CLI only, never rendered as a sentence.
SERVICE_ONLY = {
    "session_invalid": "the bearer check answers an empty 401",
    "rate_limit_invalid": "bounds the service itself chose: a configuration bug, answered 500",
    "organization_not_single": "provisioning only; the CLI prints the code",
    "seed_development_only": "demo seed only; the CLI prints the code",
    "seed_exists": "demo seed only; the CLI prints the code",
}
# Trigger functions are backstops behind the routines' own checks; a request that reaches one
# is a routine bug and answers 500, so they have no sentence.
TRIGGER_CODES = {
    "registration_immutable": "behind vehicle_registration_change",
    "business_date_immutable": "behind the revenue capture rules",
    "allocation_sum_mismatch": "behind recurring_allocation_sum",
}
# A code whose SQLSTATE differs from the catalogue's status, where no HTTP answer depends on it.
STATUS_EXCEPTIONS = {
    ("people_contact_taken", "XC409"): "api.ops_provision_user: the CLI prints the code",
}
_STATUS_OF = {"XC403": 403, "XC404": 404, "XC409": 409, "XC422": 400, "XC429": 429}


def _routine_refusals() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in (DB / "routines").rglob("*.sql"):
        text = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))
        found |= {(code, sqlstate or "XC422") for code, sqlstate in _REFUSE.findall(text)}
        found |= {(code, "XC422") for code in _CHECK_MONEY.findall(text)}
    return found


def _trigger_codes() -> set[str]:
    codes: set[str] = set()
    for path in (DB / "migrations").glob("*.sql"):
        if path.name.endswith(".down.sql"):
            continue
        codes |= {code for _, code in _TRIGGER.findall(path.read_text(encoding="utf-8"))}
    return codes


def _service_codes() -> set[str]:
    codes: set[str] = set()
    for path in SRC.rglob("*.py"):
        for plain, constant in _SERVICE.findall(path.read_text(encoding="utf-8")):
            codes.add(plain or constant)
    return codes


def _raised() -> set[str]:
    return {code for code, _ in _routine_refusals()} | _service_codes()


def test_every_code_a_routine_raises_has_a_sentence() -> None:
    missing = sorted(
        code for code, _ in _routine_refusals() if code not in MESSAGES and code not in SERVICE_ONLY
    )
    assert missing == []


def test_every_code_the_service_raises_has_a_sentence() -> None:
    assert sorted(_service_codes() - set(MESSAGES)) == []


def test_every_entry_is_raised_somewhere() -> None:
    raised = _raised()
    assert sorted(code for code in MESSAGES if code not in raised) == []


def test_trigger_codes_are_the_listed_backstops() -> None:
    assert _trigger_codes() == set(TRIGGER_CODES)
    assert not set(TRIGGER_CODES) & set(MESSAGES)


def test_service_only_codes_have_no_sentence() -> None:
    assert not set(SERVICE_ONLY) & set(MESSAGES)


def test_each_sqlstate_matches_the_status_of_its_code() -> None:
    mismatched = []
    for code, sqlstate in sorted(_routine_refusals()):
        message = MESSAGES.get(code)
        if message is None or (code, sqlstate) in STATUS_EXCEPTIONS:
            continue
        if _STATUS_OF[sqlstate] != message.status:
            mismatched.append((code, sqlstate, message.status))
    assert mismatched == []
