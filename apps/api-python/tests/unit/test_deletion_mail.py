"""The account-deletion notice to an administrator who can block members
(``deletion_request_message``): one subject; a body naming the member and the organization and
nothing else; every member-typed name folded to one line and HTML-escaped so it can neither add
a header nor inject markup; and tags of the purpose and the request id, never the address."""

from __future__ import annotations

import pytest

from xcode_api.application.ports import DeletionNotice
from xcode_api.infra.mail import DELETION_REQUEST_SUBJECT, deletion_request_message


def _notice(**overrides: object) -> DeletionNotice:
    fields: dict[str, object] = {
        "to": "admin@example.com",
        "recipient_first_name": "Ann",
        "requester_name": "Jane Doe",
        "organization_name": "Metro Trans",
        "request_id": "req-1",
    }
    fields.update(overrides)
    return DeletionNotice(**fields)  # type: ignore[arg-type]


def test_the_notice_names_the_admin_the_member_and_the_organization() -> None:
    message = deletion_request_message(_notice())
    assert message.to == "admin@example.com"
    assert message.subject == DELETION_REQUEST_SUBJECT
    assert message.text.startswith("Hello Ann,")
    assert "Jane Doe has asked to delete their XCODE account in Metro Trans." in message.text


def test_a_missing_recipient_name_falls_back_to_a_plain_greeting() -> None:
    message = deletion_request_message(_notice(recipient_first_name=""))
    assert message.text.startswith("Hello,")


@pytest.mark.parametrize(
    ("field", "value", "folded"),
    [
        ("requester_name", "Jane\r\nBcc: evil@example.com", "Jane Bcc: evil@example.com"),
        ("recipient_first_name", "Ann\nAdmin", "Ann Admin"),
        ("organization_name", "Metro\r\tTrans", "Metro Trans"),
    ],
)
def test_control_characters_in_a_name_are_folded_to_one_line(
    field: str, value: str, folded: str
) -> None:
    message = deletion_request_message(_notice(**{field: value}))
    assert "\r" not in message.text
    assert folded in message.text
    # The only newlines are the body's own blank-line separators, never from a name.
    assert message.text.count("\n") == 4


def test_a_name_cannot_inject_markup_into_the_html_part() -> None:
    message = deletion_request_message(_notice(organization_name="<script>alert(1)</script>"))
    assert message.html is not None
    assert "<script>" not in message.html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in message.html


def test_the_tags_carry_the_purpose_and_the_request_id_only() -> None:
    assert deletion_request_message(_notice()).tags == {
        "purpose": "deletion_request",
        "request_id": "req-1",
    }
    assert deletion_request_message(_notice(request_id=None)).tags == {
        "purpose": "deletion_request"
    }


def test_neither_the_message_nor_the_notice_repr_carries_the_address() -> None:
    notice = _notice(to="secret.admin@example.com")
    text = repr(deletion_request_message(notice)) + repr(notice)
    assert "secret.admin" not in text
