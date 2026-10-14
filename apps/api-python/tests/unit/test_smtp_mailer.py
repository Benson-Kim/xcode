from __future__ import annotations

import asyncio

import pytest

from xcode_api.application.ports import MailMessage
from xcode_api.infra.mail import MailDeliveryError, SmtpMailer


def test_port_587_uses_starttls() -> None:
    mailer = SmtpMailer(host="h", port=587, sender="a@b.co")
    assert mailer._start_tls is True
    assert mailer._use_tls is False


def test_port_465_uses_implicit_tls() -> None:
    mailer = SmtpMailer(host="h", port=465, sender="a@b.co")
    assert mailer._use_tls is True
    assert mailer._start_tls is False


@pytest.mark.parametrize("port", [25, 2525])
def test_any_other_port_requires_starttls_outside_development(port: int) -> None:
    mailer = SmtpMailer(host="h", port=port, sender="a@b.co")
    assert mailer._start_tls is True
    assert mailer._use_tls is False


def test_plaintext_port_allowed_in_development() -> None:
    mailer = SmtpMailer(host="h", port=25, sender="a@b.co", allow_plaintext=True)
    assert mailer._use_tls is False
    assert mailer._start_tls is False


async def _relay_without_tls(received: list[bytes]) -> asyncio.Server:
    """A mail server on this machine that offers no STARTTLS, like a host's own relay."""

    async def session(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(b"220 relay\r\n")
        data = False
        while line := await reader.readline():
            if data:
                if line == b".\r\n":
                    data = False
                    writer.write(b"250 queued\r\n")
                else:
                    received.append(line)
                    continue
            elif line.upper().startswith((b"EHLO", b"HELO")):
                writer.write(b"250 relay\r\n")
            elif line.upper().startswith(b"DATA"):
                data = True
                writer.write(b"354 go on\r\n")
            elif line.upper().startswith(b"QUIT"):
                writer.write(b"221 bye\r\n")
                await writer.drain()
                break
            else:
                writer.write(b"250 ok\r\n")
            await writer.drain()
        writer.close()

    return await asyncio.start_server(session, "127.0.0.1", 0)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
async def test_a_relay_on_this_machine_takes_mail_without_tls(host: str) -> None:
    received: list[bytes] = []
    relay = await _relay_without_tls(received)
    port = relay.sockets[0].getsockname()[1]
    try:
        mailer = SmtpMailer(host=host, port=port, sender="a@b.co", tls=False)
        await mailer.send(MailMessage(to="c@d.co", subject="s", text="Your code is 123456."))
    finally:
        relay.close()
        await relay.wait_closed()
    assert any(b"Your code is 123456." in line for line in received)


async def test_a_starttls_mailer_refuses_a_relay_without_tls() -> None:
    relay = await _relay_without_tls([])
    port = relay.sockets[0].getsockname()[1]
    try:
        mailer = SmtpMailer(host="127.0.0.1", port=port, sender="a@b.co", allow_plaintext=True)
        mailer._start_tls = True
        with pytest.raises(MailDeliveryError):
            await mailer.send(MailMessage(to="c@d.co", subject="s", text="t"))
    finally:
        relay.close()
        await relay.wait_closed()


async def test_mail_on_a_port_other_than_465_or_587_never_goes_out_in_plaintext() -> None:
    received: list[bytes] = []
    relay = await _relay_without_tls(received)
    port = relay.sockets[0].getsockname()[1]
    try:
        mailer = SmtpMailer(host="127.0.0.1", port=port, sender="a@b.co")
        with pytest.raises(MailDeliveryError):
            await mailer.send(MailMessage(to="c@d.co", subject="s", text="Your code is 123456."))
    finally:
        relay.close()
        await relay.wait_closed()
    assert received == []


@pytest.mark.parametrize("host", ["smtp.example.com", "10.0.0.5", "127.0.0.1.example.com"])
def test_mail_without_tls_is_refused_to_a_relay_on_another_machine(host: str) -> None:
    with pytest.raises(MailDeliveryError):
        SmtpMailer(host=host, port=587, sender="a@b.co", tls=False)


def test_tls_stays_on_by_default_for_a_relay_on_this_machine() -> None:
    mailer = SmtpMailer(host="127.0.0.1", port=587, sender="a@b.co")
    assert mailer._start_tls is True
