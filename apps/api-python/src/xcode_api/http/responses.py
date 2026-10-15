"""The JSON response every contract route answers with: ``application/json; charset=utf-8``,
compact separators, UTF-8 text as is, and no NaN or infinity (``docs/06-http-contract.md``
section 1.2)."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel
from starlette.responses import Response

from ..domain.reports import ExportFile


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


def file_response(file: ExportFile) -> Response:
    """A whole file as the answer: its content type, and ``Content-Disposition: attachment``
    with the name twice, as ASP.NET Core wrote it: quoted, with every character outside
    printable ASCII and the quote and backslash replaced by ``_``, and percent-encoded UTF-8
    after ``filename*`` (``docs/06-http-contract.md`` 2.13.5)."""
    ascii_name = "".join(
        ch if " " <= ch <= "~" and ch not in ('"', chr(92)) else "_" for ch in file.file_name
    )
    encoded = quote(file.file_name, safe="")
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"
    return Response(
        content=file.content,
        media_type=file.content_type,
        headers={"content-disposition": disposition},
    )
