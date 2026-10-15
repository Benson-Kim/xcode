"""The message catalogue (``http/messages.py``): every entry formats with sample parameters,
the sentences equal ``docs/06-http-contract.md`` section 3 character for character (the EN
DASH included), and the refusal handler renders problems, plain bodies and the 500 for a code
the catalogue lacks."""

from __future__ import annotations

import json
import re
import string
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from xcode_api.domain.errors import Conflict, Forbidden, NotFound, RuleViolation
from xcode_api.http.errors import register_exception_handlers
from xcode_api.http.messages import (
    CONFLICT_TITLE,
    FORBIDDEN_TITLE,
    INVALID_TITLE,
    MESSAGES,
    NOT_FOUND_TITLE,
    STALE_TITLE,
    Message,
)

DOC = Path(__file__).resolve().parents[2] / "docs" / "06-http-contract.md"
EN_DASH = "\u2013"
SERVICE_ONLY = {
    "session_invalid",
    "rate_limit_invalid",
    "organization_not_single",
    "seed_development_only",
    "seed_exists",
}
SAMPLES = {
    "value": "Mars/Olympus",
    "registration": "KDA 482M",
    "fleet": "A-17",
    "date": "2026-10-01",
    "earliest": "2026-10-01",
    "currency": "KES",
    "threshold": "4,000",
    "count": "10,001",
}


def _documented() -> dict[str, list[str]]:
    text = DOC.read_text(encoding="utf-8")
    section = text[text.index("## 3. Message catalogue") : text.index("## 4. Client facts")]
    rows: dict[str, list[str]] = {}
    for line in section.splitlines():
        match = re.match(r"\| `([a-z0-9_]+)`(?:, `([a-z0-9_]+)`)?[^|]*\| ([^|]+)\| (.+) \|$", line)
        if match is None:
            continue
        sentences = re.findall(r"`([^`]*)`", match.group(4))
        for code in (c for c in (match.group(1), match.group(2)) if c):
            rows[code] = sentences
    return rows


