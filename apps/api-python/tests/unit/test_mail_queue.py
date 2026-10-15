from __future__ import annotations

import asyncio

from xcode_api.application.ports import MailMessage
from xcode_api.infra.mail import MailDeliveryError, MailQueue


class RecordingMailer:
    def __init__(self, *, fail_on: set[str] | None = None, delay: float = 0.0) -> None:
        self.sent: list[str] = []
        self.fail_on = fail_on or set()
        self.delay = delay

    async def send(self, message: MailMessage) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)
        if message.subject in self.fail_on:
            raise MailDeliveryError("boom")
        self.sent.append(message.subject)


def _msg(subject: str) -> MailMessage:
    return MailMessage(to="person@example.com", subject=subject, text="body")


async def test_messages_drain_in_order() -> None:
    mailer = RecordingMailer()
    queue = MailQueue(mailer)
    queue.start()
    for i in range(5):
        queue.enqueue(_msg(f"s{i}"))
    await queue.drain(1.0)
    assert mailer.sent == [f"s{i}" for i in range(5)]


async def test_one_failure_does_not_stop_the_drain() -> None:
    mailer = RecordingMailer(fail_on={"s2"})
    queue = MailQueue(mailer)
    queue.start()
    for i in range(4):
        queue.enqueue(_msg(f"s{i}"))
    await queue.drain(1.0)
    assert mailer.sent == ["s0", "s1", "s3"]


async def test_full_queue_drops_without_blocking() -> None:
    mailer = RecordingMailer(delay=10.0)
    queue = MailQueue(mailer, max_pending=1)
    queue.start()
    for i in range(5):
        queue.enqueue(_msg(f"s{i}"))
    assert queue.depth <= 1


async def test_drain_respects_timeout() -> None:
    mailer = RecordingMailer(delay=10.0)
    queue = MailQueue(mailer, max_pending=10)
    queue.start()
    queue.enqueue(_msg("slow"))
    await asyncio.sleep(0)
    await queue.drain(0.05)
    assert mailer.sent == []
