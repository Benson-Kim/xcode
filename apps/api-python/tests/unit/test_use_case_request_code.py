"""``RequestCode`` orchestration: the code is mailed only after the routine that stored it
returned, the answer never shows whether a mail was sent, and a failed mail withdraws the
code."""

from __future__ import annotations

import pytest

from xcode_api.application.auth.request_code import RequestCodeCommand
from xcode_api.domain.identity import AuthEnvelope, CodePurpose, EnvelopeStatus

from .conftest import AuthKit

CHECK_EMAIL = AuthEnvelope(EnvelopeStatus.CHECK_EMAIL)


def _command(purpose: CodePurpose, phone: str = "0712345678") -> RequestCodeCommand:
    return RequestCodeCommand("req-2", phone, "phone-1", purpose)


@pytest.mark.parametrize(
    ("purpose", "pin"), [(CodePurpose.FIRST_SETUP, None), (CodePurpose.PIN_RESET, "5826")]
)
async def test_an_issued_code_is_queued_after_the_routine_returned(
    kit: AuthKit, purpose: CodePurpose, pin: str | None
) -> None:
    user_id = await kit.account(pin=pin, trusted=())
    envelope = await kit.request_code().execute(_command(purpose))

    assert kit.calls == ["request_code", "mail.send_later"]
    assert envelope == CHECK_EMAIL
    (mail,) = kit.mail.mails
    (code,) = kit.identity.codes(user_id)
    assert (mail.to, mail.purpose, mail.code, mail.code_id) == (
        "jane.doe@example.com",
        purpose,
        kit.secrets.code,
        code.code_id,
    )
    assert code.code_hash == kit.digest(kit.secrets.code)


async def test_nothing_is_mailed_for_an_unknown_number_and_the_answer_is_identical(
    kit: AuthKit,
) -> None:
    await kit.account(pin=None, trusted=())
    issued = await kit.request_code().execute(_command(CodePurpose.FIRST_SETUP))
    kit.calls.clear()
    unknown = await kit.request_code().execute(_command(CodePurpose.FIRST_SETUP, "0799999999"))
    assert kit.calls == ["request_code"]
    assert unknown == issued == CHECK_EMAIL


async def test_an_account_that_is_not_ready_gets_the_same_answer(kit: AuthKit) -> None:
    await kit.account(pin="5826", trusted=())
    envelope = await kit.request_code().execute(_command(CodePurpose.FIRST_SETUP))
    assert kit.calls == ["request_code"]
    assert envelope == CHECK_EMAIL


async def test_a_failed_mail_withdraws_the_code(kit: AuthKit) -> None:
    user_id = await kit.account(pin=None, trusted=())
    await kit.request_code().execute(_command(CodePurpose.FIRST_SETUP))
    (on_failure,) = kit.mail.failure_callbacks
    await on_failure()
    assert kit.calls == ["request_code", "mail.send_later", "withdraw_code"]
    (code,) = kit.identity.codes(user_id)
    assert code.withdrawn
    kit.calls.clear()
    again = await kit.request_code().execute(_command(CodePurpose.FIRST_SETUP))
    assert kit.calls == ["request_code", "mail.send_later"]
    assert again == CHECK_EMAIL


async def test_development_codes_return_the_issued_code_only(kit: AuthKit) -> None:
    await kit.account(pin=None, trusted=())
    issued = await kit.request_code(development_codes=True).execute(
        _command(CodePurpose.FIRST_SETUP)
    )
    silent = await kit.request_code(development_codes=True).execute(
        _command(CodePurpose.FIRST_SETUP, "0799999999")
    )
    assert issued.development_code == kit.secrets.code
    assert silent.development_code is None
