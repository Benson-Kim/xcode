"""The verification mail: one subject; a body of the code, the purpose and the device and nothing
else (``docs/07-auth.md`` 12.6); and the delivery paths of ``VerificationMailer``."""

from __future__ import annotations

from uuid import UUID

import pytest
from structlog.testing import capture_logs

from xcode_api.application.ports import VerificationMail
from xcode_api.domain.identity import CodePurpose
from xcode_api.infra.mail import (
    LogMailer,
    MailQueue,
    VerificationMailer,
    verification_message,
)

from ..support.mail import MailSpy

CODE_ID = UUID("0b6a9f4e-2c1d-4e8b-9a7f-5d3c2b1a0e9f")


def _mail(purpose: CodePurpose, device_name: str | None = None) -> VerificationMail:
    return VerificationMail(
        to="jane.doe@example.com",
        purpose=purpose,
        code="048213",
        code_id=CODE_ID,
        request_id="req-1",
        device_name=device_name,
    )


@pytest.mark.parametrize(
    ("purpose", "device_name", "body"),
    [
        (CodePurpose.FIRST_SETUP, None, "Code: 048213\nFor: First sign in\nDevice: Unknown device"),
        (
            CodePurpose.NEW_DEVICE,
            "Tecno Spark 10",
            "Code: 048213\nFor: Confirm this device\nDevice: Tecno Spark 10",
        ),
        (CodePurpose.PIN_RESET, "A", "Code: 048213\nFor: Reset PIN\nDevice: A"),
    ],
)
def test_the_code_email_holds_the_code_the_purpose_and_the_device_only(
    purpose: CodePurpose, device_name: str | None, body: str
) -> None:
    message = verification_message(_mail(purpose, device_name))
    assert message.to == "jane.doe@example.com"
    assert message.subject == "Your verification code"
    assert message.text == body
    assert message.tags == {
        "purpose": purpose.value,
        "code_id": str(CODE_ID),
        "request_id": "req-1",
    }


def test_the_message_repr_carries_neither_address_nor_code() -> None:
    text = repr(verification_message(_mail(CodePurpose.NEW_DEVICE))) + repr(
        _mail(CodePurpose.NEW_DEVICE)
    )
    assert "jane.doe" not in text
    assert "048213" not in text


async def test_send_now_reports_delivery() -> None:
    spy = MailSpy()
    mailer = VerificationMailer(spy, MailQueue(spy), timeout_seconds=1)
    assert await mailer.send_now(_mail(CodePurpose.NEW_DEVICE)) is True
    assert [m.text for m in spy.sent] == [
        "Code: 048213\nFor: Confirm this device\nDevice: Unknown device"
    ]


async def test_send_now_reports_a_failure_without_raising() -> None:
    spy = MailSpy()
    spy.fail_next()
    mailer = VerificationMailer(spy, MailQueue(spy), timeout_seconds=1)
    assert await mailer.send_now(_mail(CodePurpose.NEW_DEVICE)) is False
    assert spy.sent == []


async def test_send_now_gives_up_at_the_mail_timeout() -> None:
    spy = MailSpy()
    spy.hang_next()
    mailer = VerificationMailer(spy, MailQueue(spy), timeout_seconds=0.05)
    assert await mailer.send_now(_mail(CodePurpose.NEW_DEVICE)) is False


async def test_send_later_runs_the_failure_callback_after_a_failed_delivery() -> None:
    spy = MailSpy()
    queue = MailQueue(spy)
    mailer = VerificationMailer(spy, queue, timeout_seconds=1)
    withdrawn: list[str] = []

    async def withdraw() -> None:
        withdrawn.append("withdrawn")

    queue.start()
    spy.fail_next()
    mailer.send_later(_mail(CodePurpose.PIN_RESET), on_failure=withdraw)
    mailer.send_later(_mail(CodePurpose.FIRST_SETUP), on_failure=withdraw)
    await queue.drain(1)
    assert withdrawn == ["withdrawn"]
    assert [m.text for m in spy.sent] == [
        "Code: 048213\nFor: First sign in\nDevice: Unknown device"
    ]


async def test_a_failing_failure_callback_is_swallowed() -> None:
    spy = MailSpy()
    queue = MailQueue(spy)
    mailer = VerificationMailer(spy, queue, timeout_seconds=1)

    async def broken() -> None:
        raise RuntimeError("database down")

    queue.start()
    spy.fail_next()
    mailer.send_later(_mail(CodePurpose.PIN_RESET), on_failure=broken)
    mailer.send_later(_mail(CodePurpose.FIRST_SETUP), on_failure=broken)
    await queue.drain(1)
    assert len(spy.sent) == 1


async def test_log_mailer_reveals_the_body_only_when_told() -> None:
    message = verification_message(_mail(CodePurpose.FIRST_SETUP))
    with capture_logs() as hidden:
        await LogMailer().send(message)
    assert "048213" not in repr(hidden)
    assert [event["event"] for event in hidden] == ["mail.logged"]
    with capture_logs() as revealed:
        await LogMailer(reveal_body=True).send(message)
    assert "048213" in repr(revealed)
