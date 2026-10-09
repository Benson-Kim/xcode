using System.Globalization;
using Auth.Application.Reports;
using PdfSharp;
using PdfSharp.Drawing;
using PdfSharp.Fonts;
using PdfSharp.Pdf;

namespace Auth.Infrastructure.Reports;

// A4 landscape, as the design lays it out: the brand band with the logo, the title and period; the headline card and
// figure tiles; the table with a dark header row repeated on every page, banded rows, bars beside percentages and a
// tinted totals row; a footer with page numbers. Figtree and Fraunces are embedded, so the file reads the same anywhere.
public sealed class ReportPdf : IReportPdf
{
    private const double W = 842, H = 595, Mx = 36, Usable = W - 2 * Mx, Fs = 8.5, Rh = 17, Bottom = H - 48;

    private static readonly XColor Deep = Rgb(4, 32, 47), Deep3 = Rgb(10, 85, 96), CardA = Rgb(17, 163, 151), CardB = Rgb(18, 115, 184),
        Ink = Rgb(6, 40, 58), Body = Rgb(33, 64, 79), Slate = Rgb(84, 112, 121), Paper = Rgb(244, 248, 249), Paper2 = Rgb(227, 237, 239),
        Line = Rgb(213, 226, 229), Teal = Rgb(15, 118, 110), TealWash = Rgb(221, 243, 240), Bright = Rgb(45, 212, 191),
        Clay = Rgb(179, 38, 30), OnDeep = Rgb(194, 219, 224), LogoBlue = Rgb(106, 166, 255), LogoGold = Rgb(240, 169, 58),
        White = XColors.White;

    static ReportPdf()
    {
        if (GlobalFontSettings.FontResolver is not ReportFonts) GlobalFontSettings.FontResolver = new ReportFonts();
    }

    public byte[] Write(ReportDocument document)
    {
        var pdf = new PdfDocument();
        pdf.Info.Title = document.Table.Title;
        pdf.Info.Author = document.Organization;
        pdf.Info.Creator = "XCODE Fleet finance";
        new Renderer(pdf, document).Render();
        using var stream = new MemoryStream();
        pdf.Save(stream, false);
        return stream.ToArray();
    }

    private static XColor Rgb(int r, int g, int b) => XColor.FromArgb(r, g, b);
    private static XFont Font(double size, bool bold = false) => new(ReportFonts.Figtree, size, bold ? XFontStyleEx.Bold : XFontStyleEx.Regular);
    private static XSolidBrush Brush(XColor color) => new(color);

    private sealed class Renderer(PdfDocument pdf, ReportDocument d)
    {
        private readonly List<PdfPage> pages = [];
        private XGraphics g = null!;
        private double y;
        private double[] widths = [], xs = [];
        private bool[] numeric = [], bar = [], bold = [], cents = [];

        private string Period => d.Period ?? $"As at {d.ExportedOn.ToString("d MMM yyyy", CultureInfo.InvariantCulture)}";

