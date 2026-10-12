"""The OpenAPI document as the contract states it (``docs/06-http-contract.md`` section 1.11).

FastAPI documents a 422 on every operation with parameters or a body, but these routes
answer a refused request with 400 (section 1.6), so those responses and their two schemas
are dropped. Operations the catalogue gives no ``operationId`` (auth and health) lose the
generated one, as the .NET document had none.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

_FRAMEWORK_SCHEMAS = ("HTTPValidationError", "ValidationError")


def install(app: FastAPI, routers: Sequence[APIRouter]) -> None:
    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = build(app, routers)
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


def build(app: FastAPI, routers: Sequence[APIRouter]) -> dict[str, Any]:
    document = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        routes=app.routes,
    )
    unnamed = {
        (method.lower(), route.path_format)
        for router in routers
        for route in router.routes
        if isinstance(route, APIRoute) and route.include_in_schema and route.operation_id is None
        for method in route.methods or ()
    }
    for path, item in document.get("paths", {}).items():
        for method, operation in item.items():
            responses = operation.get("responses", {})
            if _is_framework_validation(responses.get("422")):
                del responses["422"]
            if (method, path) in unnamed:
                operation.pop("operationId", None)
    schemas = document.get("components", {}).get("schemas", {})
    for name in _FRAMEWORK_SCHEMAS:
        schemas.pop(name, None)
    return document


def _is_framework_validation(response: dict[str, Any] | None) -> bool:
    if response is None:
        return False
    schema = response.get("content", {}).get("application/json", {}).get("schema", {})
    return bool(schema.get("$ref") == "#/components/schemas/HTTPValidationError")
