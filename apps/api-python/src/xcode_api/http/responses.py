"""The JSON response every contract route answers with: ``application/json; charset=utf-8``,
compact separators, UTF-8 text as is, and no NaN or infinity (``docs/06-http-contract.md``
section 1.2)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel
from starlette.responses import Response


class JsonResponse(Response):
    media_type = "application/json; charset=utf-8"

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")


def respond(content: BaseModel | list[BaseModel], status_code: int = 200) -> JsonResponse:
    """A contract model (or a list of them) under its camelCase names, in field order."""
    if isinstance(content, list):
        return JsonResponse(
            [item.model_dump(mode="json", by_alias=True) for item in content],
            status_code=status_code,
        )
    return JsonResponse(content.model_dump(mode="json", by_alias=True), status_code=status_code)