        public void Render()
        {
            var columns = d.Table.Columns;
            var hasVehicle = columns.Any(c => c.Kind == CellKinds.Vehicle);
            numeric = [.. columns.Select(c => ReportFormat.IsNumber(c.Kind))];
            bar = [.. columns.Select(c => c.Kind == CellKinds.Percent)];
            bold = [.. columns.Select((c, k) => c.Kind is CellKinds.Net or CellKinds.Vehicle || (k == 0 && !hasVehicle))];
            cents = [.. columns.Select((_, k) => ReportFormat.HasCents(d.Rows, k))];
            var body = d.Rows.Select(row => columns.Select((c, k) => ReportFormat.Cell(row[k], c.Kind, cents[k])).ToArray()).ToList();
            var totals = Tables.Totals(columns, d.Rows);
            string[]? foot = totals.Any(t => t is not null)
                ? [.. columns.Select((c, k) => k == 0 && totals[0] is null
                    ? $"{d.Rows.Count.ToString("#,##0", CultureInfo.InvariantCulture)} {(d.Rows.Count == 1 ? "row" : "rows")}"
                    : totals[k] is { } total ? ReportFormat.Cell(total, c.Kind, cents[k]) : "")]
                : null;

            NewPage();
            Measure(body, foot);
            FirstHeader();
            Heads();
            for (var i = 0; i < body.Count; i++)
            {
                if (y + Rh > Bottom) Continue();
                if (i % 2 == 1) g.DrawRectangle(Brush(Paper), Mx, y, Usable, Rh);
                Cells(body[i], d.Rows[i], y, false);
                y += Rh;
            }
            if (body.Count == 0)
            {
                Left("Nothing to show for these dates.", Font(Fs), Slate, Mx + 6, y + 12);
                y += Rh;
            }
            if (foot is not null)
            {
                if (y + Rh + 2 > Bottom) Continue();
                g.DrawRectangle(Brush(TealWash), Mx, y, Usable, Rh + 2);
                g.DrawRectangle(Brush(Teal), Mx, y, Usable, 1.2);
                Cells(foot, null, y + 1.5, true);
                y += Rh + 2;
            }
            g.DrawLine(new XPen(Line, 0.6), Mx, y, W - Mx, y);
            g.Dispose();
            Footers();
        }

        private void NewPage()
        {
            var page = pdf.AddPage();
            page.Size = PageSize.A4;
            page.Orientation = PageOrientation.Landscape;
            pages.Add(page);
            g = XGraphics.FromPdfPage(page);
        }

        private void Continue()
        {
            g.Dispose();
            NewPage();
            g.DrawRectangle(new XLinearGradientBrush(new XPoint(0, 0), new XPoint(W, 0), Deep, Deep3), 0, 0, W, 34);
            g.DrawRectangle(Brush(Bright), 0, 34, W, 2);
            Logo(Mx, 26, 18, 11);
            Right(Fit($"{d.Table.Title}  |  {Period}", Usable - 140, Font(10, true)), Font(10, true), White, W - Mx, 21);
            y = 36 + 16;
            Heads();
        }

        // Column widths from what the cells hold, as the design sizes them: text columns share what is left over.
        private void Measure(IReadOnlyList<string[]> body, string[]? foot)
        {
            var columns = d.Table.Columns;
            var headFont = Font(7.2, true);
            widths = [.. columns.Select((c, k) =>
            {
                var w = Width(c.Label.ToUpperInvariant(), headFont);
                var cell = Font(Fs, bold[k]);
                foreach (var row in body) w = Math.Max(w, Width(row[k], cell) + (bar[k] ? 40 : 0));
                if (foot is not null) w = Math.Max(w, Width(foot[k], Font(Fs, true)));
                return Math.Min(numeric[k] ? 999 : 200, w) + 14;
            })];
            var total = widths.Sum();
            var flexible = widths.Where((_, k) => !numeric[k]).Sum();
            if (total > Usable)
                widths = [.. widths.Select(w => w * Usable / total)];
            else if (flexible > 0)
                widths = [.. widths.Select((w, k) => numeric[k] ? w : w + (Usable - total) * w / flexible)];
            xs = new double[widths.Length + 1];
            xs[0] = Mx;
            for (var k = 0; k < widths.Length; k++) xs[k + 1] = xs[k] + widths[k];
        }

