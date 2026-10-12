"""The OpenAPI document, auth half (``docs/06-http-contract.md`` section 1.11): the sign-in
operation documents 202 and 423 with ``AuthResponse`` and no security, the two bearer
operations carry ``Bearer`` and document 401, the scheme is ``http``/``bearer``/``JWT``, and
auth routes are untagged."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from xcode_api.cli.main import main
from xcode_api.container import Container
from xcode_api.main import create_app
from xcode_api.settings import Settings

from ..support.fakes import FakeOpsRepository

AUTH_RESPONSE = "#/components/schemas/AuthResponse"
ANONYMOUS = (
    "/auth/sign-in",
    "/auth/unlock",
    "/auth/verify-device",
    "/auth/setup-pin/request",
    "/auth/setup-pin/verify",
    "/auth/setup-pin/complete",
    "/auth/pin-reset/request",
    "/auth/pin-reset/verify",
    "/auth/pin-reset/complete",
    "/auth/refresh",
    "/auth/sign-out",
)


async def _document(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get("/openapi/v1.json")
    assert response.status_code == 200
    document: dict[str, Any] = response.json()
    return document


async def test_sign_in_documents_202_and_423_with_the_envelope_and_no_security(
    client: httpx.AsyncClient,
) -> None:
    document = await _document(client)
    assert "/auth/sign-in" in document["paths"]
    operation = document["paths"]["/auth/sign-in"]["post"]
    for status in ("200", "202", "423"):
        schema = operation["responses"][status]["content"]["application/json"]["schema"]
        assert schema == {"$ref": AUTH_RESPONSE}, status
    assert "security" not in operation


async def test_every_anonymous_auth_route_is_unsecured_and_untagged(
    client: httpx.AsyncClient,
) -> None:
    document = await _document(client)
    for path in ANONYMOUS:
        operation = document["paths"][path]["post"]
        assert "security" not in operation, path
        assert not operation.get("tags"), path
        assert "429" in operation["responses"], path


async def test_the_bearer_routes_carry_the_bearer_scheme_and_document_401(
    client: httpx.AsyncClient,
) -> None:
    document = await _document(client)
    operations = {
        "/auth/session": document["paths"]["/auth/session"]["get"],
        "/auth/devices/{id}/revoke": document["paths"]["/auth/devices/{id}/revoke"]["post"],
    }
    for path, operation in operations.items():
        assert operation["security"] == [{"Bearer": []}], path
        assert "401" in operation["responses"], path
        assert not operation.get("tags"), path
    assert "403" in operations["/auth/devices/{id}/revoke"]["responses"]
    assert document["components"]["securitySchemes"]["Bearer"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }


async def test_the_envelope_schema_lists_the_seven_properties_in_order(
    client: httpx.AsyncClient,
) -> None:
    document = await _document(client)
    schema = document["components"]["schemas"]["AuthResponse"]
    assert list(schema["properties"]) == [
        "status",
        "accessToken",
        "refreshToken",
        "retryAfterSeconds",
        "developmentCode",
        "maskedEmail",
        "minimumPinLength",
    ]
    session = document["components"]["schemas"]["AuthSessionResponse"]
    assert list(session["properties"]) == [
        "userId",
        "firstName",
        "lastName",
        "role",
        "permissions",
    ]


async def test_the_setup_routes_are_secured_tagged_and_document_their_problems(
    client: httpx.AsyncClient,
) -> None:
    document = await _document(client)
    assert "/setup/people" in document["paths"]
    deactivate = document["paths"]["/setup/people/{id}/deactivate"]["post"]
    assert deactivate["operationId"] == "DeactivatePerson"
    assert deactivate["security"] == [{"Bearer": []}]
    assert deactivate["tags"] == ["Setup"]
    conflict = deactivate["responses"]["409"]["content"]["application/problem+json"]
    assert conflict["schema"] == {"$ref": "#/components/schemas/ProblemDetails"}
    expected = {
        ("/setup/access/catalog", "get"): ("GetAccessCatalog", "Setup"),
        ("/setup/access/roles", "get"): ("ListAccessRoles", "Setup"),
        ("/setup/access/scope-options", "get"): ("GetAccessScopeOptions", "Setup"),
        ("/setup/access/me", "get"): ("GetMyAccessScope", "Setup"),
        ("/setup/people", "get"): ("ListPeople", "Setup"),
        ("/setup/people", "post"): ("CreatePerson", "Setup"),
        ("/setup/people/{id}", "get"): ("GetPerson", "Setup"),
        ("/setup/people/{id}", "put"): ("UpdatePerson", "Setup"),
        ("/setup/people/{id}/activate", "post"): ("ActivatePerson", "Setup"),
        ("/setup/people/{id}/sign-out", "post"): ("SignOutPerson", "Setup"),
        ("/setup/people/{id}/pin-reset", "post"): ("RequirePersonPinReset", "Setup"),
        ("/setup/people/{id}/trusted-devices/{deviceId}/remove", "post"): (
            "RemovePersonDevice",
            "Setup",
        ),
        ("/setup/history", "get"): ("ListSetupHistory", "Setup"),
        ("/setup/companies", "get"): ("ListSetupCompanies", "Setup"),
        ("/setup/companies", "post"): ("CreateSetupCompany", "Setup"),
        ("/setup/companies/{id}", "put"): ("RenameSetupCompany", "Setup"),
        ("/setup/companies/{id}/archive", "post"): ("ArchiveSetupCompany", "Setup"),
        ("/setup/companies/{id}/restore", "post"): ("RestoreSetupCompany", "Setup"),
        ("/setup/vehicles", "get"): ("ListSetupVehicles", "Setup"),
        ("/setup/vehicles", "post"): ("CreateSetupVehicle", "Setup"),
        ("/setup/vehicles/{id}", "put"): ("UpdateSetupVehicle", "Setup"),
        ("/setup/vehicles/company-options", "get"): ("ListVehicleCompanyOptions", "Setup"),
        ("/setup/vehicles/{id}/retire", "post"): ("RetireSetupVehicle", "Setup"),
        ("/setup/vehicles/{id}/restore", "post"): ("RestoreSetupVehicle", "Setup"),
        ("/setup/vehicles/{id}/report", "get"): ("GetSetupVehicleReport", "Setup"),
        ("/setup/vehicles/{id}/targets", "get"): ("ListVehicleTargets", "Setup"),
        ("/setup/vehicles/{id}/targets", "post"): ("SaveVehicleTargets", "Setup"),
        ("/setup/vehicle-targets/{id}/remove", "post"): ("RemoveVehicleTargets", "Setup"),
        ("/setup/recurring", "get"): ("ListSetupRecurring", "Setup"),
        ("/setup/recurring/vehicle-options", "get"): ("ListRecurringVehicleOptions", "Setup"),
        ("/setup/recurring", "post"): ("CreateSetupRecurring", "Setup"),
        ("/setup/recurring/{id}", "put"): ("ReviseSetupRecurring", "Setup"),
        ("/setup/recurring/{id}/stop", "post"): ("StopSetupRecurring", "Setup"),
        ("/setup/recurring/{id}/restore", "post"): ("CancelSetupRecurringStop", "Setup"),
        ("/setup/expense-categories", "get"): ("ListExpenseCategories", "Setup"),
        ("/setup/expense-items/options", "get"): ("ListExpenseItemOptions", "Setup"),
        ("/setup/expense-categories", "post"): ("CreateExpenseCategory", "Setup"),
        ("/setup/expense-categories/{id}", "put"): ("UpdateExpenseCategory", "Setup"),
        ("/setup/expense-categories/{id}/stop", "post"): ("StopExpenseCategory", "Setup"),
        ("/setup/expense-categories/{id}/restore", "post"): ("RestoreExpenseCategory", "Setup"),
        ("/setup/expense-categories/{id}/items", "post"): ("CreateExpenseItem", "Setup"),
        ("/setup/expense-items/{id}", "put"): ("RenameExpenseItem", "Setup"),
        ("/setup/expense-items/{id}/stop", "post"): ("StopExpenseItem", "Setup"),
        ("/setup/expense-items/{id}/restore", "post"): ("RestoreExpenseItem", "Setup"),
        ("/setup/expense-main-categories", "get"): ("ListExpenseMainCategories", "Setup"),
        ("/setup/expense-main-categories", "post"): ("CreateExpenseMainCategory", "Setup"),
        ("/setup/expense-main-categories/{id}", "put"): ("RenameExpenseMainCategory", "Setup"),
        ("/setup/vehicles/{id}/investment", "get"): ("GetVehicleInvestment", "Setup"),
        ("/setup/vehicles/{id}/investment", "post"): ("AddVehicleInvestment", "Setup"),
        ("/setup/investment/{id}", "put"): ("UpdateVehicleInvestment", "Setup"),
        ("/setup/investment/{id}", "delete"): ("DeleteVehicleInvestment", "Setup"),
        ("/setup/organization/settings", "get"): ("GetOrganizationSettings", "Organization"),
        ("/setup/organization/settings/{section}", "put"): (
            "UpdateOrganizationSettings",
            "Organization",
        ),
        ("/setup/organization/logo", "put"): ("UpdateOrganizationLogo", "Organization"),
        ("/setup/organization/logo", "delete"): ("DeleteOrganizationLogo", "Organization"),
        ("/setup/appearance", "get"): ("GetAppearance", "Organization"),
        ("/setup/preferences", "get"): ("GetUserPreferences", "Organization"),
        ("/setup/preferences", "put"): ("UpdateUserPreferences", "Organization"),
    }
    for (path, method), (operation_id, tag) in expected.items():
        operation = document["paths"][path][method]
        assert operation["operationId"] == operation_id, path
        assert operation["tags"] == [tag], path
        assert operation["security"] == [{"Bearer": []}], path
        assert "401" in operation["responses"], path


# --- the whole catalogue (``tests/support/operations.json``, from docs/06 section 2) --------

DOCS = Path(__file__).resolve().parents[2] / "docs" / "06-http-contract.md"
OPERATIONS: list[dict[str, Any]] = json.loads(
    (Path(__file__).resolve().parents[1] / "support" / "operations.json").read_text("utf-8")
)
DOTNET_TAGS = {"Setup", "Organization", "Revenue", "Petty cash", "Central expenses", "Reports"}
_ROUTE = re.compile(r"^(GET|POST|PUT|DELETE|PATCH) (/\S+)")


def _contract_table() -> set[tuple[str, str, str]]:
    """The (method, path, operationId) rows of every section 2 table with both columns."""
    rows: set[tuple[str, str, str]] = set()
    header: list[str] | None = None
    in_catalogue = False
    for line in DOCS.read_text("utf-8").replace("\r", "").split("\n"):
        if line.startswith("## "):
            in_catalogue = line.startswith("## 2.")
            header = None
            continue
        if not in_catalogue or not line.startswith("|"):
            header = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if set("".join(cells)) <= set("-: ") or "operationId" not in header:
            continue
        route = _ROUTE.match(cells[header.index("Route")].strip("`"))
        if route is None:
            continue
        path = route.group(2).split("?")[0].rstrip("`")
        operation_id = cells[header.index("operationId")].strip("`")
        rows.add((route.group(1).lower(), path, operation_id))
    return rows


def _operations(document: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (method, path): operation
        for path, item in document["paths"].items()
        for method, operation in item.items()
    }


def test_the_fixture_is_the_contract_table() -> None:
    fixture = {(row["method"], row["path"], row["operationId"]) for row in OPERATIONS}
    assert fixture == _contract_table()


async def test_every_catalogued_operation_has_its_id_tag_bearer_and_401(
    client: httpx.AsyncClient,
) -> None:
    operations = _operations(await _document(client))
    for row in OPERATIONS:
        operation = operations.get((row["method"], row["path"]))
        if row["planned"]:
            assert operation is None, f"{row['id']} is served now: set planned to false"
            continue
        assert operation is not None, row["id"]
        assert operation["operationId"] == row["operationId"], row["id"]
        assert operation["tags"] == [row["tag"]], row["id"]
        assert operation["security"] == [{"Bearer": []}], row["id"]
        assert "401" in operation["responses"], row["id"]


async def test_every_served_operation_is_catalogued_or_an_untagged_auth_route(
    client: httpx.AsyncClient,
) -> None:
    catalogued = {(row["method"], row["path"]) for row in OPERATIONS}
    for (method, path), operation in _operations(await _document(client)).items():
        if (method, path) in catalogued:
            continue
        assert path.startswith("/auth/"), (method, path)
        assert "operationId" not in operation, (method, path)
        assert not operation.get("tags"), (method, path)


async def test_every_secured_operation_documents_401_and_every_tag_is_a_dotnet_tag(
    client: httpx.AsyncClient,
) -> None:
    operations = _operations(await _document(client))
    tags = {tag for operation in operations.values() for tag in operation.get("tags", [])}
    assert {"Setup", "Organization", "Revenue", "Petty cash"} <= tags <= DOTNET_TAGS
    for key, operation in operations.items():
        if operation.get("security"):
            assert operation["security"] == [{"Bearer": []}], key
            assert "401" in operation["responses"], key


async def test_no_operation_documents_the_framework_422(client: httpx.AsyncClient) -> None:
    document = await _document(client)
    for key, operation in _operations(document).items():
        assert "422" not in operation["responses"], key
    assert "HTTPValidationError" not in document["components"]["schemas"]
    assert "ValidationError" not in document["components"]["schemas"]
    assert "ProblemDetails" in document["components"]["schemas"]


async def test_the_document_is_absent_when_disabled(
    make_settings: Callable[..., Settings],
    ops: FakeOpsRepository,
    make_container: Callable[[Settings, FakeOpsRepository], Container],
) -> None:
    settings = make_settings(openapi_enabled=False)
    app = create_app(settings, make_container(settings, ops))
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        response = await c.get("/openapi/v1.json")
    assert response.status_code == 404
    production = Settings.for_tests(
        env="production",
        openapi_enabled=None,
        database_url="postgresql://xcode_app@db.example.com/xcode?sslmode=verify-full",
        mail_backend="smtp",
        email_host="smtp.example.com",
        email_from="noreply@example.com",
        log_format="json",
        allowed_hosts=["api.example.com"],
    )
    assert production.openapi_is_enabled is False


def test_the_cli_document_passes_the_same_assertions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in {
        "XCODE_ENV": "production",
        "XCODE_DATABASE_URL": "postgresql://xcode_app@db.example.com/xcode?sslmode=verify-full",
        "XCODE_AUTH_SIGNING_KEY": "k" * 32,
        "XCODE_EMAIL_HOST": "smtp.example.com",
        "XCODE_EMAIL_FROM": "noreply@example.com",
        "XCODE_ALLOWED_HOSTS": "api.example.com",
    }.items():
        monkeypatch.setenv(name, value)
    assert main(["openapi"]) == 0
    document = json.loads(capsys.readouterr().out)
    operations = _operations(document)
    sign_in = operations[("post", "/auth/sign-in")]
    for status in ("202", "423"):
        schema = sign_in["responses"][status]["content"]["application/json"]["schema"]
        assert schema == {"$ref": AUTH_RESPONSE}
    assert "security" not in sign_in
    deactivate = operations[("post", "/setup/people/{id}/deactivate")]
    conflict = deactivate["responses"]["409"]["content"]["application/problem+json"]
    assert conflict["schema"] == {"$ref": "#/components/schemas/ProblemDetails"}
    assert deactivate["security"] == [{"Bearer": []}]
    for row in OPERATIONS:
        if not row["planned"]:
            assert operations[(row["method"], row["path"])]["operationId"] == row["operationId"]
