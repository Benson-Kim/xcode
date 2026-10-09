using Auth.Application.Setup;
using Auth.Domain.Setup;

namespace Auth.Application.Reports;

// What the fleet reports read, already cut to the vehicles the person can see. Postings cover [From, To] unless a
// report says otherwise; To is never after the business date.
public sealed record FleetReportData(DateOnly From, DateOnly To, DateOnly Today, IReadOnlyList<ReportVehicle> Vehicles,
    IReadOnlyList<ReportRevenueDay> Revenue, IReadOnlyList<FleetPosting> Postings);

// One vehicle over its days in a period, counted the way the vehicle report counts them, so the fleet reports and the
// vehicle report always agree.
public sealed record VehicleFigures(decimal Revenue, decimal Target, decimal Repairs, decimal Charges, decimal Loans, decimal Saved,
    int SavingRuns, int Captured, int NoRevenue, IReadOnlyList<DateOnly> Missing)
{
    public decimal MoneyOut => Repairs + Charges + Loans;
    public decimal Net => Revenue - MoneyOut;

    public static readonly VehicleFigures None = new(0, 0, 0, 0, 0, 0, 0, 0, 0, []);

    public static VehicleFigures Of(ReportVehicle vehicle, DateOnly from, DateOnly to, DateOnly today, IEnumerable<ReportRevenueDay> revenue,
        IEnumerable<FleetPosting> postings)
    {
        if (vehicle.Window(from, to, today) is not { } window) return None;
        var (first, last) = window;
        var records = revenue.Where(r => r.VehicleId == vehicle.Id && r.Date >= first && r.Date <= last).ToList();
        var captured = records.Select(r => r.Date).ToHashSet();
        // Every active day before today is expected; today only once it is captured. A day away has no target.
        var target = 0m;
        var missing = new List<DateOnly>();
        for (var day = first; day <= last; day = day.AddDays(1))
        {
            if (day < today || captured.Contains(day)) target += vehicle.Vehicle.TargetOn(day) / 7m;
            if (day < today && vehicle.Vehicle.ActiveOn(day) && !captured.Contains(day)) missing.Add(day);
        }
        var own = postings.Where(p => p.VehicleId == vehicle.Id && p.Date >= first && p.Date <= last).ToList();
        decimal Bucket(ExpenseBucket bucket) => own.Where(p => p.Kind == RecurringKind.Cost && p.Bucket == bucket).Sum(p => p.Amount);
        var savings = own.Where(p => p.Kind == RecurringKind.Savings).ToList();
        return new(records.Sum(r => r.Amount ?? 0m), decimal.Round(target, 2), Bucket(ExpenseBucket.RepairsAndMaintenance),
            Bucket(ExpenseBucket.RecurringCharges), Bucket(ExpenseBucket.LoanRepayments), savings.Sum(p => p.Amount), savings.Count,
            records.Count(r => r.Amount is not null), records.Count(r => r.Amount is null), missing);
    }
}

public static class FleetReports
{
    private static readonly ReportColumnDto Vehicle = new("vehicle", "Vehicle", CellKinds.Vehicle);
    private static readonly ReportColumnDto Company = new("company", "PSV company", CellKinds.Text);

    private static IEnumerable<(ReportVehicle Vehicle, VehicleFigures Figures)> PerVehicle(FleetReportData data)
    {
        var revenue = data.Revenue.ToLookup(r => r.VehicleId);
        var postings = data.Postings.ToLookup(p => p.VehicleId);
        return data.Vehicles
            .Where(v => v.Window(data.From, data.To, data.Today) is not null)
            .Select(v => (v, VehicleFigures.Of(v, data.From, data.To, data.Today, revenue[v.Id], postings[v.Id])));
    }

    public static ReportTable Net(FleetReportData data)
    {
        var rows = PerVehicle(data).OrderByDescending(x => x.Figures.Net).ThenBy(x => x.Vehicle.Registration, StringComparer.Ordinal).ToList();
        decimal Sum(Func<VehicleFigures, decimal> pick) => rows.Sum(x => pick(x.Figures));
        return Tables.Make(ReportIds.Fleet, "net", "Net by vehicle", data.From, data.To, data.Today,
            new("Net", Sum(f => f.Net), CellKinds.Net),
            [new("Revenue", Sum(f => f.Revenue), CellKinds.Money), new("Money out", Sum(f => f.MoneyOut), CellKinds.Money),
                new("Saved", Sum(f => f.Saved), CellKinds.Money)],
            [Vehicle, Company, new("revenue", "Revenue", CellKinds.Money, true), new("repairs", "Repairs and maintenance", CellKinds.Money, true),
                new("charges", "Recurring charges", CellKinds.Money, true), new("loans", "Loan repayments", CellKinds.Money, true),
                new("moneyOut", "Money out", CellKinds.Money, true), new("net", "Net", CellKinds.Net, true), new("saved", "Saved", CellKinds.Money, true)],
            rows.Select(x => Tables.Row(x.Vehicle.Registration, x.Vehicle.CompanyName, x.Figures.Revenue, x.Figures.Repairs, x.Figures.Charges,
                x.Figures.Loans, x.Figures.MoneyOut, x.Figures.Net, x.Figures.Saved)));
    }