def _fields(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


@pytest.mark.parametrize("code", sorted(MESSAGES))
def test_every_entry_formats_with_sample_parameters(code: str) -> None:
    message = MESSAGES[code]
    parameters = {name: SAMPLES[name] for name in _fields(message.detail or "")}
    sentence = message.sentence(parameters)
    assert (sentence is None) == (message.detail is None)
    if sentence is not None:
        assert "{" not in sentence and "}" not in sentence
        assert sentence == sentence.strip()


def test_the_catalogue_holds_every_documented_code_and_nothing_else() -> None:
    assert set(MESSAGES) == set(_documented()) - SERVICE_ONLY


@pytest.mark.parametrize("code", sorted(MESSAGES))
def test_each_sentence_is_the_documented_one(code: str) -> None:
    message = MESSAGES[code]
    documented = _documented()[code]
    if message.detail is None:
        assert message.title in documented or documented == []
    elif message.title not in (INVALID_TITLE, FORBIDDEN_TITLE, None):
        assert documented[:2] == [message.title, message.detail]
    else:
        assert documented[0] == message.detail


def test_the_en_dash_strings_are_byte_for_byte() -> None:
    assert MESSAGES["page_out_of_range"].detail == (
        f"Page must be 1{EN_DASH}100000 and page size 1{EN_DASH}100."
    )
    assert MESSAGES["reason_length"].detail == f"A reason of 1{EN_DASH}500 characters is required."
    assert MESSAGES["recurring_schedule_shape"].detail == (
        f"Choose a weekday (0{EN_DASH}6), a month day (1{EN_DASH}28 / last), "
        f"or for yearly a month (1{EN_DASH}12) and a day."
    )
    encoded = (MESSAGES["page_out_of_range"].detail or "").encode()
    assert b"\xe2\x80\x93" in encoded


def test_statuses_and_titles_follow_the_error_model() -> None:
    for code, message in MESSAGES.items():
        if message.plain:
            assert message.title is None, code
            continue
        if message.status == 403:
            assert message.title == FORBIDDEN_TITLE, code
        elif message.status == 404:
            assert message.title == NOT_FOUND_TITLE, code
        elif message.status == 400:
            assert message.title == INVALID_TITLE, code
    assert MESSAGES["version_conflict"] == Message(409, STALE_TITLE, None)
    assert MESSAGES["unique_conflict"] == Message(409, CONFLICT_TITLE, None)
    assert MESSAGES["organization_name_slug"].plain
    assert MESSAGES["organization_slug_taken"].status == 409


def test_a_missing_sentence_parameter_is_a_key_error() -> None:
    with pytest.raises(KeyError):
        MESSAGES["time_zone_invalid"].sentence({})


def _app(refusal: Exception) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/refuse")
    async def refuse() -> None:
        raise refusal

    return app


async def _get(refusal: Exception) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app(refusal), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/refuse")


async def test_a_rule_refusal_is_a_problem_with_its_sentence() -> None:
    response = await _get(RuleViolation(code="time_zone_invalid", detail={"value": "Mars/X"}))
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    body = json.loads(response.content)
    assert body["type"] == "about:blank"
    assert body["title"] == "Invalid setup change"
    assert (
        body["detail"]
        == "'Mars/X' is an unknown or invalid time zone identifier. (Parameter 'value')"
    )
    assert "value" not in body


async def test_a_plain_refusal_has_only_a_detail() -> None:
    response = await _get(Conflict(code="organization_slug_taken"))
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    assert json.loads(response.content) == {"detail": "This organization slug is already in use."}


async def test_a_refusal_without_a_sentence_omits_the_detail() -> None:
    response = await _get(Forbidden(code="permission_missing"))
    body = json.loads(response.content)
    assert (response.status_code, body["title"]) == (403, FORBIDDEN_TITLE)
    assert "detail" not in body
    response = await _get(NotFound(code="not_found"))
    assert (response.status_code, json.loads(response.content)["title"]) == (404, NOT_FOUND_TITLE)


_STORED_CELL = {
    "day": "2026-10-05",
    "status": "amount",
    "expected": 1000.0,
    "amount": 5000.5,
    "reason": None,
    "note": None,
    "can_edit": True,
    "edited_after_capture": False,
    "version": 2,
}


async def test_extension_members_come_from_the_detail_in_camel_case() -> None:
    response = await _get(
        Conflict(code="revenue_version_conflict", detail={"current": _STORED_CELL})
    )
    body = json.loads(response.content)
    assert body["title"] == "This day already has a different record."
    assert list(body["current"].items()) == [
        ("date", "2026-10-05"),
        ("status", "amount"),
        ("expected", 1000),
        ("amount", 5000.5),
        ("reason", None),
        ("note", None),
        ("canEdit", True),
        ("editedAfterCapture", False),
        ("version", 2),
    ]
    response = await _get(Conflict(code="pettycash_already_saved", detail={"current": None}))
    assert json.loads(response.content)["current"] is None


async def test_a_member_that_does_not_fit_its_contract_model_is_a_500() -> None:
    current = {**_STORED_CELL, "status": "lost"}
    response = await _get(Conflict(code="revenue_version_conflict", detail={"current": current}))
    assert response.status_code == 500
    assert "current" not in json.loads(response.content)


async def test_a_code_the_catalogue_lacks_is_a_500_without_detail() -> None:
    response = await _get(RuleViolation(code="no_such_code"))
    assert response.status_code == 500
    body = json.loads(response.content)
    assert body["title"] == "An error occurred while processing your request."
    assert "detail" not in body
    response = await _get(RuleViolation(code="time_zone_invalid"))
    assert response.status_code == 500


async def test_a_day_rows_400_names_its_vehicle_and_a_403_keeps_its_sentence() -> None:
    response = await _get(
        RuleViolation(code="revenue_future_date", detail={"vehicle_registration": "KDA 103A"})
    )
    body = json.loads(response.content)
    assert (response.status_code, body["detail"]) == (
        400,
        "KDA 103A: Revenue cannot be recorded for a future date.",
    )
    assert "vehicleRegistration" not in body
    response = await _get(
        Forbidden(code="revenue_capture_permission", detail={"vehicle_registration": "KDA 103A"})
    )
    assert json.loads(response.content)["detail"] == (
        'Recording a day that has no record yet needs the permission "Capture revenue".'
    )


async def test_a_day_conflict_names_the_vehicle_and_carries_its_cell() -> None:
    vehicle = "0b5e2a4e-6f3c-4c55-9a46-8d0f4a2b7e11"
    response = await _get(
        Conflict(
            code="revenue_day_conflict",
            detail={"vehicle_id": vehicle, "registration": "KDA 482M", "current": _STORED_CELL},
        )
    )
    body = json.loads(response.content)
    assert (response.status_code, body["title"]) == (
        409,
        "This day already has a different record.",
    )
    assert body["detail"] == (
        "KDA 482M was changed after you opened the day. Check its current record and save again."
    )
    assert body["vehicleId"] == vehicle
    assert body["current"]["date"] == "2026-10-05"
