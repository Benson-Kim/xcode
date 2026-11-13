"""Mail adapters: the verification, invitation, deletion-request and sign-in change messages in
one branded layout, log and SMTP mailers, and a drained queue.

Log events carry the recipient hash and non-secret tags, never the address, the code or the
invitation token; the log mailer writes the body only when told to (development and testing).
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import unicodedata
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiosmtplib
import structlog

from ..application.ports import (
    DeletionNotice,
    InvitationMail,
    Mailer,
    MailMessage,
    SignInNotice,
    VerificationMail,
)
from ..domain.identity import CodePurpose
from ..domain.tenancy import SignInNoticeKind
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
SuccessCallback = Callable[[], Awaitable[None]]


# The one branded layout of every mail. A body is a sequence of blocks; each renders to its text
# lines and to an HTML fragment in which every value is escaped. The text part is the blocks'
# lines, blank-line separated; the HTML part wraps the fragments in the XCODE frame: inline
# styles only, no remote images, no scripts.

_BRAND = "#1f6feb"
_INK = "#1f2933"
_MUTED = "#52606d"
_RULE = "#e4e7eb"
_PAGE = "#f4f5f7"
_FOOTER = "This is an automatic message from XCODE."


@dataclass(frozen=True, slots=True)
class Strong:
    """A run of a paragraph shown in bold in the HTML part."""

    text: str


@dataclass(frozen=True, slots=True)
class _Block:
    lines: tuple[str, ...]
    html: str


def _paragraph(*runs: str | Strong, muted: bool = False) -> _Block:
    text = "".join(r.text if isinstance(r, Strong) else r for r in runs)
    inner = "".join(
        f"<strong>{_escape(r.text)}</strong>" if isinstance(r, Strong) else _escape(r) for r in runs
    )
    style = f"margin:0 0 16px;color:{_MUTED};font-size:13px" if muted else "margin:0 0 16px"
    return _Block((text,), f'<p style="{style}">{inner}</p>')


def _facts(rows: Sequence[tuple[str, str]]) -> _Block:
    cells = "".join(
        f'<tr><td style="padding:4px 16px 4px 0;color:{_MUTED}">{_escape(label)}</td>'
        f'<td style="padding:4px 0;font-weight:bold">{_escape(value)}</td></tr>'
        for label, value in rows
    )
    return _Block(
        tuple(f"{label}: {value}" for label, value in rows),
        f'<table role="presentation" style="margin:0 0 16px;border-collapse:collapse">{cells}'
        "</table>",
    )


def _button(label: str, url: str) -> _Block:
    if not _web_url(url):
        return _paragraph(f"{label}: {url}")
    return _Block(
        (f"{label}: {url}",),
        f'<p style="margin:0 0 16px"><a href="{_escape(url)}" style="display:inline-block;'
        f"padding:10px 18px;background:{_BRAND};color:#ffffff;text-decoration:none;"
        f'border-radius:6px">{_escape(label)}</a></p>',
    )


def _links(heading: str, links: Sequence[tuple[str, str]]) -> _Block:
    anchors = "".join(
        f'<br><a href="{_escape(url)}" style="color:{_BRAND}">{_escape(name)}</a>'
        if _web_url(url)
        else f"<br>{_escape(name)}: {_escape(url)}"
        for name, url in links
    )
    return _Block(
        (heading, *(f"{name}: {url}" for name, url in links)),
        f'<p style="margin:0 0 16px">{_escape(heading)}{anchors}</p>',
    )


def _layout(subject: str, blocks: Sequence[_Block]) -> tuple[str, str]:
    """The text part and the HTML part of one mail."""
    text = "\n\n".join("\n".join(block.lines) for block in blocks)
    body = "".join(block.html for block in blocks)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_escape(subject)}</title></head>"
        f'<body style="margin:0;padding:0;background:{_PAGE};color:{_INK};'
        'font-family:Arial,Helvetica,sans-serif">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{_PAGE}"><tr><td align="center" style="padding:24px 12px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:560px;background:#ffffff;border:1px solid {_RULE};border-radius:8px">'
        f'<tr><td style="padding:20px 28px;border-bottom:3px solid {_BRAND}">'
        f'<span style="font-size:20px;font-weight:bold;letter-spacing:3px;color:{_BRAND}">'
        "XCODE</span></td></tr>"
        f'<tr><td style="padding:24px 28px 8px;font-size:15px;line-height:1.5">{body}</td></tr>'
        f'<tr><td style="padding:16px 28px;border-top:1px solid {_RULE};font-size:12px;'
        f'color:{_MUTED}">{_escape(_FOOTER)}</td></tr>'
        "</table></td></tr></table></body></html>"
    )
    return text, page


def _web_url(url: str) -> bool:
    return url.lower().startswith(("https://", "http://"))


def verification_message(mail: VerificationMail) -> MailMessage:
    """The code, its purpose and the device that asked, nothing else."""
    facts = _facts(
        (
            ("Code", mail.code),
            ("For", PURPOSE_LABELS[mail.purpose]),
            ("Device", mail.device_name or UNKNOWN_DEVICE),
        )
    )
    text, body_html = _layout(VERIFICATION_SUBJECT, (facts,))
    return MailMessage(
        to=mail.to,
        subject=VERIFICATION_SUBJECT,
        text=text,
        html=body_html,
        tags={
            "purpose": mail.purpose.value,
            "code_id": str(mail.code_id),
            "request_id": mail.request_id,
        },
    )


@dataclass(frozen=True, slots=True)
class InvitationLinks:
    """Where an invitation points: the web origin (``XCODE_PUBLIC_WEB_URL``, never the
    request's Host) and the store pages, when configured."""

    web_url: str
    app_store_url: str = ""
    play_store_url: str = ""

    def invite_link(self, token: str) -> str:
        # The token rides in the fragment, so it never reaches a server log or a Referer.
        return f"{self.web_url}/invite#{token}"


INVITATION_SUBJECT = "{organization} invited you to XCODE"


def invitation_message(mail: InvitationMail, links: InvitationLinks) -> MailMessage:
    """Text and HTML for one invitation. Every admin-typed value is folded to one line, and
    escaped in the HTML part; no phone number is ever included."""
    organization = _one_line(mail.organization_name)
    first_name = _one_line(mail.first_name)
    inviter = _one_line(mail.inviter_name or "")
    link = links.invite_link(mail.token)
    code = f"{mail.code[:3]} {mail.code[3:]}"
    until = _local_time(mail)
    added = f"{inviter or 'Someone'} added you to {organization}."
    greeting = f"Hello {first_name}," if first_name else "Hello,"
    stores = _store_lines(links)
    subject = INVITATION_SUBJECT.format(organization=organization)

    blocks = [
        _paragraph(greeting),
        _paragraph(added),
        _button("Set up my access", link),
        _paragraph("Or open the XCODE app, enter your mobile number and type ", Strong(code), "."),
        _paragraph(f"The link and code work until {until}."),
    ]
    if stores:
        blocks.append(_links("Get the app:", stores))
    blocks.append(_paragraph(_NO_PIN_BY_EMAIL, muted=True))
    text, body_html = _layout(subject, blocks)
    tags = {"purpose": "invitation", "invitation_id": str(mail.invitation_id)}
    if mail.request_id:
        tags["request_id"] = mail.request_id
    support = _one_line(mail.support_email or "")
    return MailMessage(
        to=mail.to,
        subject=subject,
        text=text,
        html=body_html,
        reply_to=support or None,
        tags=tags,
    )


_NO_PIN_BY_EMAIL = "XCODE never asks for your PIN by email. If you did not expect this, ignore it."


DELETION_REQUEST_SUBJECT = "A member asked to delete their XCODE account"


def deletion_request_message(notice: DeletionNotice) -> MailMessage:
    """Tell one administrator who can block members that a member asked to delete their
    account. Every member-typed name is folded to one line and escaped in the HTML part; no
    address, phone number or other personal data is included."""
    admin = _one_line(notice.recipient_first_name)
    requester = _one_line(notice.requester_name)
    organization = _one_line(notice.organization_name)
    greeting = f"Hello {admin}," if admin else "Hello,"
    asked = f"{requester or 'A member'} has asked to delete their XCODE account in {organization}."
    guidance = (
        "Open People in XCODE to review the request. If it is genuine, block and erase the member "
        "there; their financial records are kept against a former member."
    )
    text, body_html = _layout(
        DELETION_REQUEST_SUBJECT,
        (_paragraph(greeting), _paragraph(asked), _paragraph(guidance, muted=True)),
    )
    tags = {"purpose": "deletion_request"}
    if notice.request_id:
        tags["request_id"] = notice.request_id
    return MailMessage(
        to=notice.to,
        subject=DELETION_REQUEST_SUBJECT,
        text=text,
        html=body_html,
        tags=tags,
    )


SIGN_IN_EMAIL_SUBJECT = "Your XCODE sign-in email was changed"
SIGN_IN_DETAILS_SUBJECT = "Your XCODE sign-in details were changed"
_SIGNED_OUT = "You have been signed out of XCODE on every device and need to sign in again."


def sign_in_change_message(notice: SignInNotice) -> MailMessage:
    """Tell a person their sign-in email or mobile number changed: at the replaced email (naming
    the new one only masked), at the new one, or at the current one when only the number
    changed. It says who made the change and to contact the organization if it was not expected;
    it carries no code, link or phone number. Every name is folded to one line and escaped in
    the HTML part."""
    person = _one_line(notice.first_name)
    actor = _one_line(notice.actor_name or "") or "An administrator"
    organization = _one_line(notice.organization_name)
    hint = _one_line(notice.new_address_hint or "")
    greeting = f"Hello {person}," if person else "Hello,"
    subject = SIGN_IN_DETAILS_SUBJECT
    if notice.kind is SignInNoticeKind.OLD:
        subject = SIGN_IN_EMAIL_SUBJECT
        changed = (
            _paragraph(
                f"{actor} changed the email you use to sign in to XCODE in {organization}. "
                "It is now ",
                Strong(hint),
                ". This address no longer signs you in.",
            )
            if hint
            else _paragraph(
                f"{actor} changed the email you use to sign in to XCODE in {organization}. "
                "This address no longer signs you in."
            )
        )
    elif notice.kind is SignInNoticeKind.NEW:
        changed = _paragraph(
            f"{actor} changed your sign-in details for XCODE in {organization}. "
            "This email address now signs you in."
        )
    else:
        changed = _paragraph(
            f"{actor} changed the mobile number you use to sign in to XCODE in {organization}."
        )
    unexpected = _paragraph(
        f"If you did not expect this change, contact {organization} straight away.", muted=True
    )
    text, body_html = _layout(
        subject, (_paragraph(greeting), changed, _paragraph(_SIGNED_OUT), unexpected)
    )
    return MailMessage(
        to=notice.to,
        subject=subject,
        text=text,
        html=body_html,
        tags={"purpose": "sign_in_change", "kind": notice.kind.value},
    )


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


def _one_line(value: str) -> str:
    """Control and format characters (CR, LF, NUL, bidi overrides) become spaces, so an
    admin-typed name can neither add a header nor reshape the message."""
    return " ".join("".join(" " if _is_control(ch) else ch for ch in value).split())


def _is_control(ch: str) -> bool:
    return unicodedata.category(ch)[0] == "C"


def _local_time(mail: InvitationMail) -> str:
    try:
        zone = ZoneInfo(mail.time_zone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    moment = mail.expires_at.astimezone(zone)
    return f"{moment:%A} {moment.day} {moment:%B %Y}, {moment:%H:%M} {moment:%Z}"


def _store_lines(links: InvitationLinks) -> list[tuple[str, str]]:
    stores = (("App Store", links.app_store_url), ("Google Play", links.play_store_url))
    return [(name, url) for name, url in stores if url]


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
    """Sends via SMTP. Implicit TLS on port 465, STARTTLS required on any other port (587, or
    2525 where a host blocks the standard ports), plaintext refused unless development or a
    relay on this machine. Delivery failures raise :class:`MailDeliveryError`.
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
        if tls and port not in (465, 587) and allow_plaintext:
            self._use_tls = False
            self._start_tls = False

    async def send(self, message: MailMessage) -> None:
        email = EmailMessage()
        email["From"] = self._sender
        email["To"] = message.to
        email["Subject"] = message.subject
        if message.reply_to:
            email["Reply-To"] = message.reply_to
        email.set_content(message.text)
        if message.html is not None:
            email.add_alternative(message.html, subtype="html")
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
    on_success: SuccessCallback | None = None


class MailQueue:
    """A bounded in-process queue drained by one background task, in order.

    ``enqueue`` never blocks: a full queue drops the message and logs ``mail.dropped`` at
    ERROR (``on_failure`` does not run; a durable caller's sweep re-sends it). Each send is
    isolated; a failure logs ``mail.failed`` and runs ``on_failure``, a success logs
    ``mail.sent`` and runs ``on_success``. A callback's own failure is logged and swallowed,
    and never stops the drain. ``drain`` empties the queue for shutdown within a budget.
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

    def enqueue(
        self,
        message: MailMessage,
        *,
        on_failure: FailureCallback | None = None,
        on_success: SuccessCallback | None = None,
    ) -> None:
        rh = recipient_hash(message.to)
        try:
            self._queue.put_nowait(_Pending(message, on_failure, on_success))
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
                await _run_callback(pending.on_failure, "mail.withdraw_failed", message.tags)
        else:
            logger.info("mail.sent", recipient_hash=rh, subject=message.subject, **message.tags)
            if pending.on_success is not None:
                await _run_callback(pending.on_success, "mail.record_failed", message.tags)

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


class QueuedInvitationMailer:
    """The ``InvitationMailer`` adapter: renders the invitation and queues it after the reply;
    the callbacks record the delivery state."""

    def __init__(self, queue: MailQueue, links: InvitationLinks) -> None:
        self._queue = queue
        self._links = links

    def send_later(
        self, mail: InvitationMail, *, on_sent: SuccessCallback, on_failure: FailureCallback
    ) -> None:
        self._queue.enqueue(
            invitation_message(mail, self._links), on_failure=on_failure, on_success=on_sent
        )


class QueuedDeletionNotifier:
    """The ``DeletionNotifier`` adapter: renders each notice and queues it after the reply; the
    callbacks record the send in the notice outbox, whose sweep retries what was lost."""

    def __init__(self, queue: MailQueue) -> None:
        self._queue = queue

    def notify(
        self, notice: DeletionNotice, *, on_sent: SuccessCallback, on_failure: FailureCallback
    ) -> None:
        self._queue.enqueue(
            deletion_request_message(notice), on_failure=on_failure, on_success=on_sent
        )


class QueuedSignInNotifier:
    """The ``SignInNotifier`` adapter: renders each notice and queues it after the reply; the
    callbacks record the send in the notice outbox, whose sweep retries what was lost."""

    def __init__(self, queue: MailQueue) -> None:
        self._queue = queue

    def notify(
        self, notice: SignInNotice, *, on_sent: SuccessCallback, on_failure: FailureCallback
    ) -> None:
        self._queue.enqueue(
            sign_in_change_message(notice), on_failure=on_failure, on_success=on_sent
        )


async def _run_callback(
    callback: Callable[[], Awaitable[None]], event: str, tags: Mapping[str, str]
) -> None:
    try:
        await callback()
    except Exception as exc:
        logger.error(event, error=type(exc).__name__, **tags)
