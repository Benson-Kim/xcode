"""Shared contract types: ApiModel base, Money, Instant, Page, ProblemDetails and the
response documentation of problem answers (docs/06 section 1.2)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Context, Decimal, InvalidOperation
from typing import Annotated, Any, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
)
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    @classmethod
    def from_record(cls, record: Any) -> Self:
        """Build the wire model from a domain record whose field names are the model's."""
        return cls.model_validate(dataclasses.asdict(record))


_DECIMAL_MAX = Decimal(2**96 - 1)
_DECIMAL_SCALE = Decimal(1).scaleb(-28)
_WIDE = Context(prec=60)


def _to_decimal(value: object) -> Decimal:
    decimal_value = _read_decimal(value)
    # What a .NET decimal holds: beyond it the .NET binder refused the body, and PostgreSQL
    # cannot parse such an exponent at all; past 28 places .NET rounded the digits away.
    if not decimal_value.is_finite() or decimal_value.copy_abs() > _DECIMAL_MAX:
        raise ValueError("money must be a number")
    exponent = decimal_value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -28:
        decimal_value = decimal_value.quantize(_DECIMAL_SCALE, context=_WIDE)
    return decimal_value


def _read_decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("money must be a number")
    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, int):
        decimal_value = Decimal(value)
    elif isinstance(value, str):
        try:
            decimal_value = Decimal(value)
        except InvalidOperation:
            raise ValueError("money must be a number") from None
    elif isinstance(value, float):
        # A JSON float reaches here; its decimal string is exact for the digits sent.
        decimal_value = Decimal(str(value))
    else:
        raise ValueError("money must be a number")
    return decimal_value


def _to_money(value: object) -> Decimal:
    decimal_value = _to_decimal(value)
    exponent = decimal_value.as_tuple().exponent
    if not isinstance(exponent, int) or -exponent > 2:
        raise ValueError("money must have at most two decimal places")
    return decimal_value


def _money_to_json(value: Decimal) -> float | int:
    # pydantic writes a Decimal as a JSON string; the contract (and .NET) send a number.
    # Amounts are below 10^12 with two decimals, well within float's exact range.
    return int(value) if value == value.to_integral_value() else float(value)


Money = Annotated[
    Decimal,
    BeforeValidator(_to_money),
    PlainSerializer(_money_to_json, return_type=Any, when_used="json"),
]


def _instant_to_json(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


# An instant on the wire: UTC, six fractional digits, offset +00:00 (docs/06 section 1.2).
Instant = Annotated[
    datetime,
    PlainSerializer(_instant_to_json, return_type=str, when_used="json"),
]


# An amount the routine checks itself (an approval limit): a JSON number read exactly, served as
# a number, with no rule of its own here.
Amount = Annotated[
    Decimal,
    BeforeValidator(_to_decimal),
    PlainSerializer(_money_to_json, return_type=Any, when_used="json"),
]


class ProblemDetails(ApiModel):
    """RFC 9457 problem details. Optional members are omitted when null."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
    )

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    request_id: str = Field(alias="requestId")


class Page[T](ApiModel):
    """A page of results: ``items``, ``pageNumber``, ``pageSize``, ``total``."""

    items: list[T]
    page_number: int
    page_size: int
    total: int


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI documentation of problem answers: ``application/problem+json`` bodies of
    ``ProblemDetails``; 401 is the empty bearer refusal."""
    reference = {"$ref": "#/components/schemas/ProblemDetails"}
    documented: dict[int | str, dict[str, Any]] = {
        401: {"description": "Missing, invalid or revoked access token (empty body)"}
    }
    for status in statuses:
        documented[status] = {
            "model": ProblemDetails,
            "description": "Problem details",
            "content": {"application/problem+json": {"schema": reference}},
        }
    return documented