    public static ReportTable Target(FleetReportData data)
    {
        var rows = PerVehicle(data)
            .Select(x => (x.Vehicle, x.Figures, Reached: Tables.Percent(x.Figures.Revenue, x.Figures.Target)))
            .OrderBy(x => x.Reached ?? decimal.MaxValue).ThenBy(x => x.Vehicle.Registration, StringComparer.Ordinal)
            .ToList();
        var (revenue, target) = (rows.Sum(x => x.Figures.Revenue), rows.Sum(x => x.Figures.Target));
        return Tables.Make(ReportIds.Fleet, "target", "Revenue against target", data.From, data.To, data.Today,
            new("Revenue", revenue, CellKinds.Money),
            [new("Target", target, CellKinds.Money), new("Reached", Tables.Percent(revenue, target) ?? 0, CellKinds.Percent),
                new("Missing days", rows.Sum(x => x.Figures.Missing.Count), CellKinds.Count)],
            [Vehicle, Company, new("captured", "Days captured", CellKinds.Count, true), new("noRevenue", "No revenue days", CellKinds.Count, true),
                new("missing", "Missing days", CellKinds.Count, true), new("revenue", "Revenue", CellKinds.Money, true),
                new("target", "Target", CellKinds.Money, true), new("reached", "Reached", CellKinds.Percent),
                new("against", "Against target", CellKinds.Net, true)],
            rows.Select(x => Tables.Row(x.Vehicle.Registration, x.Vehicle.CompanyName, x.Figures.Captured, x.Figures.NoRevenue,
                x.Figures.Missing.Count, x.Figures.Revenue, x.Figures.Target, x.Reached, x.Figures.Revenue - x.Figures.Target)));
    }

    public static ReportTable Gaps(FleetReportData data)
    {
        var gaps = PerVehicle(data)
            .SelectMany(x => x.Figures.Missing.Select(day => (x.Vehicle, Day: day)))
            .OrderBy(x => x.Day).ThenBy(x => x.Vehicle.Registration, StringComparer.Ordinal)
            .ToList();
        return Tables.Make(ReportIds.Fleet, "gaps", "Capture gaps", data.From, data.To, data.Today,
            new("Missing days", gaps.Count, CellKinds.Count),
            [new("Vehicles with gaps", gaps.Select(x => x.Vehicle.Id).Distinct().Count(), CellKinds.Count)],
            [Vehicle, Company, new("date", "Date", CellKinds.Date), new("missing", "What is missing", CellKinds.Text)],
            gaps.Select(x => Tables.Row(x.Vehicle.Registration, x.Vehicle.CompanyName, Tables.Date(x.Day), "Revenue not captured")));
    }

    // Postings here run from the earliest join date to To, so the balance counts every run since each saving began;
    // Saved and Runs count only the period.
    public static ReportTable Savings(FleetReportData data)
    {
        var savings = data.Postings.Where(p => p.Kind == RecurringKind.Savings).ToLookup(p => p.VehicleId);
        var rows = data.Vehicles
            .Select(v =>
            {
                var all = v.Window(DateOnly.MinValue, data.To, data.Today) is { } window
                    ? savings[v.Id].Where(p => p.Date >= window.First && p.Date <= window.Last).ToList()
                    : [];
                var inPeriod = all.Where(p => p.Date >= data.From).ToList();
                return (Vehicle: v, Runs: inPeriod.Count, Saved: inPeriod.Sum(p => p.Amount), Balance: all.Sum(p => p.Amount));
            })
            .Where(x => x.Balance != 0 || x.Runs > 0)
            .OrderByDescending(x => x.Balance).ThenBy(x => x.Vehicle.Registration, StringComparer.Ordinal)
            .ToList();
        return Tables.Make(ReportIds.Fleet, "savings", "Savings", data.From, data.To, data.Today,
            new("Saved", rows.Sum(x => x.Saved), CellKinds.Money),
            [new("Balance", rows.Sum(x => x.Balance), CellKinds.Money), new("Runs", rows.Sum(x => x.Runs), CellKinds.Count)],
            [Vehicle, Company, new("runs", "Runs", CellKinds.Count, true), new("saved", "Saved", CellKinds.Money, true),
                new("balance", "Balance", CellKinds.Money, true)],
            rows.Select(x => Tables.Row(x.Vehicle.Registration, x.Vehicle.CompanyName, x.Runs, x.Saved, x.Balance)));
    }

