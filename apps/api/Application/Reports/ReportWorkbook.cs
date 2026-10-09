using System.Globalization;
using System.IO.Compression;
using System.Text;
using System.Xml;

namespace Auth.Application.Reports;

// An .xlsx of one report, written without a library and laid out like the PDF: a dark title band, the organization,
// period and filters, who exported it, the figures as tiles, then the table with a dark header row (frozen, filtered
// and repeated on every printed page), banded rows, numbers as numbers and dates as dates, and a tinted totals row.
// It prints landscape, one page wide.
public static class ReportWorkbook
{
    public const string ContentType = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

    private const string Main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
    private const string Relationships = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
    private const string PackageRelationships = "http://schemas.openxmlformats.org/package/2006/relationships";
    private const string XmlNamespace = "http://www.w3.org/XML/1998/namespace";
    private const int HeaderRow = 8;

    private static readonly DateOnly Epoch = new(1899, 12, 30);

    // Fonts, fills and number formats the styles below combine.
    private enum Font { Body, Bold, Title, Muted, HeaderWhite, TileLabel, TileValue }
    private enum Fill { None, Gray, Deep, Ink, Band, Totals, Tile }
    private enum Format { General = 0, Count = 3, Money = 164, Whole = 165, Percent = 166, Date = 167, Quantity = 168, Net = 169, NetWhole = 170 }

    private sealed class Styles
    {
        private readonly List<(Format Format, Font Font, Fill Fill, bool TopBorder, bool Right)> list = [(Format.General, Font.Body, Fill.None, false, false)];

        public int Of(Format format, Font font, Fill fill = Fill.None, bool topBorder = false, bool right = false)
        {
            var key = (format, font, fill, topBorder, right);
            var index = list.IndexOf(key);
            if (index >= 0) return index;
            list.Add(key);
            return list.Count - 1;
        }

        public string Xml() =>
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>" +
            $"<styleSheet xmlns=\"{Main}\">" +
            "<numFmts count=\"7\"><numFmt numFmtId=\"164\" formatCode=\"#,##0.00\"/><numFmt numFmtId=\"165\" formatCode=\"#,##0\"/>" +
            "<numFmt numFmtId=\"166\" formatCode=\"0.0&quot;%&quot;\"/><numFmt numFmtId=\"167\" formatCode=\"d mmm yyyy\"/>" +
            "<numFmt numFmtId=\"168\" formatCode=\"#,##0.###\"/><numFmt numFmtId=\"169\" formatCode=\"#,##0.00;[Red]-#,##0.00\"/>" +
            "<numFmt numFmtId=\"170\" formatCode=\"#,##0;[Red]-#,##0\"/></numFmts>" +
            "<fonts count=\"7\">" +
            "<font><sz val=\"10\"/><color rgb=\"FF213F4F\"/><name val=\"Calibri\"/></font>" +
            "<font><b/><sz val=\"10\"/><color rgb=\"FF06283A\"/><name val=\"Calibri\"/></font>" +
            "<font><b/><sz val=\"16\"/><color rgb=\"FFFFFFFF\"/><name val=\"Calibri\"/></font>" +
            "<font><sz val=\"10\"/><color rgb=\"FF547079\"/><name val=\"Calibri\"/></font>" +
            "<font><b/><sz val=\"10\"/><color rgb=\"FFFFFFFF\"/><name val=\"Calibri\"/></font>" +
            "<font><b/><sz val=\"8\"/><color rgb=\"FF547079\"/><name val=\"Calibri\"/></font>" +
            "<font><b/><sz val=\"13\"/><color rgb=\"FF06283A\"/><name val=\"Calibri\"/></font></fonts>" +
            "<fills count=\"7\"><fill><patternFill patternType=\"none\"/></fill><fill><patternFill patternType=\"gray125\"/></fill>" +
            Solid("FF04202F") + Solid("FF06283A") + Solid("FFF4F8F9") + Solid("FFDDF3F0") + Solid("FFE3EDEF") + "</fills>" +
            "<borders count=\"2\"><border><left/><right/><top/><bottom/><diagonal/></border>" +
            "<border><left/><right/><top style=\"medium\"><color rgb=\"FF0F766E\"/></top><bottom/><diagonal/></border></borders>" +
            "<cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs>" +
            $"<cellXfs count=\"{list.Count}\">" + string.Concat(list.Select(s =>
                $"<xf numFmtId=\"{(int)s.Format}\" fontId=\"{(int)s.Font}\" fillId=\"{(int)s.Fill}\" borderId=\"{(s.TopBorder ? 1 : 0)}\" xfId=\"0\"" +
                " applyNumberFormat=\"1\" applyFont=\"1\" applyFill=\"1\" applyBorder=\"1\" applyAlignment=\"1\">" +
                $"<alignment vertical=\"center\"{(s.Right ? " horizontal=\"right\"" : "")}/></xf>")) +
            "</cellXfs></styleSheet>";

