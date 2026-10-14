"""Readers of the files the exports produce, for the unit and the HTTP tests: an Excel file
opened as the zip of XML parts it is (cells by reference, shared strings, number formats, the
quote prefix, the pane, the footer, the sheet name) and a PDF's fonts through ``pypdf``."""

from __future__ import annotations

import io
import zipfile
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring as parse_xml
from pypdf import PdfReader

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_BUILT_IN_FORMATS = {"0": "General", "3": "#,##0", "4": "#,##0.00"}


class Workbook:
    def __init__(self, content: bytes) -> None:
        self.content = content
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.sheet: Element = parse_xml(archive.read("xl/worksheets/sheet1.xml"))
            self.styles: Element = parse_xml(archive.read("xl/styles.xml"))
            self.workbook: Element = parse_xml(archive.read("xl/workbook.xml"))
            self.core = archive.read("docProps/core.xml").decode()
            self.shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                strings = parse_xml(archive.read("xl/sharedStrings.xml"))
                self.shared = ["".join(si.itertext()) for si in strings.findall("m:si", NS)]

    def cell(self, reference: str) -> Element:
        cell = self.sheet.find(f".//m:c[@r='{reference}']", NS)
        assert cell is not None, reference
        return cell

    def has(self, reference: str) -> bool:
        return self.sheet.find(f".//m:c[@r='{reference}']", NS) is not None

    def text(self, reference: str) -> str:
        cell = self.cell(reference)
        value = cell.find("m:v", NS)
        if cell.get("t") == "s":
            assert value is not None and value.text is not None
            return self.shared[int(value.text)]
        if cell.get("t") == "inlineStr":
            return "".join(cell.itertext())
        raise AssertionError(f"{reference} is not a string cell")

    def number(self, reference: str) -> str:
        cell = self.cell(reference)
        assert cell.get("t") is None, reference
        value = cell.find("m:v", NS)
        assert value is not None and value.text is not None, reference
        return value.text

    def value(self, reference: str) -> str | None:
        """A cell's text or number as text, None for a blank or missing cell."""
        if not self.has(reference):
            return None
        cell = self.cell(reference)
        if cell.find("m:v", NS) is None and cell.get("t") != "inlineStr":
            return None
        return (
            self.text(reference) if cell.get("t") in ("s", "inlineStr") else self.number(reference)
        )

    def row(self, number: int, width: int) -> list[str | None]:
        return [self.value(f"{column_letter(index)}{number}") for index in range(width)]

    def xf(self, reference: str) -> Element:
        xfs = self.styles.find("m:cellXfs", NS)
        assert xfs is not None
        return list(xfs)[int(self.cell(reference).get("s", "0"))]

    def number_format(self, reference: str) -> str:
        code = self.xf(reference).get("numFmtId")
        for fmt in self.styles.iterfind(".//m:numFmt", NS):
            if fmt.get("numFmtId") == code:
                return fmt.get("formatCode", "")
        return _BUILT_IN_FORMATS.get(code or "0", code or "")

    @property
    def sheet_name(self) -> str:
        sheet = self.workbook.find(".//m:sheet", NS)
        assert sheet is not None
        return sheet.get("name", "")

    @property
    def has_formulas(self) -> bool:
        return self.sheet.find(".//m:f", NS) is not None


def column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def embedded_fonts(reader: PdfReader) -> dict[str, bool]:
    """Every font the pages reference by its base name, and whether its file is embedded."""
    embedded: dict[str, bool] = {}
    for page in reader.pages:
        for reference in page["/Resources"]["/Font"].values():
            font = reference.get_object()
            base = str(font["/BaseFont"]).split("+")[-1]
            descriptor = font.get("/FontDescriptor")
            if descriptor is None and "/DescendantFonts" in font:
                descriptor = font["/DescendantFonts"][0].get_object().get("/FontDescriptor")
            file = None if descriptor is None else descriptor.get_object().get("/FontFile2")
            embedded[base] = embedded.get(base, False) or file is not None
    return embedded
