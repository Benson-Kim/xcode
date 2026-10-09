using Auth.Application.PettyCash;
using Auth.Domain;

namespace Auth.Application.Reports;

// What the petty cash reports read: the floats asked for, their entries the person may see (the same rule as the
// Petty cash page), and the tallies the opening balances come from. Rows cover [From, To] except for Waiting, whose
// rows are every waiting entry. Vehicles names the vehicles on those rows.
public sealed record PettyCashReportData(DateOnly From, DateOnly To, DateOnly Today, IReadOnlyList<PettyCashHolderDto> Holders,
    IReadOnlyList<PettyCashReportRow> Rows, IReadOnlyList<PettyCashTally> Tallies,
    IReadOnlyDictionary<Guid, (string Registration, string Company)> Vehicles);

public static class PettyCashReports
{
    private static readonly ReportColumnDto Manager = new("manager", "Manager", CellKinds.Text);
    private static readonly ReportColumnDto Vehicle = new("vehicle", "Vehicle", CellKinds.Vehicle);
    private static readonly ReportColumnDto What = new("what", "What", CellKinds.Text);

    // Cash raises a float; expenses and credit notes lower it, whatever their approval status.
    private static decimal Effect(PettyCashKind kind, decimal total) => kind == PettyCashKind.Cash ? total : -total;

    private static decimal Opening(PettyCashReportData data, Guid? holderId = null) => data.Tallies
        .Where(t => t.Period == PettyCashTally.Before && (holderId is null || t.HolderId == holderId))
        .Sum(t => Effect(t.Kind, t.Total));

    private static bool Spent(PettyCashReportRow row) => row.Kind != PettyCashKind.Cash;

    private static decimal Sum(IEnumerable<PettyCashReportRow> rows, PettyCashKind kind) => rows.Where(r => r.Kind == kind).Sum(r => r.Total);

    private static decimal Sum(IEnumerable<PettyCashReportRow> rows, PettyCashStatus status) =>
        rows.Where(r => Spent(r) && r.Status == status).Sum(r => r.Total);

    private static string Name(PettyCashReportData data, Guid holderId) => data.Holders.FirstOrDefault(h => h.Id == holderId)?.Name ?? "";

    private static string Registration(PettyCashReportData data, Guid? vehicleId) =>
        vehicleId is { } id && data.Vehicles.TryGetValue(id, out var vehicle) ? vehicle.Registration : "";

    private static string Describe(PettyCashReportRow row) =>
        row.Kind == PettyCashKind.Credit ? $"Credit note to {row.Payee}" : row.ItemName ?? "";

    private static IEnumerable<PettyCashReportRow> InPeriod(PettyCashReportData data) =>
        data.Rows.Where(r => r.Date >= data.From && r.Date <= data.To);

    public static ReportTable CashBook(PettyCashReportData data)
    {
        var opening = Opening(data);
        var balance = opening;
        var days = InPeriod(data).GroupBy(r => r.Date).OrderBy(g => g.Key).Select(day =>
        {
            var start = balance;
            balance += day.Sum(r => Effect(r.Kind, r.Total));
            return Tables.Row(Tables.Date(day.Key), start, Sum(day, PettyCashKind.Cash), Sum(day, PettyCashKind.Expense),
                Sum(day, PettyCashKind.Credit), balance, Sum(day, PettyCashStatus.Waiting));
        }).ToList();
        var period = InPeriod(data).ToList();
        return Tables.Make(ReportIds.PettyCash, "cashBook", "Cash book", data.From, data.To, data.Today,
            new("Closing cash balance", balance, CellKinds.Net),
            [new("Opening cash balance", opening, CellKinds.Net), new("Cash received", Sum(period, PettyCashKind.Cash), CellKinds.Money),
                new("Expenses", Sum(period, PettyCashKind.Expense), CellKinds.Money),
                new("Credit notes", Sum(period, PettyCashKind.Credit), CellKinds.Money)],
            [new("date", "Date", CellKinds.Date), new("opening", "Opening", CellKinds.Net), new("cash", "Cash received", CellKinds.Money, true),
                new("expenses", "Expenses", CellKinds.Money, true), new("credits", "Credit notes", CellKinds.Money, true),
                new("closing", "Closing", CellKinds.Net), new("waiting", "Waiting", CellKinds.Money, true)],
            days);
    }

    public static ReportTable Managers(PettyCashReportData data)
    {
        var period = InPeriod(data).ToList();
        var rows = data.Holders.OrderBy(h => h.Name, StringComparer.OrdinalIgnoreCase).Select(holder =>
        {
            var own = period.Where(r => r.HolderId == holder.Id).ToList();
            var onHand = Opening(data, holder.Id) + own.Sum(r => Effect(r.Kind, r.Total));
            return Tables.Row(holder.Name, own.Count(Spent), Sum(own, PettyCashKind.Cash), Sum(own, PettyCashKind.Credit),
                Sum(own, PettyCashStatus.Approved), Sum(own, PettyCashStatus.Waiting), Sum(own, PettyCashStatus.SentBack), onHand);
        }).ToList();
        return Tables.Make(ReportIds.PettyCash, "managers", "By manager", data.From, data.To, data.Today,
            new("Money out", period.Where(Spent).Sum(r => r.Total), CellKinds.Money),
            [new("Approved", Sum(period, PettyCashStatus.Approved), CellKinds.Money),
                new("Waiting", Sum(period, PettyCashStatus.Waiting), CellKinds.Money),
                new("Sent back", Sum(period, PettyCashStatus.SentBack), CellKinds.Money)],
            [Manager, new("entries", "Entries", CellKinds.Count, true), new("cash", "Cash received", CellKinds.Money, true),
                new("credits", "Credit notes", CellKinds.Money, true), new("approved", "Approved", CellKinds.Money, true),
                new("waiting", "Waiting", CellKinds.Money, true), new("sentBack", "Sent back", CellKinds.Money, true),
                new("onHand", "Cash on hand", CellKinds.Net, true)],
            rows);
    }