    // Each vehicle since it joined, up to the business date: what went in, and the net contribution against it.
    public static ReportTable Investment(FleetReportData data, IReadOnlyDictionary<Guid, decimal> invested)
    {
        var revenue = data.Revenue.ToLookup(r => r.VehicleId);
        var postings = data.Postings.ToLookup(p => p.VehicleId);
        var rows = data.Vehicles
            .Where(v => v.Vehicle.JoinedOn <= data.Today)
            .Select(v =>
            {
                var net = VehicleFigures.Of(v, v.Vehicle.JoinedOn, data.Today, data.Today, revenue[v.Id], postings[v.Id]).Net;
                var put = invested.GetValueOrDefault(v.Id);
                return (Vehicle: v, Invested: put, Net: net, Recovered: Tables.Percent(net, put));
            })
            .OrderByDescending(x => x.Recovered ?? decimal.MinValue).ThenBy(x => x.Vehicle.Registration, StringComparer.Ordinal)
            .ToList();
        var (total, net) = (rows.Sum(x => x.Invested), rows.Sum(x => x.Net));
        return Tables.Make(ReportIds.Fleet, "investment", "Investment", null, null, data.Today,
            new("Invested in vehicles", total, CellKinds.Money),
            [new("Net since joining", net, CellKinds.Net), new("Recovered", Tables.Percent(net, total) ?? 0, CellKinds.Percent)],
            [Vehicle, Company, new("joined", "Joined", CellKinds.Date), new("invested", "Invested", CellKinds.Money, true),
                new("net", "Net since joining", CellKinds.Net, true), new("recovered", "Recovered", CellKinds.Percent)],
            rows.Select(x => Tables.Row(x.Vehicle.Registration, x.Vehicle.CompanyName, Tables.Date(x.Vehicle.Vehicle.JoinedOn), x.Invested,
                x.Net, x.Recovered)));
    }

    // Every cost by item, from all three sources. A central row shared by several vehicles counts its share of the
    // quantity bought at the true unit cost, so prices are not distorted by the split.
    public static ReportTable MoneyOut(FleetReportData data, IReadOnlyDictionary<Guid, string> itemNames)
    {
        var visible = data.Vehicles.Select(v => v.Id).ToHashSet();
        var costs = data.Postings
            .Where(p => p.Kind == RecurringKind.Cost && visible.Contains(p.VehicleId) && p.Date >= data.From && p.Date <= data.To)
            .ToList();
        var total = costs.Sum(p => p.Amount);
        var rows = costs
            .GroupBy(p => p.ExpenseItemId is { } id ? (Key: id.ToString(), Name: Name(p, itemNames)) : (Key: "schedule:" + p.Name, Name: p.Name))
            .Select(g =>
            {
                var first = g.First();
                var units = g.Select(UnitCost).ToList();
                return (Category: first.CategoryName ?? ExpenseBuckets.Label(first.Bucket ?? ExpenseBucket.RecurringCharges), Item: g.Key.Name,
                    Entries: g.Count(), Quantity: decimal.Round(g.Sum(Quantity), 3), Low: units.Min(), High: units.Max(), Amount: g.Sum(p => p.Amount));
            })
            .OrderByDescending(x => x.Amount).ThenBy(x => x.Item, StringComparer.Ordinal)
            .ToList();
        decimal Bucket(ExpenseBucket bucket) => costs.Where(p => p.Bucket == bucket).Sum(p => p.Amount);
        return Tables.Make(ReportIds.Fleet, "moneyOut", "Money out", data.From, data.To, data.Today,
            new("Money out", total, CellKinds.Money),
            [new("Repairs and maintenance", Bucket(ExpenseBucket.RepairsAndMaintenance), CellKinds.Money),
                new("Recurring charges", Bucket(ExpenseBucket.RecurringCharges), CellKinds.Money),
                new("Loan repayments", Bucket(ExpenseBucket.LoanRepayments), CellKinds.Money)],
            [new("category", "Category", CellKinds.Text), new("item", "Item", CellKinds.Text), new("entries", "Entries", CellKinds.Count, true),
                new("quantity", "Qty", CellKinds.Quantity, true), new("low", "Lowest unit cost", CellKinds.Money),
                new("high", "Highest unit cost", CellKinds.Money), new("amount", "Amount", CellKinds.Money, true),
                new("share", "Share", CellKinds.Percent)],
            rows.Select(x => Tables.Row(x.Category, x.Item, x.Entries, x.Quantity, x.Low, x.High, x.Amount, Tables.Percent(x.Amount, total))));
    }

    private static string Name(FleetPosting posting, IReadOnlyDictionary<Guid, string> itemNames) =>
        posting.Source == PostingSource.Scheduled && posting.ExpenseItemId is { } id && itemNames.TryGetValue(id, out var name) ? name : posting.Name;

    private static bool Shared(FleetPosting posting) => posting.Group is { Size: > 1, Total: not 0 };

    private static decimal Quantity(FleetPosting posting) =>
        Shared(posting) ? posting.Group!.Units * posting.Amount / posting.Group.Total : posting.Units;

    private static decimal UnitCost(FleetPosting posting) => Shared(posting) ? posting.Group!.UnitAmount : posting.UnitAmount;
}
