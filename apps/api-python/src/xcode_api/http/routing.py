"""The route class of the ``/setup`` routers: a body route answers 415 with an empty body
unless the request says ``Content-Type: application/json`` (``docs/06-http-contract.md``
section 1.7). A route whose body is optional also takes no body and no content type at all,
which is how released clients call activate and deactivate. A query value or a body string
holding U+0000 or an unpaired surrogate, which PostgreSQL text cannot store, is a 400 before
the handler runs."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from email.message import Message
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException


def _is_json(content_type: str | None) -> bool:
    if not content_type:
        return False
    parsed = Message()
    parsed["content-type"] = content_type
    subtype = parsed.get_content_subtype()
    return parsed.get_content_maintype() == "application" and (
        subtype == "json" or subtype.endswith("+json")
    )


UNSTORABLE_TEXT = "Text cannot contain U+0000 or an unpaired surrogate."


def _storable(value: object) -> bool:
    if isinstance(value, str):
        if chr(0) in value:
            return False
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return False
        return True
    if isinstance(value, dict):
        return all(_storable(key) and _storable(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_storable(item) for item in value)
    return True


def _unstorable(*location: str) -> RequestValidationError:
    return RequestValidationError(
        [{"type": "value_error", "loc": location, "msg": UNSTORABLE_TEXT, "input": None}]
    )


class SetupRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        body_field = self.body_field

        async def route(request: Request) -> Response:
            for name, value in request.query_params.multi_items():
                if not (_storable(name) and _storable(value)):
                    raise _unstorable("query", name)
            if body_field is not None:
                body = await request.body()
                optional_and_absent = not body_field.field_info.is_required() and not body
                if not optional_and_absent and not _is_json(request.headers.get("content-type")):
                    raise HTTPException(status_code=415)
                if body and not _storable(await _parsed(request)):
                    raise _unstorable("body")
            return await handler(request)

        return route


async def _parsed(request: Request) -> object:
    """The JSON body, cached on the request for the handler; ``None`` when it does not parse,
    which the handler then refuses itself."""
    try:
        return await request.json()
    except ValueError:
        return None
