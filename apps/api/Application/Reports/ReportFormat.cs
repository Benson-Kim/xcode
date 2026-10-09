using System.Globalization;

namespace Auth.Application.Reports;

// How an exported file writes cells and figures, the same in Excel and PDF: dates as "9 Oct 2026", amounts with
// thousands separators and cents only where the column has any, percentages with one decimal.
public static class ReportFormat
{
    private static readonly CultureInfo Invariant = CultureInfo.InvariantCulture;

    public static bool IsNumber(string kind) =>
        kind is CellKinds.Money or CellKinds.Net or CellKinds.Count or CellKinds.Quantity or CellKinds.Percent;

    public static decimal? Number(object? cell) =>
        cell is IConvertible value and not string ? Convert.ToDecimal(value, Invariant) : null;

    public static DateOnly? Date(object? cell) =>
        cell is string text && DateOnly.TryParseExact(text, "yyyy-MM-dd", Invariant, DateTimeStyles.None, out var date) ? date : null;

    public static bool HasCents(IEnumerable<IReadOnlyList<object?>> rows, int column) =>
        rows.Any(row => Number(row[column]) is { } value && decimal.Truncate(value) != value);

    public static string Amount(decimal value, bool cents) =>
        (value < 0 ? "-" : "") + Math.Abs(value).ToString(cents ? "#,##0.00" : "#,##0", Invariant);

    public static string Cell(object? cell, string kind, bool cents)
    {
        if (cell is null) return "";
        if (Number(cell) is not { } value)
            return kind == CellKinds.Date && Date(cell) is { } date ? date.ToString("d MMM yyyy", Invariant) : cell.ToString() ?? "";
        return kind switch
        {
            CellKinds.Percent => value.ToString("0.0", Invariant) + "%",
            CellKinds.Quantity => value.ToString("#,##0.###", Invariant),
            CellKinds.Count => value.ToString("#,##0", Invariant),
            _ => Amount(value, cents)
        };
    }

    public static string Figure(ReportFigureDto figure, string currency) => figure.Kind switch
    {
        CellKinds.Percent => figure.Value.ToString("0.0", Invariant) + "%",
        CellKinds.Count => figure.Value.ToString("#,##0", Invariant),
        _ => $"{currency} {Amount(figure.Value, decimal.Truncate(figure.Value) != figure.Value)}"
    };
}
