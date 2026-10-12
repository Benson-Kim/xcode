"""MailSpy: a Mailer that records every message so tests can assert what was sent.

The real ``MailQueue`` and ``VerificationMailer`` still drive it, so after-commit, timeout
and drain behaviour is exercised. ``fail_next`` makes the next sends raise
``MailDeliveryError``; ``hang_next`` makes them never finish (the mail timeout must cut
them off). ``attempts`` counts every send, delivered or not.
"""

from __future__ import annotations

import asyncio

from xcode_api.application.ports import MailMessage
from xcode_api.infra.mail import MailDeliveryError


class MailSpy:
    def __init__(self) -> None:
        self.sent: list[MailMessage] = []
        self.attempts: list[MailMessage] = []
        self._failures = 0
        self._hangs = 0

    def fail_next(self, count: int = 1) -> None:
        self._failures += count

    def hang_next(self, count: int = 1) -> None:
        self._hangs += count

    async def send(self, message: MailMessage) -> None:
        self.attempts.append(message)
        if self._hangs:
            self._hangs -= 1
            await asyncio.Event().wait()
        if self._failures:
            self._failures -= 1
            raise MailDeliveryError("the spy was told to fail")
        self.sent.append(message)
