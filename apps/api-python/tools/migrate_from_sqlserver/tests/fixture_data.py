"""The fixture extract: one small organization in the format ``extract`` writes.

``build`` makes the files of ``tests/fixtures/extract`` from the constants below, and
``test_fixture.py`` checks the committed files equal a fresh build, so they never drift.
Rebuild them with ``python -m tests.fixture_data`` from the tool's directory.

The data covers every enumeration value the map converts and the conversions of the design
notes v2.29 to v2.33, and holds one deliberately invalid row: an away period that returns
before it leaves (``ck_vehicle_away_periods_returned_on``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from migrate_from_sqlserver.formats import csv_bytes, sha256
from migrate_from_sqlserver.tablemap import NOT_MIGRATED, TABLES

EXTRACT_DIR = Path(__file__).parent / "fixtures" / "extract"
EXTRACTED_AT = datetime(2026, 10, 12, 18, 0, 0, 123456, tzinfo=UTC)
PIN = "2580"
SIGNING_KEY = "fixture-signing-key-not-a-secret-0123456789"
OWNER_TOKEN = "fixture-refresh-token-of-the-owner-phone"
OWNER_PHONE = "+254711000001"
OWNER_DEVICE = "phone-owner"
INVALID_AWAY_KEY = "OrganizationId={org}|Id={id}"
_NAMESPACE = uuid.UUID("6f1d2c3b-0a9e-4d8c-b7a6-5e4f3d2c1b0a")


def guid(name: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, name)).upper()


def pin_hash(salt_name: str, pin: str = PIN) -> str:
    salt = hashlib.sha256(salt_name.encode()).digest()[:16]
    key = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 210_000, 32)
    return f"{base64.b64encode(salt).decode()}.{base64.b64encode(key).decode()}"


def digest(token: str) -> str:
    return hmac.new(SIGNING_KEY.encode(), token.encode(), hashlib.sha256).hexdigest().upper()


def at(moment: datetime, ticks: int = 0) -> str:
    """A SQL Server instant as extract writes it (UTC, seven fractional digits)."""
    base = moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
    return f"{base}.{moment.microsecond * 10 + ticks:07d}"


def bit(value: bool) -> str:
    return "1" if value else "0"


ORG = guid("org")
OWNER, CLERK, MANAGER, ADMIN, LEAVER = (
    guid(f"user:{n}") for n in ("owner", "clerk", "manager", "admin", "leaver")
)
ROLE = {
    name: guid(f"role:{name}")
    for name in ("Owner", "Office admin", "Fleet manager", "Revenue clerk")
}
COAST, ENA = guid("company:coast"), guid("company:ena")
V1, V2, V3 = guid("vehicle:1"), guid("vehicle:2"), guid("vehicle:3")
REPAIRS, INSURANCE, LOANS = guid("cat:repairs"), guid("cat:insurance"), guid("cat:loans")
TYRES, COVER, BANK = guid("item:tyres"), guid("item:cover"), guid("item:bank")
INVALID_AWAY = guid("away:invalid")
NOW = EXTRACTED_AT


def _rows() -> dict[str, list[dict[str, str | None]]]:
    days = [datetime(2026, 9, 28, tzinfo=UTC) + timedelta(days=i) for i in range(10)]
    revenue: list[dict[str, str | None]] = []
    for i, day in enumerate(days):
        revenue.append(_revenue(f"rev:v1:{i}", V1, day, amount=f"{4500 + 100 * i}.00"))
    for reason, day in zip((1, 2, 3), days[:3], strict=True):
        revenue.append(_revenue(f"rev:v2:{reason}", V2, day, reason=str(reason)))
    revenue.append(_revenue("rev:v3:other", V3, days[0], reason="4", note="Driver at a funeral"))

    return {
        "Users": [
            _user(
                OWNER,
                "Owner@Example.com",
                OWNER_PHONE,
                pin_hash("owner"),
                status="0",
                security_version="3",
            ),
            _user(
                CLERK,
                "clerk@example.com",
                "0711000002",
                pin_hash("clerk"),
                failed="2",
                paused=at(NOW + timedelta(minutes=10)),
            ),
            _user(
                MANAGER,
                "manager@example.com",
                "+254711000003",
                pin_hash("manager"),
                failed="5",
                untrusted="12",
                paused=at(NOW - timedelta(days=1)),
            ),
            _user(ADMIN, "admin@example.com", "+254711000004", None),
            _user(LEAVER, "leaver@example.com", "+254711000005", pin_hash("leaver"), status="1"),
        ],
        "Organizations": [
            {
                "Id": ORG,
                "Slug": "mombasa-line",
                "Name": "Mombasa Line",
                "BusinessDate": None,
                "SettingsVersion": "6",
            },
        ],
        "Memberships": [
            _member(OWNER, "Amina", "Owner"),
            _member(CLERK, "Baraka", "Clerk", limit="5000.00"),
            _member(MANAGER, "Chebet", "Manager"),
            _member(ADMIN, "Dalmas", "Admin"),
            _member(LEAVER, "Esther", "Leaver", active=False),
        ],
        "Localizations": [
            {
                "OrganizationId": ORG,
                "Locale": "en-GB",
                "TimeZone": "E. Africa Standard Time",
                "DatePattern": "medium",
                "Hour12": "0",
                "FirstDayOfWeek": "1",
                "WeekNumbering": "iso8601",
                "Currency": "KES",
                "UseGrouping": "1",
                "NumberDecimals": "2",
                "AllowLocaleOverride": "1",
                "AllowTimeZoneOverride": "0",
                "AllowHour12Override": "1",
                "AllowThemeOverride": "1",
            },
        ],
        "Brandings": [
            {
                "OrganizationId": ORG,
                "DisplayName": "Mombasa Line",
                "LegalName": "Mombasa Line Ltd",
                "LogoAlt": "Mombasa Line",
                "Primary": "#1D5FD6",
                "Secondary": "#14213D",
                "Accent": "#1E6B3A",
                "LogoLight": "",
                "LogoDark": None,
                "Favicon": None,
                "TermsUrl": "https://example.com/terms",
                "PrivacyUrl": None,
                "Domain": None,
                "SupportEmail": "help@example.com",
            },
        ],
        "Logos": [
            {
                "OrganizationId": ORG,
                "ContentType": "image/png",
                "Data": "89504E470D0A1A0A0000000D49484452",
                "UpdatedAt": at(NOW - timedelta(days=30)),
            },
        ],
        "SecurityPolicies": [
            {
                "OrganizationId": ORG,
                "PasswordMinLength": "12",
                "PasswordComplexity": "1",
                "PasswordHistory": "5",
                "PinLength": "4",
                "LockoutThreshold": "5",
                "LockoutMinutes": "15",
                "AccessTokenMinutes": "20",
                "RefreshTokenDays": "30",
                "IdleUnlockSeconds": "300",
                "AllowPinSignIn": "1",
            },
        ],
        "Roles": [{"OrganizationId": ORG, "Id": i, "Name": n} for n, i in ROLE.items()],
        "PersonRoles": [
            _person_role(OWNER, "Owner"),
            _person_role(CLERK, "Revenue clerk"),
            _person_role(MANAGER, "Fleet manager"),
            _person_role(ADMIN, "Office admin"),
            _person_role(LEAVER, "Revenue clerk"),
        ],
        "PermissionOverrides": [
            _override(MANAGER, "pettycash.approve_item", True),
            _override(MANAGER, "legacy.unknown_key", True),
            _override(CLERK, "revenue.no_earnings", False),
            _override(ADMIN, "bills.approve", True),
            _override(guid("user:stranger"), "revenue.view", True),
        ],
        "UserPreferences": [
            {
                "OrganizationId": ORG,
                "UserId": OWNER,
                "Locale": None,
                "TimeZone": None,
                "Hour12": None,
                "ThemeMode": "dark",
                "ReducedMotion": "0",
                "FontScale": "1.2500000000000000E+000",
            },
            {
                "OrganizationId": ORG,
                "UserId": CLERK,
                "Locale": "en-KE",
                "TimeZone": "Africa/Nairobi",
                "Hour12": "1",
                "ThemeMode": "system",
                "ReducedMotion": "1",
                "FontScale": "1.0000000000000000E+000",
            },
        ],
        "PsvCompany": [
            {
                "OrganizationId": ORG,
                "Id": COAST,
                "Name": "Coast Express",
                "NormalizedName": "COAST EXPRESS",
                "ArchivedOn": None,
            },
            {
                "OrganizationId": ORG,
                "Id": ENA,
                "Name": "Ena Coach",
                "NormalizedName": "ENA COACH",
                "ArchivedOn": "2026-09-01",
            },
        ],
        "FleetVehicle": [
            _vehicle(V1, COAST, "KBX 123A", "2026-01-05", None),
            _vehicle(V2, COAST, "KCA 456B", "2026-01-05", None),
            _vehicle(V3, ENA, "KDD 789C", "2026-02-01", "2026-08-31"),
        ],
        "ExpenseCategory": [
            _category(REPAIRS, "Repairs", "1"),
            _category(INSURANCE, "Insurance", "2"),
            _category(LOANS, "Loans", "3"),
        ],
        "ExpenseItem": [
            _item(TYRES, REPAIRS, "Tyres"),
            _item(COVER, INSURANCE, "Comprehensive cover"),
            _item(BANK, LOANS, "Bank loan"),
        ],
        "VehicleTarget": [
            _target("t:v1:1", V1, "1", "2026-01-05", "7000.00"),
            _target("t:v1:2", V1, "2", "2026-01-05", "7700.00"),
            _target("t:v1:3", V1, "3", "2026-06-01", "10000.00"),
            _target("t:v2:1", V2, "1", "2026-01-05", "0.05"),
            _target("t:v3:1", V3, "1", "2026-02-01", "5000.00"),
        ],
        "VehicleAwayPeriod": [
            {
                "OrganizationId": ORG,
                "Id": guid("away:valid"),
                "VehicleId": V1,
                "LeftOn": "2026-03-01",
                "ReturnedOn": "2026-03-05",
            },
            {
                "OrganizationId": ORG,
                "Id": INVALID_AWAY,
                "VehicleId": V2,
                "LeftOn": "2026-04-10",
                "ReturnedOn": "2026-04-08",
            },
        ],
        "VehicleInvestment": [
            {
                "OrganizationId": ORG,
                "Id": guid("invest:1"),
                "VehicleId": V1,
                "Date": "2026-01-05",
                "Description": "Purchase",
                "Amount": "2500000.00",
                "RecordedBy": OWNER,
                "RecordedAt": at(datetime(2026, 1, 5, 9, tzinfo=UTC), 7),
            },
        ],
        "SetupDataScopes": [
            {"OrganizationId": ORG, "UserId": CLERK, "AllCompanies": "0"},
            {"OrganizationId": ORG, "UserId": MANAGER, "AllCompanies": "1"},
        ],
        "SetupCompanyScopes": [{"OrganizationId": ORG, "UserId": CLERK, "CompanyId": COAST}],
        "SetupVehicleScopes": [{"OrganizationId": ORG, "UserId": CLERK, "VehicleId": V1}],
        "RecurringItem": [
            {"OrganizationId": ORG, "Id": guid(f"recurring:{n}"), "StoppedFrom": None}
            for n in ("loan", "saving", "fuel", "insurance")
        ],
        "RecurringVersion": [
            _version("loan", "1", "30000.00", "3", day="5", item=BANK, bucket="3"),
            _version("saving", "2", "2000.00", "2", day="1"),
            _version("fuel", "1", "500.00", "1", item=TYRES, bucket="1"),
            _version("insurance", "1", "60000.00", "4", day="1", month="1", item=COVER, bucket="2"),
        ],
        "RecurringAllocation": [
            _allocation("loan", V1, "15000.00"),
            _allocation("loan", V2, "15000.00"),
            _allocation("saving", V1, "2000.00"),
            _allocation("fuel", V1, "250.00"),
            _allocation("fuel", V2, "250.00"),
            _allocation("insurance", V1, "60000.00"),
        ],
        "RevenueRecords": revenue,
        "PettyCashEntries": [
            _petty("pc:cash", 1, None, "5000.00", status=None),
            _petty("pc:waiting", 2, TYRES, "1200.00", status="1", vehicle=V1),
            _petty(
                "pc:approved",
                2,
                TYRES,
                "33.33",
                status="2",
                vehicle=V1,
                units="3.000",
                total="99.99",
                reviewed=True,
            ),
            _petty(
                "pc:sent-back",
                2,
                TYRES,
                "800.00",
                status="3",
                vehicle=V2,
                reviewed=True,
                sent_back="Attach the receipt",
            ),
            _petty("pc:credit", 3, None, "-150.00", status="2", reviewed=True, payee="Shell"),
        ],
        "CentralExpenses": [],
        "RecurringPause": [],
        "OrganizationSettingsVersion": [
            _change(1, "companies", COAST, None),
            _change(2, "vehicles", V1, V1),
            _change(3, "revenue", guid("rev:v1:0"), V1),
            _change(4, "people", CLERK, None),
        ],
        "AuditEvents": [
            _audit(
                "audit:1",
                "people.update",
                '{"role":"Revenue clerk"}',
                '{"role":"Fleet manager"}',
                1,
            ),
            _audit("audit:2", "settings.update", None, '{"a":1,"a":2}', 2),
            _audit("audit:3", "vehicle.create", None, '{"registration":"KBX 123A"}', 3),
        ],
        "TrustedDevices": [
            _device("dev:owner", OWNER, OWNER_DEVICE),
            _device("dev:owner-tablet", OWNER, "tablet-owner", revoked=True),
            _device("dev:clerk", CLERK, "phone-clerk"),
            _device("dev:manager-old", MANAGER, "phone-old"),
        ],
        "RefreshTokens": [
            _token("tok:owner-live", OWNER, OWNER_DEVICE, OWNER_TOKEN, NOW + timedelta(days=20)),
            _token(
                "tok:owner-old",
                OWNER,
                OWNER_DEVICE,
                "owner-old",
                NOW - timedelta(days=5),
                revoked=True,
            ),
            _token("tok:clerk-expired", CLERK, "phone-clerk", "clerk-old", NOW - timedelta(days=1)),
            _token("tok:clerk-live", CLERK, "phone-clerk", "clerk-live", NOW + timedelta(days=29)),
        ],
    }


def _user(
    id_: str,
    email: str,
    phone: str,
    pin: str | None,
    status: str = "0",
    failed: str = "0",
    untrusted: str = "0",
    paused: str | None = None,
    security_version: str = "1",
) -> dict[str, str | None]:
    return {
        "Id": id_,
        "Email": email,
        "PhoneNumber": phone,
        "PinHash": pin,
        "Status": status,
        "SecurityVersion": security_version,
        "FailedAttempts": failed,
        "PausedUntil": paused,
        "UntrustedFailedAttempts": untrusted,
        "Version": "4",
    }


def _member(
    user: str, first: str, last: str, limit: str | None = None, active: bool = True
) -> dict[str, str | None]:
    return {
        "OrganizationId": ORG,
        "UserId": user,
        "FirstName": first,
        "LastName": last,
        "Active": bit(active),
        "ApprovalLimit": limit,
        "Version": "2",
    }


def _person_role(user: str, role: str) -> dict[str, str | None]:
    return {"OrganizationId": ORG, "UserId": user, "RoleId": ROLE[role]}


def _override(user: str, key: str, granted: bool) -> dict[str, str | None]:
    return {"OrganizationId": ORG, "UserId": user, "Permission": key, "Granted": bit(granted)}


def _vehicle(
    id_: str, company: str, registration: str, joined: str, left: str | None
) -> dict[str, str | None]:
    return {
        "OrganizationId": ORG,
        "Id": id_,
        "CompanyId": company,
        "Registration": registration,
        "JoinedOn": joined,
        "LeftOn": left,
    }


def _category(id_: str, name: str, bucket: str) -> dict[str, str | None]:
    return {
        "OrganizationId": ORG,
        "Id": id_,
        "Name": name,
        "NormalizedName": name.upper(),
        "Bucket": bucket,
        "StoppedOn": None,
    }


def _item(id_: str, category: str, name: str) -> dict[str, str | None]:
    return {
        "OrganizationId": ORG,
        "Id": id_,
        "CategoryId": category,
        "Name": name,
        "NormalizedName": name.upper(),
        "StoppedOn": None,
    }


def _target(
    name: str, vehicle: str, revision: str, start: str, weekly: str
) -> dict[str, str | None]:
    return {
        "OrganizationId": ORG,
        "Id": guid(name),
        "VehicleId": vehicle,
        "EffectiveFrom": start,
        "Revision": revision,
        "WeeklyAmount": weekly,
    }


def _version(
    name: str,
    kind: str,
    amount: str,
    frequency: str,
    day: str | None = None,
    month: str | None = None,
    item: str | None = None,
    bucket: str | None = None,
) -> dict[str, str | None]:
    return {
        "OrganizationId": ORG,
        "Id": guid(f"version:{name}"),
        "ItemId": guid(f"recurring:{name}"),
        "Revision": "1",
        "EffectiveFrom": "2026-01-01",
        "Name": name.capitalize(),
        "Kind": kind,
        "Amount": amount,
        "Frequency": frequency,
        "Day": day,
        "LastDay": "0",
        "Month": month,
        "Start": "2026-01-01",
        "End": None,
        "ExpenseItemId": item,
        "Bucket": bucket,
        "Note": None,
    }


def _allocation(name: str, vehicle: str, amount: str) -> dict[str, str | None]:
    return {
        "OrganizationId": ORG,
        "Id": guid(f"allocation:{name}:{vehicle}"),
        "VersionId": guid(f"version:{name}"),
        "VehicleId": vehicle,
        "Amount": amount,
    }


def _revenue(
    name: str,
    vehicle: str,
    day: datetime,
    amount: str | None = None,
    reason: str | None = None,
    note: str | None = None,
) -> dict[str, str | None]:
    captured = day + timedelta(hours=19)
    return {
        "OrganizationId": ORG,
        "Id": guid(name),
        "VehicleId": vehicle,
        "BusinessDate": day.date().isoformat(),
        "Amount": amount,
        "Reason": reason,
        "Note": note,
        "CapturedAt": at(captured, 5),
        "CapturedBy": CLERK,
        "UpdatedAt": at(captured, 5),
        "UpdatedBy": CLERK,
        "CorrectedAfterDate": "0",
        "Version": "1",
    }


def _petty(
    name: str,
    kind: int,
    item: str | None,
    amount: str,
    status: str | None,
    vehicle: str | None = None,
    units: str = "1.000",
    total: str | None = None,
    reviewed: bool = False,
    sent_back: str | None = None,
    payee: str | None = None,
) -> dict[str, str | None]:
    when = at(datetime(2026, 10, 1, 10, tzinfo=UTC))
    return {
        "OrganizationId": ORG,
        "Id": guid(name),
        "HolderId": MANAGER,
        "Kind": str(kind),
        "Date": "2026-10-01",
        "VehicleId": vehicle,
        "ExpenseItemId": item,
        "Units": units,
        "UnitAmount": amount,
        "Total": total or amount,
        "Payee": payee,
        "Note": None,
        "Reimbursable": "0",
        "Status": status,
        "SentBackNote": sent_back,
        "ReviewedBy": OWNER if reviewed else None,
        "ReviewedAt": at(datetime(2026, 10, 2, 8, tzinfo=UTC)) if reviewed else None,
        "RecordedBy": MANAGER,
        "RecordedAt": when,
        "UpdatedBy": MANAGER,
        "UpdatedAt": when,
        "RemovedBy": None,
        "RemovedAt": None,
        "RemovalReason": None,
        "Version": "1",
    }


def _change(version: int, section: str, entity: str, vehicle: str | None) -> dict[str, str | None]:
    when = datetime(2026, 9, 1, 8, tzinfo=UTC) + timedelta(hours=version)
    return {
        "OrganizationId": ORG,
        "Id": guid(f"change:{version}"),
        "Version": str(version),
        "Section": section,
        "EntityId": entity,
        "VehicleId": vehicle,
        "ActorId": OWNER,
        "Reason": f"Change {version}",
        "OccurredAt": at(when, 3),
        "EffectiveFrom": None,
        "Before": '{"Name":"Before"}',
        "After": '{"Name":"After"}',
        "CorrelationId": f"req-{version}",
    }


def _audit(
    name: str, action: str, before: str | None, after: str, hours: int
) -> dict[str, str | None]:
    when = datetime(2026, 9, 2, tzinfo=UTC) + timedelta(hours=hours)
    return {
        "OrganizationId": ORG,
        "Id": guid(name),
        "ActorId": OWNER,
        "Action": action,
        "Entity": "Person",
        "Before": before,
        "After": after,
        "OccuredAt": at(when),
        "CorrelationId": f"req-{name}",
    }


def _device(name: str, user: str, device: str, revoked: bool = False) -> dict[str, str | None]:
    return {
        "Id": guid(name),
        "UserId": user,
        "DeviceId": device,
        "Revoked": bit(revoked),
        "TrustExpiresAt": None,
    }


def _token(
    name: str, user: str, device: str, token: str, expires: datetime, revoked: bool = False
) -> dict[str, str | None]:
    return {
        "Id": guid(name),
        "UserId": user,
        "DeviceId": device,
        "TokenHash": digest(token),
        "ExpiresAt": at(expires),
        "Revoked": bit(revoked),
        "Version": "1",
    }


NOT_COPIED_ROWS: Mapping[str, int] = {
    "VerificationCodes": 2,
    "RolePermissions": 0,
    "RecurringKindLookup": 2,
    "RecurrenceFrequencyLookup": 4,
    "ExpenseBucketLookup": 3,
    "__EFMigrationsHistory": 31,
}


def build(
    directory: Path = EXTRACT_DIR, rows: Mapping[str, list[dict[str, str | None]]] | None = None
) -> dict[str, object]:
    """Write the extract files and ``manifest.json``; ``rows`` replaces the data (tests)."""
    data = dict(_rows() if rows is None else rows)
    directory.mkdir(parents=True, exist_ok=True)
    tables: dict[str, object] = {}
    for table in TABLES:
        if table.source is None:
            continue
        names = [str(c.source) for c in table.source_columns]
        body = [tuple(row[n] for n in names) for row in data[table.source]]
        positions = [names.index(k) for k in table.key]
        body.sort(key=lambda r: tuple(r[i] or "" for i in positions))
        payload = csv_bytes(names, body)
        file = f"{table.source}.csv"
        (directory / file).write_bytes(payload)
        tables[table.source] = {"file": file, "rows": len(body), "sha256": sha256(payload)}
    for name, _ in NOT_MIGRATED:
        tables[name] = {"rows": NOT_COPIED_ROWS[name], "copied": False}
    manifest = {
        "format": 1,
        "tool": "fixture",
        "extracted_at": EXTRACTED_AT.isoformat(),
        "source": {
            "database": "XCodeFixture",
            "server_version": "16.0.1000.6",
            "server": "fixture",
            "snapshot": "SNAPSHOT isolation",
            "latest_migration": "20261010194310_RecurringPauses",
        },
        "tables": tables,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def rows() -> dict[str, list[dict[str, str | None]]]:
    return _rows()


if __name__ == "__main__":
    build()
