using System.Globalization;
using Auth.Application.CentralExpenses;
using Auth.Application.PettyCash;
using Auth.Application.Revenue;

namespace Auth.Application.Reports;

// The Revenue, Central expenses and Petty cash screens as files: each reads its rows through the screen's own query,
// so the file holds what the screen lists for the same filters and access, then it is written and logged as a report
// export (reports.export).
public sealed class ScreenExports(RevenueUseCases revenue, CentralExpenseUseCases expenses, PettyCashUseCases pettyCash, ReportUseCases reports)
{
    public const string Group = "screens";
    // A file holds at most this many rows; a longer list asks for a shorter period.
    public const int MaxRows = 10_000;

    private static readonly CultureInfo Invariant = CultureInfo.InvariantCulture;

    public async Task<ReportExport> Revenue(DateOnly? weekStart, Guid? companyId, string? format, CancellationToken ct)
    {
        ReportUseCases.IsPdf(format);
        var week = await revenue.Week(weekStart, companyId, null, null, null, ct);
        var days = Enumerable.Range(0, 7).Select(i => week.WeekStart.AddDays(i)).ToList();
        var cells = week.Vehicles.SelectMany(v => v.Days).ToList();
        var table = Tables.Make(Group, "revenue", "Revenue", week.WeekStart, week.WeekThrough, week.BusinessDate,
            new("Revenue", week.TotalAmount, CellKinds.Money),
            [new("Expected", week.TotalExpected, CellKinds.Money), new("Reached", week.Percent ?? 0, CellKinds.Percent),
                new("No revenue days", cells.Count(c => c.Status == CellStatus.Reason), CellKinds.Count),
                new("Missing days", cells.Count(c => c.Status == CellStatus.Missing), CellKinds.Count)],
            [new("vehicle", "Vehicle", CellKinds.Vehicle), new("company", "PSV company", CellKinds.Text),
                .. days.Select(d => new ReportColumnDto(Tables.Date(d), d.ToString("ddd d", Invariant), CellKinds.Money, true)),
                new("total", "Week total", CellKinds.Money, true), new("expected", "Expected", CellKinds.Money, true),
                new("reached", "Reached", CellKinds.Percent)],
            week.Vehicles.Select(v => (IReadOnlyList<object?>)[v.Registration, v.CompanyName,
                .. days.Select(d => Day(v.Days.FirstOrDefault(c => c.Date == d))), v.TotalAmount, v.TotalExpected, (decimal?)v.Percent]));
        var company = companyId is null ? "All companies" : week.Companies.FirstOrDefault(c => c.Id == companyId)?.Name ?? "";
        return await reports.ExportScreen(table, company, null, format, ct);
    }

    public async Task<ReportExport> Expenses(DateOnly? from, DateOnly? to, string? source, string? q, string? format, CancellationToken ct)
    {
        ReportUseCases.IsPdf(format);
        var ledger = await expenses.AllRows(from, to, source, q, MaxRows, ct);
        TooMany(ledger.Total);
        var table = Tables.Make(Group, "expenses", "Central expenses", ledger.From, ledger.To, ledger.BusinessDate,
            new("Total", ledger.Figures.Total, CellKinds.Money),
            [new("Central", ledger.Figures.Central, CellKinds.Money), new("Petty cash", ledger.Figures.PettyCash, CellKinds.Money),
                new("Scheduled", ledger.Figures.Scheduled, CellKinds.Money)],
            [new("date", "Date", CellKinds.Date), new("vehicle", "Vehicle", CellKinds.Vehicle), new("item", "Item", CellKinds.Text),
                new("category", "Category", CellKinds.Text), new("quantity", "Qty", CellKinds.Quantity),
                new("unit", "Unit cost", CellKinds.Money), new("amount", "Total amount", CellKinds.Money, true),
                new("source", "Source", CellKinds.Text), new("recordedBy", "Recorded by", CellKinds.Text)],
            ledger.Items.Select(r => Tables.Row(Tables.Date(r.Date), r.Registration, r.ItemName, r.CategoryName ?? "", r.Units, r.UnitAmount,
                r.Total, SourceName(r.Source), r.Source == "scheduled" ? "Standing order"
                    : r.Source == "pettycash" && r.HolderName is { } holder ? $"{r.RecordedByName}, {holder}'s float" : r.RecordedByName ?? "")));
        var filters = new[] { source is null or "" ? "" : $"Source: {SourceName(source)}", Searched(q) };
        return await reports.ExportScreen(table, Join(filters), Clean(q), format, ct);
    }

