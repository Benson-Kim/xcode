"""``file_response``: the whole file as the body with its content type, and the name twice in
``Content-Disposition`` as ASP.NET Core wrote it (``docs/06-http-contract.md`` 2.13.5): quoted
with every character outside printable ASCII, the quote and the backslash replaced by ``_``,
and percent-encoded UTF-8 after ``filename*``."""

from __future__ import annotations

from xcode_api.domain.reports import PDF_CONTENT_TYPE, XLSX_CONTENT_TYPE, ExportFile
from xcode_api.http.responses import file_response


def test_an_ascii_name_is_quoted_and_percent_encoded() -> None:
    response = file_response(
        ExportFile(b"PK...", XLSX_CONTENT_TYPE, "Net by vehicle 1 Oct 2026 to 9 Oct 2026.xlsx")
    )
    assert response.status_code == 200
    assert response.body == b"PK..."
    assert response.headers["content-type"] == XLSX_CONTENT_TYPE
    assert response.headers["content-disposition"] == (
        'attachment; filename="Net by vehicle 1 Oct 2026 to 9 Oct 2026.xlsx"; '
        "filename*=UTF-8''Net%20by%20vehicle%201%20Oct%202026%20to%209%20Oct%202026.xlsx"
    )


def test_a_name_with_other_letters_keeps_them_only_in_the_encoded_form() -> None:
    response = file_response(ExportFile(b"%PDF", PDF_CONTENT_TYPE, 'Résumé "Q\\A".pdf'))
    assert response.headers["content-type"] == PDF_CONTENT_TYPE
    assert response.headers["content-disposition"] == (
        'attachment; filename="R_sum_ _Q_A_.pdf"; '
        "filename*=UTF-8''R%C3%A9sum%C3%A9%20%22Q%5CA%22.pdf"
    )
