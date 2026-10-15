"""The keyed digest of codes and refresh tokens: HMAC-SHA256, UTF-8, upper-case hex."""

from __future__ import annotations

from xcode_api.security.codes import new_code
from xcode_api.security.digests import KeyedDigester, keyed_digest
from xcode_api.security.refresh_tokens import new_refresh_token

# RFC 4231 test case 2: key "Jefe", data "what do ya want for nothing?".
RFC_4231_CASE_2 = "5BDCC146BF60754E6A042426089575C75A003F089D2739839DEC58B964EC3843"


def test_fixed_hmac_vector() -> None:
    assert keyed_digest("what do ya want for nothing?", "Jefe") == RFC_4231_CASE_2


def test_digester_uses_the_signing_key() -> None:
    digester = KeyedDigester("Jefe")
    assert digester.digest("what do ya want for nothing?") == RFC_4231_CASE_2
    assert "Jefe" not in repr(digester)
    assert KeyedDigester("another key of 32 bytes or more!!").digest("x") != digester.digest("x")


def test_codes_are_six_zero_padded_digits() -> None:
    codes = {new_code() for _ in range(2000)}
    assert all(len(code) == 6 and code.isascii() and code.isdigit() for code in codes)
    assert len(codes) > 1900


def test_refresh_tokens_are_48_bytes_of_standard_base64() -> None:
    import base64

    token = new_refresh_token()
    assert len(token) == 64
    assert len(base64.b64decode(token, validate=True)) == 48
    assert new_refresh_token() != token
