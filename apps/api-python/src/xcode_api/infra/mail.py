"""Mail adapters: the verification message, log and SMTP mailers, and a drained queue.

Log events carry the recipient hash and non-secret tags, never the address or the code; the
log mailer writes the body only when told to (development and testing).
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from email.message import EmailMessage
from types import MappingProxyType

import aiosmtplib
import structlog

from ..application.ports import Mailer, MailMessage, VerificationMail
from ..domain.identity import CodePurpose
from ..settings import is_local_host

logger = structlog.get_logger("xcode_api.mail")

VERIFICATION_SUBJECT = "Your verification code"
UNKNOWN_DEVICE = "Unknown device"
# The step titles of the sign-in screens, not the enum values.
PURPOSE_LABELS = MappingProxyType(
    {
        CodePurpose.FIRST_SETUP: "First sign in",
        CodePurpose.NEW_DEVICE: "Confirm this device",
        CodePurpose.PIN_RESET: "Reset PIN",
    }
)

FailureCallback = Callable[[], Awaitable[None]]


def verification_message(mail: VerificationMail) -> MailMessage:
    """The code, its purpose and the device that asked, nothing else."""
    lines = (
        f"Code: {mail.code}",
        f"For: {PURPOSE_LABELS[mail.purpose]}",
        f"Device: {mail.device_name or UNKNOWN_DEVICE}",
    )
    return MailMessage(
        to=mail.to,
        subject=VERIFICATION_SUBJECT,
        text="\n".join(lines),
        tags={
            "purpose": mail.purpose.value,
            "code_id": str(mail.code_id),
            "request_id": mail.request_id,
        },
    )


class MailDeliveryError(Exception):
    """Raised by a mailer when a message could not be delivered."""


def recipient_hash(address: str) -> str:
    digest = hashlib.sha256(address.strip().lower().encode("utf-8")).hexdigest()
    return digest[:12]


class LogMailer:
    """Logs instead of sending. Allowed only in development and testing, where
    ``reveal_body`` lets a developer read the code from the log (``mail.body``)."""

    def __init__(self, *, reveal_body: bool = False) -> None:
        self._reveal_body = reveal_body

    async def send(self, message: MailMessage) -> None:
        rh = recipient_hash(message.to)
        logger.info("mail.logged", recipient_hash=rh, subject=message.subject, **message.tags)
        if self._reveal_body:
            logger.info("mail.body", recipient_hash=rh, text=message.text)


class SmtpMailer:
    """Sends via SMTP. STARTTLS on port 587, implicit TLS on 465, plaintext refused unless
    development. Delivery failures raise :class:`MailDeliveryError`.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        username: str = "",
        password: str = "",
        timeout_seconds: int = 10,
        tls: bool = True,
        allow_plaintext: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._username = username
        self._password = password
        self._timeout = timeout_seconds
        self._use_tls = tls and port == 465
        self._start_tls = tls and port != 465
        if not tls and not (allow_plaintext or is_local_host(host)):
            raise MailDeliveryError(
                "SMTP without TLS is refused outside development, except to a relay on this machine"
            )
        if tls and port not in (465, 587) and not allow_plaintext:
            raise MailDeliveryError(
                "plaintext SMTP is refused outside development (use port 587 or 465)"
            )
        if tls and port not in (465, 587) and allow_plaintext:
            self._use_tls = False
            self._start_tls = False

    async def send(self, message: MailMessage) -> None:
        email = EmailMessage()
        email["From"] = self._sender
        email["To"] = message.to
        email["Subject"] = message.subject
        email.set_content(message.text)
        try:
            await aiosmtplib.send(
                email,
                hostname=self._host,
                port=self._port,
                username=self._username or None,
                password=self._password or None,
                use_tls=self._use_tls,
                start_tls=self._start_tls,
                timeout=self._timeout,
            )
        except (aiosmtplib.SMTPException, OSError, TimeoutError) as exc:
            raise MailDeliveryError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class _Pending:
    message: MailMessage
    on_failure: FailureCallback | None


class MailQueue:
    """A bounded in-process queue drained by one background task, in order.

    ``enqueue`` never blocks: a full queue drops the message and logs ``mail.dropped`` at
    ERROR. Each send is isolated; a failure logs ``mail.failed``, runs the message's
    ``on_failure`` callback (whose own failure is logged and swallowed) and does not stop
    the drain. ``drain`` empties the queue for shutdown within a budget.
    """

    def __init__(self, mailer: Mailer, *, max_pending: int = 1000) -> None:
        self._mailer = mailer
        self._queue: asyncio.Queue[_Pending] = asyncio.Queue(maxsize=max_pending)
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    @property
    def depth(self) -> int:
        return self._queue.qsize()

    def start(self) -> None:
        if self._task is None:
            self._stopped.clear()
            self._task = asyncio.create_task(self._run())

    def enqueue(self, message: MailMessage, *, on_failure: FailureCallback | None = None) -> None:
        rh = recipient_hash(message.to)
        try:
            self._queue.put_nowait(_Pending(message, on_failure))
        except asyncio.QueueFull:
            logger.error("mail.dropped", recipient_hash=rh, subject=message.subject, **message.tags)
            return
        logger.info("mail.queued", recipient_hash=rh, subject=message.subject, **message.tags)

    async def _run(self) -> None:
        while True:
            pending = await self._queue.get()
            await self._deliver(pending)
            self._queue.task_done()

    async def _deliver(self, pending: _Pending) -> None:
        message = pending.message
        rh = recipient_hash(message.to)
        try:
            await self._mailer.send(message)
        except Exception as exc:
            logger.error("mail.failed", recipient_hash=rh, error=type(exc).__name__, **message.tags)
            if pending.on_failure is not None:
                await _run_failure_callback(pending.on_failure, message.tags)
        else:
            logger.info("mail.sent", recipient_hash=rh, subject=message.subject, **message.tags)

    async def drain(self, timeout_seconds: float) -> None:
        """Deliver everything already queued within the budget, then stop the task."""
        try:
            await asyncio.wait_for(self._queue.join(), timeout=timeout_seconds)
        except TimeoutError:
            logger.warning("mail.drain_timeout", pending=self.depth)
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


class VerificationMailer:
    """The ``CodeMailer`` adapter: renders the verification message, sends it before the
    reply (``send_now``, bounded by the mail timeout) or through the queue after the reply
    (``send_later``)."""

    def __init__(self, mailer: Mailer, queue: MailQueue, *, timeout_seconds: float) -> None:
        self._mailer = mailer
        self._queue = queue
        self._timeout = timeout_seconds

    async def send_now(self, mail: VerificationMail) -> bool:
        message = verification_message(mail)
        rh = recipient_hash(message.to)
        try:
            await asyncio.wait_for(self._mailer.send(message), timeout=self._timeout)
        except Exception as exc:
            logger.error("mail.failed", recipient_hash=rh, error=type(exc).__name__, **message.tags)
            return False
        logger.info("mail.sent", recipient_hash=rh, subject=message.subject, **message.tags)
        return True

    def send_later(self, mail: VerificationMail, *, on_failure: FailureCallback) -> None:
        self._queue.enqueue(verification_message(mail), on_failure=on_failure)


async def _run_failure_callback(callback: FailureCallback, tags: Mapping[str, str]) -> None:
    try:
        await callback()
    except Exception as exc:
        logger.error("mail.withdraw_failed", error=type(exc).__name__, **tags)