        private static string Solid(string argb) =>
            $"<fill><patternFill patternType=\"solid\"><fgColor rgb=\"{argb}\"/><bgColor indexed=\"64\"/></patternFill></fill>";
    }

    public static byte[] Write(ReportDocument document)
    {
        var styles = new Styles();
        var sheet = Sheet(document, styles);
        var title = SheetName(document.Table.Title);
        using var stream = new MemoryStream();
        using (var zip = new ZipArchive(stream, ZipArchiveMode.Create, leaveOpen: true))
        {
            Part(zip, "[Content_Types].xml", ContentTypes);
            Part(zip, "_rels/.rels",
                $"<Relationships xmlns=\"{PackageRelationships}\"><Relationship Id=\"rId1\" Type=\"{Relationships}/officeDocument\" Target=\"xl/workbook.xml\"/></Relationships>");
            Part(zip, "xl/workbook.xml",
                $"<workbook xmlns=\"{Main}\" xmlns:r=\"{Relationships}\"><sheets><sheet name=\"{Escape(title)}\" sheetId=\"1\" r:id=\"rId1\"/></sheets>" +
                $"<definedNames><definedName name=\"_xlnm.Print_Titles\" localSheetId=\"0\">'{Escape(title.Replace("'", "''"))}'!${HeaderRow}:${HeaderRow}</definedName></definedNames></workbook>");
            Part(zip, "xl/_rels/workbook.xml.rels",
                $"<Relationships xmlns=\"{PackageRelationships}\"><Relationship Id=\"rId1\" Type=\"{Relationships}/worksheet\" Target=\"worksheets/sheet1.xml\"/>" +
                $"<Relationship Id=\"rId2\" Type=\"{Relationships}/styles\" Target=\"styles.xml\"/></Relationships>");
            Part(zip, "xl/styles.xml", styles.Xml());
            Part(zip, "xl/worksheets/sheet1.xml", sheet);
        }
        return stream.ToArray();
    }

    private static string Sheet(ReportDocument document, Styles styles)
    {
        var table = document.Table;
        var columns = table.Columns;
        var rows = document.Rows;
        var cents = columns.Select((_, k) => ReportFormat.HasCents(rows, k)).ToArray();
        var figures = new[] { table.Headline }.Concat(table.Figures).ToList();
        var span = Math.Max(columns.Count, figures.Count);
        var last = ColumnName(span - 1);
        var period = document.Period ?? $"As at {document.ExportedOn.ToString("d MMM yyyy", CultureInfo.InvariantCulture)}";
        var totals = Tables.Totals(columns, rows);
        var hasTotals = totals.Any(t => t is not null);

        var text = new StringBuilder();
        using (var xml = XmlWriter.Create(text, new XmlWriterSettings { Encoding = Encoding.UTF8 }))
        {
            xml.WriteStartDocument(true);
            xml.WriteStartElement("worksheet", Main);
            xml.WriteStartElement("sheetPr");
            xml.WriteStartElement("pageSetUpPr");
            xml.WriteAttributeString("fitToPage", "1");
            xml.WriteEndElement();
            xml.WriteEndElement();
            xml.WriteStartElement("sheetViews");
            xml.WriteStartElement("sheetView");
            xml.WriteAttributeString("showGridLines", "0");
            xml.WriteAttributeString("workbookViewId", "0");
            xml.WriteStartElement("pane");
            xml.WriteAttributeString("ySplit", HeaderRow.ToString(CultureInfo.InvariantCulture));
            xml.WriteAttributeString("topLeftCell", $"A{HeaderRow + 1}");
            xml.WriteAttributeString("activePane", "bottomLeft");
            xml.WriteAttributeString("state", "frozen");
            xml.WriteEndElement();
            xml.WriteEndElement();
            xml.WriteEndElement();
            xml.WriteStartElement("cols");
            for (var i = 0; i < span; i++)
            {
                xml.WriteStartElement("col");
                xml.WriteAttributeString("min", (i + 1).ToString(CultureInfo.InvariantCulture));
                xml.WriteAttributeString("max", (i + 1).ToString(CultureInfo.InvariantCulture));
                xml.WriteAttributeString("width", Width(document, i, cents).ToString("0.#", CultureInfo.InvariantCulture));
                xml.WriteAttributeString("customWidth", "1");
                xml.WriteEndElement();
            }
            xml.WriteEndElement();

            xml.WriteStartElement("sheetData");
            var band = styles.Of(Format.General, Font.Title, Fill.Deep);
            Row(xml, 1, 30, [.. Enumerable.Range(0, span).Select(i => ((object?)(i == 0 ? table.Title : null), band))]);
            var subtitle = string.Join("  ·  ", new[] { document.Organization, period, document.Filters }.Where(p => p.Length > 0));
            Row(xml, 2, null, [(subtitle, styles.Of(Format.General, Font.Bold))]);
            Row(xml, 3, null, [(document.Stamp, styles.Of(Format.General, Font.Muted))]);
            var tileLabel = styles.Of(Format.General, Font.TileLabel, Fill.Tile);
            Row(xml, 5, null, [.. figures.Select(f => ((object?)Label(f, document.Currency), tileLabel))]);
            Row(xml, 6, 24, [.. figures.Select(f => ((object?)f.Value, styles.Of(FigureFormat(f), Font.TileValue, Fill.Tile, right: true)))]);
            Row(xml, HeaderRow, 20, [.. columns.Select(c => ((object?)c.Label,
                styles.Of(Format.General, Font.HeaderWhite, Fill.Ink, right: ReportFormat.IsNumber(c.Kind))))]);
            for (var r = 0; r < rows.Count; r++)
            {
                var fill = r % 2 == 1 ? Fill.Band : Fill.None;
                Row(xml, HeaderRow + 1 + r, null, [.. rows[r].Select((cell, k) => (Value(cell, columns[k].Kind),
                    styles.Of(CellFormat(columns[k].Kind, cents[k]), columns[k].Kind is CellKinds.Vehicle or CellKinds.Net ? Font.Bold : Font.Body,
                        fill, right: ReportFormat.IsNumber(columns[k].Kind))))]);
            }
            if (hasTotals)
                Row(xml, HeaderRow + rows.Count + 1, 20, [.. totals.Select((total, k) => k == 0 && total is null
                    ? ((object?)$"{rows.Count.ToString("#,##0", CultureInfo.InvariantCulture)} {(rows.Count == 1 ? "row" : "rows")}",
                        styles.Of(Format.General, Font.Bold, Fill.Totals, topBorder: true))
                    : ((object?)total, styles.Of(total is null ? Format.General : CellFormat(columns[k].Kind, cents[k]), Font.Bold, Fill.Totals,
                        topBorder: true, right: ReportFormat.IsNumber(columns[k].Kind))))]);
            xml.WriteEndElement();

            if (rows.Count > 0)
            {
                xml.WriteStartElement("autoFilter");
                xml.WriteAttributeString("ref", $"A{HeaderRow}:{ColumnName(columns.Count - 1)}{HeaderRow + rows.Count}");
                xml.WriteEndElement();
            }
            xml.WriteStartElement("mergeCells");
            xml.WriteAttributeString("count", "3");
            foreach (var row in new[] { 1, 2, 3 })
            {
                xml.WriteStartElement("mergeCell");
                xml.WriteAttributeString("ref", $"A{row}:{last}{row}");
                xml.WriteEndElement();
            }
            xml.WriteEndElement();
            xml.WriteStartElement("pageMargins");
            foreach (var (name, value) in new[] { ("left", "0.4"), ("right", "0.4"), ("top", "0.5"), ("bottom", "0.5"), ("header", "0.3"), ("footer", "0.3") })
                xml.WriteAttributeString(name, value);
            xml.WriteEndElement();
            xml.WriteStartElement("pageSetup");
            xml.WriteAttributeString("paperSize", "9");
            xml.WriteAttributeString("orientation", "landscape");
            xml.WriteAttributeString("fitToWidth", "1");
            xml.WriteAttributeString("fitToHeight", "0");
            xml.WriteEndElement();
            xml.WriteStartElement("headerFooter");
            xml.WriteElementString("oddFooter", $"&L&8{FooterText($"XCODE Fleet finance | {table.Title}, {period}")}&R&8Page &P of &N");
            xml.WriteEndElement();
            xml.WriteEndElement();
            xml.WriteEndDocument();
        }
        // StringBuilder output declares UTF-16; the part is written as UTF-8.
        return text.ToString().Replace("encoding=\"utf-16\"", "encoding=\"UTF-8\"", StringComparison.Ordinal);
    }

    private static void Row(XmlWriter xml, int number, double? height, IReadOnlyList<(object? Value, int Style)> cells)
    {
        xml.WriteStartElement("row");
        xml.WriteAttributeString("r", number.ToString(CultureInfo.InvariantCulture));
        if (height is { } points)
        {
            xml.WriteAttributeString("ht", points.ToString(CultureInfo.InvariantCulture));
            xml.WriteAttributeString("customHeight", "1");
        }
        for (var i = 0; i < cells.Count; i++)
        {
            var (value, style) = cells[i];
            if (value is null && style == 0) continue;
            xml.WriteStartElement("c");
            xml.WriteAttributeString("r", $"{ColumnName(i)}{number}");
            if (style != 0) xml.WriteAttributeString("s", style.ToString(CultureInfo.InvariantCulture));
            if (value is string text)
            {
                xml.WriteAttributeString("t", "inlineStr");
                xml.WriteStartElement("is");
                xml.WriteStartElement("t");
                xml.WriteAttributeString("xml", "space", XmlNamespace, "preserve");
                xml.WriteString(Clean(text));
                xml.WriteEndElement();
                xml.WriteEndElement();
            }
            else if (value is not null)
            {
                xml.WriteElementString("v", Convert.ToDecimal(value, CultureInfo.InvariantCulture).ToString("G29", CultureInfo.InvariantCulture));
            }
            xml.WriteEndElement();
        }
        xml.WriteEndElement();
    }

    // A date cell becomes Excel's day number so it sorts and filters as a date.
    private static object? Value(object? cell, string kind) =>
        kind == CellKinds.Date && ReportFormat.Date(cell) is { } date ? date.DayNumber - Epoch.DayNumber : cell;

    private static Format CellFormat(string kind, bool cents) => kind switch
    {
        CellKinds.Money => cents ? Format.Money : Format.Whole,
        CellKinds.Net => cents ? Format.Net : Format.NetWhole,
        CellKinds.Count => Format.Count,
        CellKinds.Quantity => Format.Quantity,
        CellKinds.Percent => Format.Percent,
        CellKinds.Date => Format.Date,
        _ => Format.General
    };

    private static Format FigureFormat(ReportFigureDto figure) => figure.Kind switch
    {
        CellKinds.Percent => Format.Percent,
        CellKinds.Count => Format.Count,
        _ => decimal.Truncate(figure.Value) == figure.Value ? Format.NetWhole : Format.Net
    };

    private static string Label(ReportFigureDto figure, string currency) =>
        figure.Kind is CellKinds.Money or CellKinds.Net ? $"{figure.Label.ToUpperInvariant()} ({currency})" : figure.Label.ToUpperInvariant();

    // Wide enough for the longest thing the column shows, in characters.
    private static double Width(ReportDocument document, int index, bool[] cents)
    {
        var columns = document.Table.Columns;
        var longest = 10;
        if (index < columns.Count)
        {
            longest = Math.Max(longest, columns[index].Label.Length + 3);
            foreach (var row in document.Rows)
                longest = Math.Max(longest, ReportFormat.Cell(row[index], columns[index].Kind, cents[index]).Length + 2);
        }
        var figures = new[] { document.Table.Headline }.Concat(document.Table.Figures).ToList();
        if (index < figures.Count)
            longest = Math.Max(longest, Label(figures[index], document.Currency).Length + 2);
        return Math.Min(48, longest * 1.1);
    }

    // An ampersand starts a code in Excel's header and footer text.
    private static string FooterText(string text) => text.Replace("&", "&&", StringComparison.Ordinal);

    private static string ColumnName(int index)
    {
        var name = "";
        for (index++; index > 0; index = (index - 1) / 26) name = (char)('A' + (index - 1) % 26) + name;
        return name;
    }

    // Excel sheet names: at most 31 characters, none of : \ / ? * [ ].
    private static string SheetName(string title)
    {
        var name = new string([.. title.Where(c => c is not (':' or '\\' or '/' or '?' or '*' or '[' or ']'))]);
        return name.Length > 31 ? name[..31] : name;
    }

    private static string Escape(string text) => System.Security.SecurityElement.Escape(text) ?? "";

    // Characters XML 1.0 cannot hold are dropped.
    private static string Clean(string text) => new([.. text.Where(XmlConvert.IsXmlChar)]);

    private static void Part(ZipArchive zip, string name, string content)
    {
        var entry = zip.CreateEntry(name, CompressionLevel.Optimal);
        using var writer = new StreamWriter(entry.Open(), new UTF8Encoding(false));
        writer.Write(content);
    }

    private const string ContentTypes =
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>" +
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">" +
        "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>" +
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>" +
        "<Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>" +
        "<Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>" +
        "<Override PartName=\"/xl/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>" +
        "</Types>";
}
