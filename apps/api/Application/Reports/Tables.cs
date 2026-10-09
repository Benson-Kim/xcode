using System.Globalization;

namespace Auth.Application.Reports;

public static class Tables
{
    public static IReadOnlyList<object?> Row(params object?[] cells) => cells;

    public static string Date(DateOnly date) => date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    // part as a share of whole, 0 to 100 with one decimal; null when there is no whole to share.
    public static decimal? Percent(decimal part, decimal whole) =>
        whole == 0 ? null : decimal.Round(part / whole * 100, 1, MidpointRounding.AwayFromZero);

    public static ReportTable Make(string group, string report, string title, DateOnly? from, DateOnly? to, DateOnly today,
        ReportFigureDto headline, IReadOnlyList<ReportFigureDto> figures, IReadOnlyList<ReportColumnDto> columns,
        IEnumerable<IReadOnlyList<object?>> rows) =>
        new(group, report, title, from, to, today, headline, figures, columns, [.. rows]);

    // One page of the rows matching the search, with the footer over all of them.
    public static ReportTableDto Page(ReportTable table, string? q, int page, int pageSize)
    {
        var rows = Search(table, q);
        return new(table.Group, table.Report, table.Title, table.From, table.To, table.BusinessDate, table.Headline, table.Figures,
            table.Columns, [.. rows.Skip((page - 1) * pageSize).Take(pageSize)], page, pageSize, rows.Count, Totals(table.Columns, rows));
    }

    // Each summed column added up over the rows, null for the others.
    public static IReadOnlyList<decimal?> Totals(IReadOnlyList<ReportColumnDto> columns, IReadOnlyList<IReadOnlyList<object?>> rows) =>
        [.. columns.Select((column, i) => column.Sum
            ? rows.Sum(row => row[i] is IConvertible value and not string ? Convert.ToDecimal(value, CultureInfo.InvariantCulture) : 0m)
            : (decimal?)null)];

    // The words a cell shows, for search: text as it is, a date also as "9 Oct 2026", a number with and without
    // thousands separators.
    public static IEnumerable<string> Texts(object? cell, string kind)
    {
        switch (cell)
        {
            case null:
                yield break;
            case string text when kind == CellKinds.Date && DateOnly.TryParseExact(text, "yyyy-MM-dd", CultureInfo.InvariantCulture,
                DateTimeStyles.None, out var date):
                yield return text;
                yield return date.ToString("d MMM yyyy", CultureInfo.InvariantCulture);
                break;
            case string text:
                yield return text;
                break;
            case IFormattable number:
                var value = Convert.ToDecimal(number, CultureInfo.InvariantCulture);
                yield return value.ToString("G29", CultureInfo.InvariantCulture);
                yield return value.ToString(decimal.Truncate(value) == value ? "#,##0" : "#,##0.00", CultureInfo.InvariantCulture);
                break;
        }
    }

    // Each word must appear somewhere in the row's text.
    public static IReadOnlyList<IReadOnlyList<object?>> Search(ReportTable table, string? q)
    {
        var words = (q ?? "").Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (words.Length == 0) return table.Rows;
        return [.. table.Rows.Where(row =>
        {
            var hay = string.Join(' ', row.SelectMany((cell, index) => Texts(cell, table.Columns[index].Kind)));
            return words.All(word => hay.Contains(word, StringComparison.OrdinalIgnoreCase));
        })];
    }
}
