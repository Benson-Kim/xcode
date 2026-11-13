"""One branded XCODE layout for every mail: each message carries an HTML part in the same frame
(the XCODE header and the automatic-message footer, the subject as its title), inline-styled
with no script, image, stylesheet or other remote resource, and a link only to an http(s)
address. The text parts are tested with each message."""

from __future__ import annotations

import html
from datetime import UTC, datetime
from uuid import UUID

import pytest

from xcode_api.application.ports import (
    DeletionNotice,
    InvitationMail,
    MailMessage,
    SignInNotice,
    VerificationMail,
)
from xcode_api.domain.identity import CodePurpose
from xcode_api.domain.tenancy import SignInNoticeKind
from xcode_api.infra.mail import (
    InvitationLinks,
    deletion_request_message,
    invitation_message,
    sign_in_change_message,
    verification_message,
)

LINKS = InvitationLinks(
    web_url="https://app.example.com",
    app_store_url="https://apps.apple.com/app/id1",
    play_store_url="https://play.google.com/store/apps/details?id=ke.co.priori.xcode",
)


def _verification(device_name: str | None = "Pixel 8") -> MailMessage:
    return verification_message(
        VerificationMail(
            to="jane@example.com",
            purpose=CodePurpose.FIRST_SETUP,
            code="048213",
            code_id=UUID("0b6a9f4e-2c1d-4e8b-9a7f-5d3c2b1a0e9f"),
            request_id="req-1",
            device_name=device_name,
        )
    )


def _invitation(
    links: InvitationLinks = LINKS, first_name: str = "Jane", organization_name: str = "Metro"
) -> MailMessage:
    return invitation_message(
        InvitationMail(
            to="jane@example.com",
            token="t0ken",
            code="314159",
            invitation_id=UUID("6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"),
            first_name=first_name,
            organization_name=organization_name,
            expires_at=datetime(2026, 11, 17, 11, 5, tzinfo=UTC),
            time_zone="Africa/Nairobi",
            inviter_name="Amos Kariuki",
            support_email="help@example.com",
            request_id="req-1",
        ),
        links,
    )


def _deletion(requester_name: str = "Jane Doe") -> MailMessage:
    return deletion_request_message(
        DeletionNotice(
            to="admin@example.com",
            recipient_first_name="Ann",
            requester_name=requester_name,
            organization_name="Metro",
            request_id="req-1",
        )
    )


def _sign_in(first_name: str = "Jane") -> MailMessage:
    return sign_in_change_message(
        SignInNotice(
            to="jane@example.com",
            kind=SignInNoticeKind.NEW,
            first_name=first_name,
            actor_name="Olive Owner",
            organization_name="Metro",
        )
    )


MESSAGES = {
    "verification": _verification,
    "invitation": _invitation,
    "deletion": _deletion,
    "sign_in": _sign_in,
}


@pytest.mark.parametrize("name", list(MESSAGES))
def test_every_mail_has_an_html_part_in_the_xcode_frame(name: str) -> None:
    message = MESSAGES[name]()
    assert message.html is not None
    page = message.html
    assert page.startswith("<!doctype html>")
    assert f"<title>{html.escape(message.subject)}</title>" in page
    assert ">XCODE</span>" in page
    assert "This is an automatic message from XCODE." in page
    assert page.endswith("</body></html>")


@pytest.mark.parametrize("name", list(MESSAGES))
def test_no_mail_loads_a_script_an_image_or_any_remote_resource(name: str) -> None:
    page = MESSAGES[name]().html or ""
    lowered = page.lower()
    for banned in ("<script", "<img", "<link", "<style", "<iframe", "src=", "url(", "@import"):
        assert banned not in lowered, banned
    assert all(
        href.startswith(("https://", "http://"))
        for href in (part.split('"', 1)[0] for part in page.split('href="')[1:])
    )


@pytest.mark.parametrize("name", list(MESSAGES))
def test_the_text_part_carries_no_markup(name: str) -> None:
    message = MESSAGES[name]()
    assert "<" not in message.text and "&lt;" not in message.text and "&amp;" not in message.text


def test_the_verification_facts_are_a_table_in_the_html_and_lines_in_the_text() -> None:
    message = _verification()
    assert message.text == "Code: 048213\nFor: First sign in\nDevice: Pixel 8"
    assert message.html is not None
    assert ">048213</td>" in message.html
    assert ">Pixel 8</td>" in message.html


@pytest.mark.parametrize(
    "message",
    [
        lambda v: _verification(device_name=v),
        lambda v: _invitation(first_name=v),
        lambda v: _invitation(organization_name=v),
        lambda v: _deletion(requester_name=v),
        lambda v: _sign_in(first_name=v),
    ],
)
def test_a_typed_value_is_escaped_in_the_html_part(message: object) -> None:
    hostile = '"><img src=x onerror=alert(1)><script>alert(1)</script>'
    page = message(hostile).html  # type: ignore[operator]
    assert "<script" not in page and "<img" not in page
    assert html.escape(hostile, quote=True) in page


def test_a_link_that_is_not_http_is_shown_as_text_never_as_a_link() -> None:
    message = _invitation(
        InvitationLinks(web_url="javascript:alert(1)", play_store_url="data:text/html,x")
    )
    assert message.html is not None
    assert "href=" not in message.html
    assert "javascript:alert(1)/invite#t0ken" in message.text
