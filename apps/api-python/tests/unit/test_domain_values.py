"""Value objects and enumeration properties of ``xcode_api.domain``: normalisation and refusals.

The bounds mirror the columns of ``docs/04-schema.md`` (``numeric(14,2)`` money, versions that
start at 0 or 1, pages of 1 to 100 000 by 1 to 100); the routines check them again.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from xcode_api.domain.revenue import NoEarningsReason
from xcode_api.domain.setup import ExpenseBucket, RecurrenceFrequency, RecurringKind
from xcode_api.domain.values import (
    MAX_PAGE,
    MAX_PAGE_SIZE,
    MONEY_CAP,
    DeviceId,
    DeviceName,
    DeviceToken,
    Email,
    Money,
    PageRequest,
    PhoneNumber,
    Pin,
    RefreshToken,
    VerificationCode,
    Version,
    WriteOutcome,
    WriteResult,
)

from ..support.phone_vectors import PHONE_VECTORS


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1500", Decimal("1500.00")),
        ("1.5", Decimal("1.50")),
        (" 21000.00 ", Decimal("21000.00")),
        (Decimal("0.01"), Decimal("0.01")),
        (7, Decimal("7.00")),
        ("1E+3", Decimal("1000.00")),
        ("999999999999.99", MONEY_CAP),
    ],
)
def test_money_normalises_to_two_places(value: Decimal | int | str, expected: Decimal) -> None:
    amount = Money(value).amount
    assert amount == expected
    assert amount.as_tuple().exponent == -2


@pytest.mark.parametrize("value", ["0", "0.00", "-1", "-0.01"])
def test_money_refuses_zero_and_negative(value: str) -> None:
    with pytest.raises(ValueError, match="positive"):
        Money(value)


@pytest.mark.parametrize("value", ["1.005", "0.001", Decimal("12.345")])
def test_money_refuses_more_than_two_places_instead_of_rounding(value: str | Decimal) -> None:
    with pytest.raises(ValueError, match="two decimal places"):
        Money(value)


@pytest.mark.parametrize("value", ["1000000000000", "1000000000000.00", "1e30"])
def test_money_refuses_the_cap_and_above(value: str) -> None:
    with pytest.raises(ValueError, match="below"):
        Money(value)


@pytest.mark.parametrize("value", ["", "abc", "NaN", "Infinity", "1,000", True, 1.5, None])
def test_money_refuses_what_is_not_a_decimal(value: object) -> None:
    with pytest.raises(ValueError):
        Money(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [0, 1, 2**62])
def test_version_accepts_zero_and_up(value: int) -> None:
    assert Version(value).value == value


@pytest.mark.parametrize("value", [-1, True, 1.0, "1"])
def test_version_refuses_negatives_and_non_integers(value: object) -> None:
    with pytest.raises(ValueError):
        Version(value)  # type: ignore[arg-type]


def test_page_request_defaults() -> None:
    assert PageRequest() == PageRequest(page=1, page_size=25)


@pytest.mark.parametrize(("page", "size"), [(1, 1), (MAX_PAGE, MAX_PAGE_SIZE), (3, 50)])
def test_page_request_accepts_the_bounds(page: int, size: int) -> None:
    request = PageRequest(page=page, page_size=size)
    assert (request.page, request.page_size) == (page, size)


@pytest.mark.parametrize(
    ("page", "size"),
    [(0, 25), (MAX_PAGE + 1, 25), (1, 0), (1, MAX_PAGE_SIZE + 1), (1, 1000), (True, 25)],
)
def test_page_request_refuses_out_of_range_instead_of_clamping(page: int, size: int) -> None:
    with pytest.raises(ValueError):
        PageRequest(page=page, page_size=size)


@pytest.mark.parametrize(
    "value", ["a", "a" * 128, "x!~", "sp ace", "caf" + chr(0xE9), chr(0x1F4F1)]
)
def test_device_id_is_opaque_text_of_1_to_128_code_points(value: str) -> None:
    assert DeviceId(value).value == value


@pytest.mark.parametrize("value", ["", "a" * 129, chr(0x1F4F1) * 129, "nul" + chr(0)])
def test_device_id_rejects_empty_too_long_or_unstorable(value: str) -> None:
    with pytest.raises(ValueError):
        DeviceId(value)


def test_email_normalises() -> None:
    assert Email("  User@Example.COM ").value == "user@example.com"


def test_email_allows_320_characters() -> None:
    value = "x" * 64 + "@" + "d" * 251 + ".com"
    assert len(value) == 320
    assert Email(value).value == value


@pytest.mark.parametrize(
    "value",
    [
        "noat",
        "two@@ats.com",
        "two@at@s.com",
        "@nolocal.com",
        "nodomain@",
        "x" * 64 + "@" + "d" * 252 + ".com",
        "Jane Doe <jane@example.com>",
        '"jane"@example.com',
        "jane doe@example.com",
        "jane@example..com",
        "jane@.example.com",
        "jane@example.com.",
        "jane@exa" + chr(1) + "mple.com",
    ],
)
def test_email_rejects_anything_but_local_at_domain(value: str) -> None:
    with pytest.raises(ValueError):
        Email(value)
    assert Email.parse(value) is None


@pytest.mark.parametrize(("raw", "normalized"), PHONE_VECTORS)
def test_phone_number_normalisation_table(raw: str, normalized: str | None) -> None:
    parsed = PhoneNumber.parse(raw)
    assert (None if parsed is None else parsed.value) == normalized


def test_phone_number_stays_out_of_repr() -> None:
    parsed = PhoneNumber.parse("0712345678")
    assert parsed is not None
    assert "712345678" not in repr(parsed)


def test_a_pin_as_a_request_carries_it_is_at_most_eight_characters() -> None:
    assert Pin.MAX_LENGTH == 8


@pytest.mark.parametrize(
    ("raw", "name"),
    [
        ("", None),
        ("   ", None),
        ("  Tecno Spark 10 (work)  ", "Tecno Spark 10 (work)"),
        ("A", "A"),
        ("x" * 60, "x" * 60),
        ("Samsung A14+ 4G-1.2", "Samsung A14+ 4G-1.2"),
    ],
)
def test_device_name_accepts_the_narrow_alphabet(raw: str, name: str | None) -> None:
    assert DeviceName.parse(raw) == name


@pytest.mark.parametrize(
    "raw",
    ["x" * 61, "(phone)", "-phone", "phone: call 0700", "https://evil", "a@b", "phone/1", "tél"],
)
def test_device_name_refuses_anything_else(raw: str) -> None:
    with pytest.raises(ValueError):
        DeviceName.parse(raw)


@pytest.mark.parametrize(
    ("token", "valid"),
    [
        ("a" * 43, True),
        ("A-_9", True),
        ("x" * 64, True),
        ("", False),
        ("x" * 65, False),
        ("a+b", False),
        ("a=", False),
    ],
)
def test_device_token_shape(token: str, valid: bool) -> None:
    assert DeviceToken.valid(token) is valid


def test_secret_values_stay_out_of_repr() -> None:
    assert "482913" not in repr(VerificationCode("482913"))
    assert "token-value" not in repr(RefreshToken("token-value"))


def test_code_and_refresh_token_bounds() -> None:
    assert VerificationCode("x" * 32).value == "x" * 32
    assert RefreshToken("x" * 256).value == "x" * 256
    with pytest.raises(ValueError):
        VerificationCode("x" * 33)
    with pytest.raises(ValueError):
        RefreshToken("x" * 257)


def test_write_result_carries_the_outcome_word() -> None:
    result = WriteResult(id=uuid4(), version=1, outcome=WriteOutcome("replayed"))
    assert result.outcome is WriteOutcome.REPLAYED
    assert [o.value for o in WriteOutcome] == ["created", "updated", "unchanged", "replayed"]


def test_no_earnings_reason_labels_and_snapshot_names() -> None:
    assert [(r.value, r.label, r.snapshot_name) for r in NoEarningsReason] == [
        (1, "Garage", "Garage"),
        (2, "Arrest", "Arrest"),
        (3, "No Crew", "NoCrew"),
        (4, "Other", "Other"),
    ]


def test_setup_code_labels() -> None:
    assert [k.label for k in RecurringKind] == ["Cost", "Savings"]
    assert [f.label for f in RecurrenceFrequency] == ["Daily", "Weekly", "Monthly", "Yearly"]
    assert [b.label for b in ExpenseBucket] == [
        "repairs and maintenance",
        "recurring charges",
        "loan repayments",
    ]
