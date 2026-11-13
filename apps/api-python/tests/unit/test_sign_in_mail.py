"""The notice that a person's sign-in email or mobile number changed (``sign_in_change_message``):
to the replaced email, naming the new one only masked; to the new email; to the current one when
only the number changed. Each says who changed it, that every device is signed out and to
contact the organization if it was not expected, and carries no code or link. Names are folded
to one line and escaped in the HTML part; the tags carry the purpose and the kind, never an
address. ``QueuedSignInNotifier`` sends it through the queue and reports the outcome."""

from __future__ import annotations

import pytest

from xcode_api.application.ports import MailMessage, SignInNotice
from xcode_api.domain.tenancy import SignInNoticeKind
from xcode_api.infra.mail import (
    SIGN_IN_DETAILS_SUBJECT,
    SIGN_IN_EMAIL_SUBJECT,
    MailDeliveryError,
    MailQueue,
    QueuedSignInNotifier,
    sign_in_change_message,
)

SIGNED_OUT = "You have been signed out of XCODE on every device and need to sign in again."
UNEXPECTED = "If you did not expect this change, contact Metro Trans straight away."


def _notice(kind: SignInNoticeKind = SignInNoticeKind.OLD, **overrides: object) -> SignInNotice:
    fields: dict[str, object] = {
        "to": "jane@example.com",
        "kind": kind,
        "first_name": "Jane",
        "actor_name": "Olive Owner",
        "organization_name": "Metro Trans",
        "new_address_hint": "j***@example.org" if kind is SignInNoticeKind.OLD else None,
    }
    fields.update(overrides)
    return SignInNotice(**fields)  # type: ignore[arg-type]


def test_the_replaced_email_hears_the_new_one_only_masked() -> None:
    message = sign_in_change_message(_notice())
    assert message.to == "jane@example.com"
    assert message.subject == SIGN_IN_EMAIL_SUBJECT
    assert message.text == "\n\n".join(
        (
            "Hello Jane,",
            "Olive Owner changed the email you use to sign in to XCODE in Metro Trans. "
            "It is now j***@example.org. This address no longer signs you in.",
            SIGNED_OUT,
            UNEXPECTED,
        )
    )
    assert message.html is not None
    assert "<strong>j***@example.org</strong>" in message.html


def test_without_a_hint_the_replaced_email_hears_only_that_it_no_longer_signs_in() -> None:
    message = sign_in_change_message(_notice(new_address_hint=None))
    assert (
        "Olive Owner changed the email you use to sign in to XCODE in Metro Trans. "
        "This address no longer signs you in."
    ) in message.text
    assert "It is now" not in message.text


def test_the_new_email_hears_that_it_now_signs_in() -> None:
    message = sign_in_change_message(_notice(SignInNoticeKind.NEW, to="janet@example.org"))
    assert message.to == "janet@example.org"
    assert message.subject == SIGN_IN_DETAILS_SUBJECT
    assert (
        "Olive Owner changed your sign-in details for XCODE in Metro Trans. "
        "This email address now signs you in."
    ) in message.text
    assert "@" not in message.text


def test_the_current_email_hears_of_a_new_mobile_number_without_the_number() -> None:
    message = sign_in_change_message(_notice(SignInNoticeKind.CURRENT))
    assert message.subject == SIGN_IN_DETAILS_SUBJECT
    assert (
        "Olive Owner changed the mobile number you use to sign in to XCODE in Metro Trans."
    ) in message.text
    assert not any(ch.isdigit() for ch in message.text)


@pytest.mark.parametrize("kind", list(SignInNoticeKind))
def test_every_notice_says_the_devices_are_signed_out_and_whom_to_contact(
    kind: SignInNoticeKind,
) -> None:
    message = sign_in_change_message(_notice(kind))
    assert SIGNED_OUT in message.text
    assert message.text.endswith(UNEXPECTED)
    assert "http" not in message.text + (message.html or "")
    assert message.tags == {"purpose": "sign_in_change", "kind": kind.value}


def test_a_gone_actor_is_an_administrator_and_a_missing_name_a_plain_greeting() -> None:
    message = sign_in_change_message(_notice(actor_name=None, first_name=""))
    assert message.text.startswith("Hello,\n\nAn administrator changed the email")


@pytest.mark.parametrize(
    ("field", "value", "folded"),
    [
        ("actor_name", "Olive\r\nBcc: evil@example.com", "Olive Bcc: evil@example.com"),
        ("first_name", "Jane\nDoe", "Jane Doe"),
        ("organization_name", "Metro\r\tTrans", "Metro Trans"),
    ],
)
def test_control_characters_in_a_name_are_folded_to_one_line(
    field: str, value: str, folded: str
) -> None:
    message = sign_in_change_message(_notice(**{field: value}))
    assert "\r" not in message.text
    assert folded in message.text
    assert message.text.count("\n") == 6


@pytest.mark.parametrize("field", ["actor_name", "first_name", "organization_name"])
def test_a_name_cannot_inject_markup_into_the_html_part(field: str) -> None:
    message = sign_in_change_message(_notice(**{field: '<script>alert("x")</script>'}))
    assert message.html is not None
    assert "<script>" not in message.html
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in message.html


def test_neither_the_message_nor_the_notice_repr_carries_an_address() -> None:
    notice = _notice(to="secret.jane@example.com", new_address_hint="s***@example.org")
    text = repr(sign_in_change_message(notice)) + repr(notice)
    assert "secret.jane" not in text
    assert "s***" not in text


class _Mailer:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[MailMessage] = []

    async def send(self, message: MailMessage) -> None:
        if self.fail:
            raise MailDeliveryError("down")
        self.sent.append(message)


async def _notify(mailer: _Mailer) -> list[str]:
    outcome: list[str] = []

    async def on_sent() -> None:
        outcome.append("sent")

    async def on_failure() -> None:
        outcome.append("failed")

    queue = MailQueue(mailer)
    queue.start()
    QueuedSignInNotifier(queue).notify(_notice(), on_sent=on_sent, on_failure=on_failure)
    await queue.drain(1.0)
    return outcome


async def test_a_delivered_notice_runs_on_sent() -> None:
    mailer = _Mailer()
    assert await _notify(mailer) == ["sent"]
    assert [m.subject for m in mailer.sent] == [SIGN_IN_EMAIL_SUBJECT]


async def test_a_failed_notice_runs_on_failure() -> None:
    assert await _notify(_Mailer(fail=True)) == ["failed"]
