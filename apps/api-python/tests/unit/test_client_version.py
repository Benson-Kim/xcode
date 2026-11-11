"""The minimum mobile version: what a dotted numeric version is, how two compare, and how
``XCODE_MIN_MOBILE_VERSION`` is validated before the API starts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from xcode_api.http.client_version import ClientVersionMiddleware
from xcode_api.settings import Settings, dotted_version


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1", (1, 0, 0, 0)),
        ("1.4", (1, 4, 0, 0)),
        ("1.4.0", (1, 4, 0, 0)),
        ("1.4.0.7", (1, 4, 0, 7)),
        ("10.0.12", (10, 0, 12, 0)),
        ("01.4.0", (1, 4, 0, 0)),
    ],
)
def test_a_dotted_numeric_version_pads_to_four_parts(text: str, expected: tuple[int, ...]) -> None:
    assert dotted_version(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "1.",
        ".1",
        "1..4",
        "1.4.0-beta",
        "v1.4.0",
        "1.4.0.0.1",
        "1234567.0",
        " 1.4.0",
        "1.4.0\n",
        "\u0661.\u0664",
        "abc",
    ],
)
def test_anything_else_is_not_a_version(text: str) -> None:
    assert dotted_version(text) is None


@pytest.mark.parametrize(
    ("older", "newer"),
    [("1.4.0", "1.4.1"), ("1.4.9", "1.10.0"), ("1.9", "2"), ("0.9.9", "1.0.0")],
)
def test_versions_compare_part_by_part_not_as_text(older: str, newer: str) -> None:
    low, high = dotted_version(older), dotted_version(newer)
    assert low is not None and high is not None
    assert low < high


def test_trailing_zeros_do_not_change_a_version() -> None:
    assert dotted_version("1.4") == dotted_version("1.4.0") == dotted_version("1.4.0.0")


def test_no_minimum_is_the_default_and_serves_every_build() -> None:
    settings = Settings.for_tests()
    assert settings.min_mobile_version == ""
    assert settings.minimum_mobile_version is None


def test_a_valid_minimum_is_kept_as_written_and_compared_as_numbers() -> None:
    settings = Settings.for_tests(min_mobile_version="1.4.0")
    assert settings.minimum_mobile_version == (1, 4, 0, 0)
    assert settings.summary()["min_mobile_version"] == "1.4.0"


@pytest.mark.parametrize("value", ["latest", "1.4.0-beta", "1..4", "v2"])
def test_a_malformed_minimum_refuses_to_start(value: str) -> None:
    with pytest.raises(ValidationError, match="XCODE_MIN_MOBILE_VERSION"):
        Settings.for_tests(min_mobile_version=value)


def test_the_middleware_refuses_a_minimum_that_is_not_a_version() -> None:
    async def app(scope: object, receive: object, send: object) -> None:
        return None

    with pytest.raises(ValueError, match="dotted numeric"):
        ClientVersionMiddleware(app, minimum_version="latest")