    public static ReportTable Vehicles(PettyCashReportData data)
    {
        var expenses = InPeriod(data).Where(r => r.Kind == PettyCashKind.Expense && r.VehicleId is not null).ToList();
        var total = expenses.Sum(r => r.Total);
        var rows = expenses.GroupBy(r => r.VehicleId!.Value)
            .Select(g => (Id: g.Key, Entries: g.Count(), Approved: Sum(g, PettyCashStatus.Approved),
                Open: Sum(g, PettyCashStatus.Waiting) + Sum(g, PettyCashStatus.SentBack), Total: g.Sum(r => r.Total)))
            .OrderByDescending(x => x.Total).ThenBy(x => Registration(data, x.Id), StringComparer.Ordinal)
            .ToList();
        return Tables.Make(ReportIds.PettyCash, "vehicles", "By vehicle", data.From, data.To, data.Today,
            new("Expenses", total, CellKinds.Money),
            [new("Vehicles", rows.Count, CellKinds.Count), new("Approved", rows.Sum(x => x.Approved), CellKinds.Money)],
            [Vehicle, new("company", "PSV company", CellKinds.Text), new("entries", "Entries", CellKinds.Count, true),
                new("approved", "Approved", CellKinds.Money, true), new("open", "Not yet approved", CellKinds.Money, true),
                new("total", "Total", CellKinds.Money, true), new("share", "Share", CellKinds.Percent)],
            rows.Select(x => Tables.Row(Registration(data, x.Id), data.Vehicles.TryGetValue(x.Id, out var v) ? v.Company : "", x.Entries,
                x.Approved, x.Open, x.Total, Tables.Percent(x.Total, total))));
    }

    public static ReportTable Items(PettyCashReportData data)
    {
        var expenses = InPeriod(data).Where(r => r.Kind == PettyCashKind.Expense && r.ExpenseItemId is not null).ToList();
        var total = expenses.Sum(r => r.Total);
        var rows = expenses.GroupBy(r => r.ExpenseItemId!.Value)
            .Select(g => (Category: g.First().CategoryName ?? "", Item: g.First().ItemName ?? "", Entries: g.Count(), Units: g.Sum(r => r.Units),
                Low: g.Min(r => r.UnitAmount), High: g.Max(r => r.UnitAmount), Total: g.Sum(r => r.Total)))
            .OrderByDescending(x => x.Total).ThenBy(x => x.Item, StringComparer.Ordinal)
            .ToList();
        return Tables.Make(ReportIds.PettyCash, "items", "By item", data.From, data.To, data.Today,
            new("Expenses", total, CellKinds.Money),
            [new("Items", rows.Count, CellKinds.Count), new("Entries", expenses.Count, CellKinds.Count)],
            [new("category", "Category", CellKinds.Text), new("item", "Item", CellKinds.Text), new("entries", "Entries", CellKinds.Count, true),
                new("quantity", "Qty", CellKinds.Quantity, true), new("low", "Lowest unit cost", CellKinds.Money),
                new("high", "Highest unit cost", CellKinds.Money), new("total", "Total", CellKinds.Money, true),
                new("share", "Share", CellKinds.Percent)],
            rows.Select(x => Tables.Row(x.Category, x.Item, x.Entries, x.Units, x.Low, x.High, x.Total, Tables.Percent(x.Total, total))));
    }

    // Every entry still waiting, oldest first, whatever the period.
    public static ReportTable Waiting(PettyCashReportData data)
    {
        var waiting = data.Rows.Where(r => Spent(r) && r.Status == PettyCashStatus.Waiting).OrderBy(r => r.Date).ToList();
        var oldest = waiting.Count == 0 ? 0 : data.Today.DayNumber - waiting[0].Date.DayNumber;
        return Tables.Make(ReportIds.PettyCash, "waiting", "Waiting for approval", null, null, data.Today,
            new("Waiting for approval", waiting.Sum(r => r.Total), CellKinds.Money),
            [new("Entries", waiting.Count, CellKinds.Count), new("Oldest, days", oldest, CellKinds.Count)],
            [new("date", "Date", CellKinds.Date), Manager, Vehicle, What, new("days", "Days waiting", CellKinds.Count),
                new("total", "Total amount", CellKinds.Money, true)],
            waiting.Select(r => Tables.Row(Tables.Date(r.Date), Name(data, r.HolderId), Registration(data, r.VehicleId), Describe(r),
                data.Today.DayNumber - r.Date.DayNumber, r.Total)));
    }

    public static ReportTable SentBack(PettyCashReportData data)
    {
        var sent = InPeriod(data).Where(r => Spent(r) && r.Status == PettyCashStatus.SentBack).OrderByDescending(r => r.Date).ToList();
        return Tables.Make(ReportIds.PettyCash, "sentBack", "Sent back", data.From, data.To, data.Today,
            new("Sent back", sent.Sum(r => r.Total), CellKinds.Money),
            [new("Entries", sent.Count, CellKinds.Count)],
            [new("date", "Date", CellKinds.Date), Manager, Vehicle, What, new("comment", "Comment", CellKinds.Text),
                new("total", "Total amount", CellKinds.Money, true)],
            sent.Select(r => Tables.Row(Tables.Date(r.Date), Name(data, r.HolderId), Registration(data, r.VehicleId), Describe(r),
                r.SentBackNote ?? "", r.Total)));
    }
}
