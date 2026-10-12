"""``UpdateOrganizationLogo``: the data URL is decoded before the repository is told anything
(its length first, then its shape, then the base64), and the answer is the data URL rebuilt
from the bytes the repository stored."""

from __future__ import annotations

import base64

import pytest

from xcode_api.application.caller import Caller
from xcode_api.application.organization.update_organization_logo import (
    UpdateOrganizationLogo,
    UpdateOrganizationLogoCommand,
)
from xcode_api.domain.errors import RuleViolation
from xcode_api.domain.identity import Principal
from xcode_api.domain.tenancy import LOGO_MAX_DATA_URL, LogoUpload

from ..support.clock import ManualClock
from ..support.fakes import FakeTenancyRepository

PNG_BYTES = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 8
PNG_URL = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()


@pytest.mark.parametrize(
    ("data_url", "code"),
    [
        ("data:image/png;base64," + "A" * LOGO_MAX_DATA_URL, "logo_too_large"),
        ("data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=", "logo_type"),
        ("data:image/gif;base64,R0lGODlh", "logo_type"),
        ("data:image/png;base64,!!!!", "logo_type"),
        ("data:image/png;base64,abc", "logo_unreadable"),
        ("image/png;base64,iVBORw0KGgo=", "logo_type"),
    ],
    ids=["oversized", "svg", "gif", "not-base64", "bad-padding", "no-scheme"],
)
def test_a_data_url_that_does_not_decode_is_refused_by_its_code(data_url: str, code: str) -> None:
    with pytest.raises(RuleViolation) as caught:
        LogoUpload.parse(data_url)
    assert caught.value.code == code


def test_the_length_is_checked_before_the_shape() -> None:
    with pytest.raises(RuleViolation) as caught:
        LogoUpload.parse("not a data url " * 40_000)
    assert caught.value.code == "logo_too_large"


def test_a_decoded_logo_keeps_its_type_and_bytes() -> None:
    logo = LogoUpload.parse(PNG_URL)
    assert (logo.content_type, logo.data) == ("image/png", PNG_BYTES)
    assert logo.data_url == PNG_URL


async def test_the_use_case_stores_the_decoded_bytes_and_answers_their_data_url() -> None:
    tenancy = FakeTenancyRepository()
    owner = tenancy.add_member()
    principal = Principal(owner, "phone-1", 0, tenancy.organization_id, "Owner", ())
    use_case = UpdateOrganizationLogo(tenancy, ManualClock())
    answer = await use_case.execute(
        UpdateOrganizationLogoCommand(Caller(principal, "req-1"), PNG_URL, None)
    )
    assert answer == PNG_URL
    assert tenancy.logo == LogoUpload("image/png", PNG_BYTES)
    assert tenancy.log[-1].reason == "Uploaded a new logo"


async def test_an_undecodable_logo_never_reaches_the_repository() -> None:
    tenancy = FakeTenancyRepository()
    owner = tenancy.add_member()
    principal = Principal(owner, "phone-1", 0, tenancy.organization_id, "Owner", ())
    use_case = UpdateOrganizationLogo(tenancy, ManualClock())
    with pytest.raises(RuleViolation):
        await use_case.execute(
            UpdateOrganizationLogoCommand(
                Caller(principal, "req-1"), "data:image/png;base64,abc", None
            )
        )
    assert tenancy.log == []