    // view is "expenses" (the Expenses tab) or "cash" (Cash received: cash issued and credit notes).
    public async Task<ReportExport> PettyCash(DateOnly? from, DateOnly? to, Guid? holderId, string? view, string? status, string? q,
        string? format, CancellationToken ct)
    {
        ReportUseCases.IsPdf(format);
        var cash = view?.Trim() switch
        {
            null or "" or "expenses" => false,
            "cash" => true,
            _ => throw new ArgumentException("Choose the expenses or the cash received.")
        };
        var overview = await pettyCash.Overview(null, null, holderId, from, to, ct);
        var entries = await pettyCash.AllEntries(overview.From, overview.To, holderId, cash ? "cash,credit" : "expense", cash ? null : status, q,
            MaxRows, ct);
        TooMany(entries.Total);
        var f = overview.Figures;
        ReportFigureDto Money(string label, decimal value) => new(label, value, CellKinds.Money);
        IReadOnlyList<ReportFigureDto> figures =
            [Money("Opening balance", f.OpeningBalance), Money("Cash issued", f.CashReceived), Money("Expenses", f.Expenses),
                Money("Credit notes", f.CreditNotes)];
        var headline = Money("Cash balance", f.ClosingBalance);
        var table = cash
            ? Tables.Make(Group, "pettycashCash", "Petty cash, cash received", overview.From, overview.To, overview.BusinessDate, headline, figures,
                [new("date", "Date", CellKinds.Date), new("type", "Type", CellKinds.Text), new("manager", "Manager", CellKinds.Text),
                    new("reason", "Reason", CellKinds.Text), new("in", "In", CellKinds.Money, true), new("out", "Out", CellKinds.Money, true)],
                entries.Items.Select(e =>
                {
                    var into = e.Kind == "cash" ? e.Total : -e.Total;
                    return Tables.Row(Tables.Date(e.Date), CashType(e), e.HolderName, e.Note ?? "", into > 0 ? into : null, into < 0 ? -into : null);
                }))
            : Tables.Make(Group, "pettycashExpenses", "Petty cash, expenses", overview.From, overview.To, overview.BusinessDate, headline, figures,
                [new("date", "Date", CellKinds.Date), new("vehicle", "Vehicle", CellKinds.Vehicle), new("item", "Item", CellKinds.Text),
                    new("quantity", "Qty", CellKinds.Quantity), new("unit", "Unit cost", CellKinds.Money),
                    new("amount", "Total amount", CellKinds.Money, true), new("manager", "Manager", CellKinds.Text),
                    new("status", "Status", CellKinds.Text), new("note", "Note", CellKinds.Text)],
                entries.Items.Select(e => Tables.Row(Tables.Date(e.Date), e.Registration ?? "", e.ExpenseItemName ?? "", e.Units, e.UnitAmount,
                    e.Total, e.HolderName, StatusName(e.Status), string.Join(". ", new[] { e.Note, e.SentBackNote }.Where(n => !string.IsNullOrEmpty(n))))));
        var manager = holderId is null ? "All managers" : overview.Holders.FirstOrDefault(h => h.Id == holderId)?.Name ?? "";
        var filters = new[] { manager, cash || status is null or "" ? "" : $"Status: {StatusName(status)}", Searched(q) };
        return await reports.ExportScreen(table, Join(filters), Clean(q), format, ct);
    }

    // A day as the grid shows it: the amount, the reason there was none, or "Missing".
    private static object? Day(RevenueCellDto? cell) => cell?.Status switch
    {
        CellStatus.Amount => cell.Amount,
        CellStatus.Reason => cell.Reason,
        CellStatus.Missing => "Missing",
        _ => null
    };

    private static string CashType(PettyCashEntryDto entry) => entry.Kind == "cash"
        ? entry.Total < 0 ? "Cash taken back" : "Cash issued"
        : entry.Status == "approved" ? "Credit note" : $"Credit note, {StatusName(entry.Status).ToLowerInvariant()}";

    private static string StatusName(string? status) => status switch
    {
        "waiting" => "Waiting",
        "approved" => "Approved",
        "sentBack" => "Sent back",
        _ => status ?? ""
    };

    private static string SourceName(string source) => source.Trim() switch
    {
        "central" => "Central",
        "pettycash" => "Petty cash",
        "scheduled" => "Scheduled",
        var other => other
    };

    private static void TooMany(int total)
    {
        if (total > MaxRows)
            throw new ArgumentException($"There are {total:N0} rows to export, more than {MaxRows:N0}. Choose a shorter period or search.");
    }

    private static string? Clean(string? q) => string.IsNullOrWhiteSpace(q) ? null : q.Trim();

    private static string Searched(string? q) => Clean(q) is { } text ? $"Search: {text}" : "";

    private static string Join(IEnumerable<string> parts) => string.Join("  ·  ", parts.Where(p => p.Length > 0));
}
