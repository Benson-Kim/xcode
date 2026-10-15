"""``identity.normalize_phone`` and its Python twin ``PhoneNumber.parse`` agree on every
vector of the shared table and on every non-ASCII decimal digit Unicode knows."""

from __future__ import annotations

import pytest

from xcode_api.domain.values import PhoneNumber

from ..support.phone_vectors import PHONE_VECTORS
from ..support.scenario import Conn


@pytest.mark.parametrize(("raw", "normalized"), PHONE_VECTORS)
def test_routine_and_python_twin_normalise_alike(
    executor: Conn, raw: str, normalized: str | None
) -> None:
    row = executor.execute("SELECT identity.normalize_phone(%s) AS phone", (raw,)).fetchone()
    assert row is not None
    parsed = PhoneNumber.parse(raw)
    assert row["phone"] == normalized
    assert (None if parsed is None else parsed.value) == normalized


def test_every_non_ascii_decimal_digit_makes_the_input_not_a_number(executor: Conn) -> None:
    digits = [chr(c) for c in range(0x80, 0x110000) if chr(c).isdecimal()]
    # Stripping the digit would leave a valid number; it must be refused instead.
    inputs = [digit + "0712345678" for digit in digits] + ["0712345678" + digit for digit in digits]
    row = executor.execute(
        "SELECT array_agg(raw) FILTER (WHERE identity.normalize_phone(raw) IS NOT NULL) AS kept "
        "FROM unnest(%s::text[]) AS raw",
        (inputs,),
    ).fetchone()
    assert row is not None
    assert row["kept"] is None
    assert [raw for raw in inputs if PhoneNumber.parse(raw) is not None] == []
