"""The invitation mail: text and HTML parts, admin-typed values escaped and folded to one
line, the link host from settings only, and no token, code or address in any log event."""

from __future__ import annotations

import html
import secrets
from datetime import UTC, datetime
from email.message import EmailMessage
from uuid import UUID

import aiosmtplib
import pytest
from structlog.testing import capture_logs

from xcode_api.application.ports import InvitationMail, MailMessage
from xcode_api.infra.mail import (
    InvitationLinks,
    LogMailer,
    MailDeliveryError,
    MailQueue,
    QueuedInvitationMailer,
    SmtpMailer,
    invitation_message,
)

INVITATION_ID = UUID("6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b")
LINKS = InvitationLinks(web_url="https://app.example.com")
EXPIRES = datetime(2026, 11, 17, 11, 5, tzinfo=UTC)


def _mail(**overrides: object) -> InvitationMail:
    values: dict[str, object] = {
        "to": "jane.doe@example.com",
        "token": secrets.token_urlsafe(32),
        "code": f"{secrets.randbelow(10**6):06d}",
        "invitation_id": INVITATION_ID,
        "first_name": "Jane",
        "organization_name": "Rada Logistics",
        "expires_at": EXPIRES,
        "time_zone": "Africa/Nairobi",
        "inviter_name": "Amos Kariuki",
        "support_email": "help@rada.example",
        "request_id": "req-1",
    }
    values.update(overrides)
    return InvitationMail(**values)  # type: ignore[arg-type]


def test_text_and_html_carry_the_link_the_code_and_the_expiry() -> None:
    mail = _mail(code="123456")
    message = invitation_message(mail, LINKS)
    link = f"https://app.example.com/invite#{mail.token}"
    assert message.subject == "Rada Logistics invited you to XCODE"
    assert message.html is not None
    for part in (message.text, message.html):
        assert "Amos Kariuki added you to Rada Logistics." in part
        assert link in part
        assert "123 456" in part
        assert "Tuesday 17 November 2026, 14:05 EAT" in part
        assert "XCODE never asks for your PIN by email" in part
    assert "Set up my access" in message.html
    assert message.reply_to == "help@rada.example"


def test_no_phone_number_and_no_secret_in_the_tags() -> None:
    mail = _mail()
    message = invitation_message(mail, LINKS)
    assert message.tags == {
        "purpose": "invitation",
        "invitation_id": str(INVITATION_ID),
        "request_id": "req-1",
    }
    assert mail.token not in repr(message)
    assert mail.code not in repr(message)
    assert mail.to not in repr(message) and mail.to not in repr(mail)


@pytest.mark.parametrize(
    "hostile",
    [
        "<script>alert(1)</script>",
        '"><img src=x onerror=alert(1)>',
        "' onmouseover='alert(1)",
        "Tom & Jerry <b>",
    ],
)
def test_admin_typed_values_are_escaped_in_the_html(hostile: str) -> None:
    message = invitation_message(
        _mail(first_name=hostile, organization_name=hostile, inviter_name=hostile), LINKS
    )
    assert message.html is not None
    assert hostile not in message.html
    assert "<script" not in message.html
    assert "<img" not in message.html
    assert html.escape(hostile, quote=True) in message.html


@pytest.mark.parametrize("breaker", ["\r\n", "\n", "\r", "\u2028", "\x00", "\u202e"])
def test_line_breaks_and_controls_cannot_reach_a_header(breaker: str) -> None:
    hostile = f"Rada{breaker}Bcc: everyone@example.com"
    message = invitation_message(
        _mail(organization_name=hostile, support_email=f"help@rada.example{breaker}X: y"), LINKS
    )
    assert message.subject == "Rada Bcc: everyone@example.com invited you to XCODE"
    for header in (message.subject, message.reply_to or ""):
        assert not any(ch in header for ch in "\r\n\x00\u2028\u202e")


def test_the_link_host_comes_only_from_the_configured_origin() -> None:
    mail = _mail()
    message = invitation_message(mail, InvitationLinks(web_url="https://xcode.example.org"))
    assert f"https://xcode.example.org/invite#{mail.token}" in message.text
    assert "app.example.com" not in message.text