        private void FirstHeader()
        {
            g.DrawRectangle(new XLinearGradientBrush(new XPoint(0, 0), new XPoint(W, 0), Deep, Deep3), 0, 0, W, 66);
            g.DrawRectangle(Brush(Bright), 0, 66, W, 2);
            Logo(Mx, 48, 30, 17);
            Right(d.Table.Title, Font(16, true), White, W - Mx, 31);
            Right(Period, Font(10), OnDeep, W - Mx, 47);

            var stamp = d.Stamp;
            var lineFont = Font(8.5, true);
            var line = d.Filters.Length > 0 ? $"{d.Organization}  ·  {d.Filters}" : d.Organization;
            Left(Fit(line, Usable - Width(stamp, Font(8.5)) - 20, lineFont), lineFont, Ink, Mx, 85);
            Right(stamp, Font(8.5), Slate, W - Mx, 85);

            const double top = 98;
            var heroLabel = d.Table.Headline.Label.ToUpperInvariant();
            var heroValue = ReportFormat.Figure(d.Table.Headline, d.Currency);
            var heroWidth = Math.Max(150, Math.Max(Width(heroValue, Font(17, true)) + 30, Spaced(heroLabel, Font(6.8, true), 0.5) + 30));
            g.DrawRoundedRectangle(new XLinearGradientBrush(new XPoint(Mx, 0), new XPoint(Mx + heroWidth, 0), CardA, CardB),
                Mx, top, heroWidth, 46, 16, 16);
            Spaced(Fit(heroLabel, heroWidth - 24, Font(6.8, true)), Font(6.8, true), White, Mx + 13, top + 15, 0.5);
            Left(heroValue, Font(17, true), White, Mx + 13, top + 35);

            var x = Mx + heroWidth + 8;
            var tiles = d.Table.Figures
                .Select(f => (Label: f.Label.ToUpperInvariant(), Value: ReportFormat.Figure(f, d.Currency)))
                .Select(f => (f.Label, f.Value,
                    Width: Math.Max(Spaced(f.Label, Font(6.8, true), 0.5) + 6, Width(f.Value, Font(12.5, true))) + 26))
                .ToList();
            var grow = tiles.Count == 0 ? 0 : Math.Max(0, (W - Mx - x - tiles.Sum(t => t.Width) - 8 * (tiles.Count - 1)) / tiles.Count);
            foreach (var tile in tiles)
            {
                var w = tile.Width + grow;
                if (x + w > W - Mx + 0.5) break;
                g.DrawRoundedRectangle(Brush(Paper), x, top, w, 46, 16, 16);
                Spaced(tile.Label, Font(6.8, true), Slate, x + 13, top + 15, 0.5);
                Left(tile.Value, Font(12.5, true), Ink, x + 13, top + 34);
                x += w + 8;
            }
            y = top + 46 + 16;
        }

        private void Heads()
        {
            g.DrawRoundedRectangle(Brush(Ink), Mx, y, Usable, 20, 10, 10);
            g.DrawRectangle(Brush(Ink), Mx, y + 12, Usable, 8);
            var font = Font(7.2, true);
            for (var k = 0; k < widths.Length; k++)
            {
                var text = Fit(d.Table.Columns[k].Label.ToUpperInvariant(), widths[k] - 10, font);
                if (numeric[k]) Right(text, font, White, xs[k + 1] - 6, y + 13);
                else Left(text, font, White, xs[k] + 6, y + 13);
            }
            y += 20;
        }

        private void Cells(string[] texts, IReadOnlyList<object?>? raw, double top, bool totals)
        {
            var columns = d.Table.Columns;
            var baseline = top + 11.6;
            for (var k = 0; k < texts.Length; k++)
            {
                var strong = totals || bold[k];
                var font = Font(Fs, strong);
                var value = raw is null ? null : ReportFormat.Number(raw[k]);
                var text = Fit(texts[k], widths[k] - 12 - (bar[k] && !totals ? 38 : 0), font);
                if (text.Length == 0) continue;
                var color = value < 0 && columns[k].Kind is CellKinds.Money or CellKinds.Net ? Clay : strong ? Ink : Body;
                if (bar[k] && !totals && value is { } share)
                {
                    var barTop = top + Rh - 6.4 - 4.2;
                    g.DrawRoundedRectangle(Brush(Paper2), xs[k] + 7, barTop, 30, 4.2, 4.2, 4.2);
                    if (share > 0)
                        g.DrawRoundedRectangle(Brush(share >= 100 ? Teal : CardA), xs[k] + 7, barTop,
                            Math.Max(4.2, 30 * (double)Math.Min(100, share) / 100), 4.2, 4.2, 4.2);
                }
                if (numeric[k]) Right(text, font, color, xs[k + 1] - 6, baseline);
                else Left(text, font, color, xs[k] + 6, baseline);
            }
        }