def test_store_links_appear_only_when_configured() -> None:
    plain = invitation_message(_mail(), LINKS)
    assert "App Store" not in plain.text and "Google Play" not in plain.text
    stores = InvitationLinks(
        web_url="https://app.example.com",
        app_store_url="https://apps.apple.com/app/id1",
        play_store_url="https://play.google.com/store/apps/details?id=ke.co.priori.xcode",
    )
    message = invitation_message(_mail(), stores)
    assert "App Store: https://apps.apple.com/app/id1" in message.text
    assert message.html is not None
    assert 'href="https://play.google.com/store/apps/details?id=ke.co.priori.xcode"' in message.html


def test_an_unknown_time_zone_falls_back_to_utc() -> None:
    message = invitation_message(_mail(time_zone="Not/AZone"), LINKS)
    assert "Tuesday 17 November 2026, 11:05 UTC" in message.text


def test_no_inviter_and_no_support_address() -> None:
    message = invitation_message(_mail(inviter_name=None, support_email=None, first_name=""), LINKS)
    assert message.text.startswith("Hello,\n")
    assert "Someone added you to Rada Logistics." in message.text
    assert message.reply_to is None


async def test_smtp_sends_text_and_html_alternatives_with_reply_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[EmailMessage] = []

    async def fake_send(email: EmailMessage, **_: object) -> None:
        sent.append(email)

    monkeypatch.setattr(aiosmtplib, "send", fake_send)
    mailer = SmtpMailer(host="smtp.example.com", port=587, sender="noreply@example.com")
    await mailer.send(invitation_message(_mail(), LINKS))
    (email,) = sent
    assert email.get_content_type() == "multipart/alternative"
    assert [part.get_content_type() for part in email.iter_parts()] == [
        "text/plain",
        "text/html",
    ]
    assert email["Reply-To"] == "help@rada.example"


async def test_smtp_without_html_stays_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[EmailMessage] = []

    async def fake_send(email: EmailMessage, **_: object) -> None:
        sent.append(email)

    monkeypatch.setattr(aiosmtplib, "send", fake_send)
    mailer = SmtpMailer(host="smtp.example.com", port=587, sender="noreply@example.com")
    await mailer.send(MailMessage(to="a@example.com", subject="s", text="t"))
    assert sent[0].get_content_type() == "text/plain"
    assert sent[0]["Reply-To"] is None


class _Mailer:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[MailMessage] = []

    async def send(self, message: MailMessage) -> None:
        if self.fail:
            raise MailDeliveryError("down")
        self.sent.append(message)


async def _deliver(mailer: object, mail: InvitationMail) -> list[str]:
    outcome: list[str] = []

    async def on_sent() -> None:
        outcome.append("sent")

    async def on_failure() -> None:
        outcome.append("failed")

    queue = MailQueue(mailer)  # type: ignore[arg-type]
    queue.start()
    QueuedInvitationMailer(queue, LINKS).send_later(mail, on_sent=on_sent, on_failure=on_failure)
    await queue.drain(1.0)
    return outcome


async def test_a_delivered_invitation_runs_on_sent() -> None:
    mailer = _Mailer()
    assert await _deliver(mailer, _mail()) == ["sent"]
    assert len(mailer.sent) == 1


async def test_a_failed_invitation_runs_on_failure() -> None:
    assert await _deliver(_Mailer(fail=True), _mail()) == ["failed"]


async def test_a_failing_success_callback_is_logged_and_swallowed() -> None:
    async def broken() -> None:
        raise RuntimeError("db down")

    async def unused() -> None:
        raise AssertionError("on_failure must not run after a send")

    queue = MailQueue(_Mailer())
    queue.start()
    with capture_logs() as logs:
        QueuedInvitationMailer(queue, LINKS).send_later(_mail(), on_sent=broken, on_failure=unused)
        await queue.drain(1.0)
    events = [entry["event"] for entry in logs]
    assert events == ["mail.queued", "mail.sent", "mail.record_failed"]


@pytest.mark.parametrize("fail", [False, True])
async def test_no_log_event_carries_the_token_the_code_or_the_address(fail: bool) -> None:
    mail = _mail(code="048213")
    mailer: object = _Mailer(fail=True) if fail else LogMailer()
    with capture_logs() as logs:
        await _deliver(mailer, mail)
    assert logs
    flat = repr(logs)
    for secret in (mail.token, mail.code, mail.to):
        assert secret not in flat
    assert all(entry.get("purpose") == "invitation" for entry in logs)