        // The mark (one blue stroke, two gold) and the wordmark; yBase is the bottom of the mark's box.
        private void Logo(double x, double yBase, double size, double fontSize)
        {
            var k = size / 40;
            XPoint P(double a, double b) => new(x + a * k, yBase - b * k);
            var blue = new XPen(LogoBlue, 6.5 * k) { LineCap = XLineCap.Round };
            var gold = new XPen(LogoGold, 6.5 * k) { LineCap = XLineCap.Round };
            g.DrawLine(blue, P(9, 31), P(31, 9));
            g.DrawLine(gold, P(31, 31), P(24.5, 24.5));
            g.DrawLine(gold, P(15.5, 15.5), P(9, 9));
            var mark = new XFont(ReportFonts.Fraunces, fontSize, XFontStyleEx.Bold);
            Spaced("XCODE", mark, White, x + size + 7, yBase - size * 0.5 + (fontSize > 12 ? 1 : fontSize * 0.36), fontSize * 0.14);
            if (fontSize > 12)
                Spaced("FLEET FINANCE", Font(6, true), OnDeep, x + size + 7.5, yBase - size * 0.5 + 11, 0.9);
        }

        private void Footers()
        {
            var note = $"XCODE Fleet finance  |  {d.Table.Title}, {Period}";
            for (var i = 0; i < pages.Count; i++)
            {
                using var footer = XGraphics.FromPdfPage(pages[i], XGraphicsPdfPageOptions.Append);
                g = footer;
                g.DrawLine(new XPen(Line, 0.6), Mx, H - 36, W - Mx, H - 36);
                Left(Fit(note, Usable - 80, Font(7.5)), Font(7.5), Slate, Mx, H - 24);
                Right($"Page {i + 1} of {pages.Count}", Font(7.5, true), Ink, W - Mx, H - 24);
            }
        }

        private double Width(string text, XFont font) => text.Length == 0 ? 0 : g.MeasureString(text, font).Width;

        private string Fit(string text, double width, XFont font)
        {
            if (Width(text, font) <= width) return text;
            while (text.Length > 1 && Width(text + "...", font) > width) text = text[..^1];
            return text + "...";
        }

        private void Left(string text, XFont font, XColor color, double x, double baseline) =>
            g.DrawString(text, font, Brush(color), x, baseline, XStringFormats.BaseLineLeft);

        private void Right(string text, XFont font, XColor color, double right, double baseline) =>
            Left(text, font, color, right - Width(text, font), baseline);

        private double Spaced(string text, XFont font, double spacing) =>
            text.Sum(c => Width(c.ToString(), font) + spacing) - (text.Length > 0 ? spacing : 0);

        // Letter-spaced capitals, drawn one letter at a time.
        private void Spaced(string text, XFont font, XColor color, double x, double baseline, double spacing)
        {
            foreach (var c in text)
            {
                var letter = c.ToString();
                Left(letter, font, color, x, baseline);
                x += Width(letter, font) + spacing;
            }
        }
    }
}

// Figtree for text and Fraunces for the wordmark, read from the API's own assembly (Assets/Fonts, SIL Open Font License).
internal sealed class ReportFonts : IFontResolver
{
    public const string Figtree = "Figtree";
    public const string Fraunces = "Fraunces";

    public FontResolverInfo ResolveTypeface(string familyName, bool bold, bool italic) =>
        string.Equals(familyName, Fraunces, StringComparison.OrdinalIgnoreCase)
            ? new FontResolverInfo("Fraunces-Bold")
            : new FontResolverInfo(bold ? "Figtree-Bold" : "Figtree-Regular");

    public byte[] GetFont(string faceName)
    {
        using var stream = typeof(ReportFonts).Assembly.GetManifestResourceStream($"fonts/{faceName}.ttf")
            ?? throw new InvalidOperationException($"The font {faceName} is not embedded in the API.");
        using var bytes = new MemoryStream();
        stream.CopyTo(bytes);
        return bytes.ToArray();
    }
}
