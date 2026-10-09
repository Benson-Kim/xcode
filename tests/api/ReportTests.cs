using System.IO.Compression;
using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application.PettyCash;
using Auth.Application.Reports;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;
using Xunit;
using static Auth.Tests.RevenueTestData;

namespace Auth.Tests;

// The business date is Tuesday 31 March 2026. KDA 482M and KDB 111A run for Report Fleet, KDC 222C for Other Fleet;
// all three joined on 1 February. KDA 482M's weekly target rose from 7,000 to 14,000 on 16 March.
public sealed class ReportTests : IDisposable
{
    private static readonly DateOnly Today = new(2026, 3, 31);
    private static readonly DateOnly Joined = new(2026, 2, 1);
    private static readonly DateOnly Start = new(2026, 1, 1);
    private const string March = "from=2026-03-01&to=2026-03-31";
    private readonly AuthFactory app = new();

    private sealed record World(HttpClient Owner, Guid A, Guid B, Guid C, Guid CompanyA, Guid Tyres, Guid Parking);

    private async Task<World> Arrange()
    {
        await app.SeedDemo();
        await SetBusinessDate(app, Today);
        var companyA = await Company(app, "Report Fleet");
        var companyB = await Company(app, "Other Fleet");
        var a = await Vehicle(app, companyA, "KDA 482M", Joined, 7000m, revision: (14000m, new DateOnly(2026, 3, 16)));
        var b = await Vehicle(app, companyA, "KDB 111A", Joined);
        var c = await Vehicle(app, companyB, "KDC 222C", Joined);
        var owner = await app.SignIn(Owner);
        return new(owner, a, b, c, companyA, await ExpenseItemTestData.Id(owner, "Tyres"), await ExpenseItemTestData.Id(owner, "Parking"));
    }

    [Fact]
    public async Task NetByVehicleAgreesWithEachVehicleReport()
    {
        var w = await Arrange();
        await Save(o => new RecurringItem(o, Cost("Service", Monthly(10), ExpenseBucket.RepairsAndMaintenance, [new(w.A, 2000m), new(w.B, 1000m)])));
        await Save(o => new RecurringItem(o, Cost("Parking", Weekly(1), ExpenseBucket.RecurringCharges, [new(w.A, 300m)], w.Parking)));
        await Save(o => new RecurringItem(o, Cost("Loan repayment", new RecurringSchedule(RecurrenceFrequency.Monthly, null, lastDay: true),
            ExpenseBucket.LoanRepayments, [new(w.A, 10000m)])));
        await Save(o => new RecurringItem(o, Saving("Owner savings", [new(w.A, 1000m)])));
        await Records(app, w.A, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 1500m, skip: [new DateOnly(2026, 3, 10)]);
        await Garage(w.A, new DateOnly(2026, 3, 10));
        await Records(app, w.B, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 2000m);
        await Records(app, w.C, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 1000m);
        await Central(w.Owner, w.Tyres, new DateOnly(2026, 3, 12), 1, 6000m, (w.A, 6000m));
        await Central(w.Owner, w.Tyres, new DateOnly(2026, 3, 14), 2, 450m, (w.A, 450m), (w.B, 450m));
        await ScopeToCompany(app, Clerk, w.CompanyA);
        await Grant(app, Clerk, "pettycash.spend");
        using var clerk = await app.SignIn(Clerk);
        var approved = await PettyExpense(clerk, w.B, w.Tyres, new DateOnly(2026, 3, 20), 700m);
        await PettyExpense(clerk, w.B, w.Tyres, new DateOnly(2026, 3, 21), 800m);
        (await w.Owner.PostAsJsonAsync($"/setup/pettycash/entries/{approved.Id}/approve", new { version = approved.Version })).EnsureSuccessStatusCode();

        var net = await Report(w.Owner, "fleet/net", March);
        Assert.Equal(["vehicle", "company", "revenue", "repairs", "charges", "loans", "moneyOut", "net", "saved"], net.Columns.Select(c => c.Key));
        // Highest net first: KDB 111A 60,000 - 2,150; KDC 222C 30,000; KDA 482M 23,550.
        Assert.Equal(["KDB 111A", "KDC 222C", "KDA 482M"], net.Rows.Select(r => Text(r[0])));
        foreach (var row in net.Rows)
        {
            var id = Text(row[0]) switch { "KDA 482M" => w.A, "KDB 111A" => w.B, _ => w.C };
            var report = (await w.Owner.GetFromJsonAsync<VehicleReport>($"/setup/vehicles/{id}/report?from=2026-03-01&through=2026-03-31"))!;
            Assert.Equal((report.MoneyIn, report.Repairs, report.Charges, report.Loans, report.MoneyOut, report.Net, report.Savings),
                (Number(row[2]), Number(row[3]), Number(row[4]), Number(row[5]), Number(row[6]), Number(row[7]), Number(row[8])));
        }
        // KDA 482M: 29 days at 1,500; service 2,000, tyres 6,000 + 450; Mondays 2, 9, 16, 23, 30 at 300; the loan; 4 Fridays.
        var kda = net.Rows.Single(r => Text(r[0]) == "KDA 482M");
        Assert.Equal((43500m, 8450m, 1500m, 10000m, 19950m, 23550m, 4000m),
            (Number(kda[2]), Number(kda[3]), Number(kda[4]), Number(kda[5]), Number(kda[6]), Number(kda[7]), Number(kda[8])));
        // KDB 111A: the approved petty cash counts, the waiting one does not.
        Assert.Equal(1000m + 450m + 700m, Number(net.Rows.Single(r => Text(r[0]) == "KDB 111A")[3]));
        Assert.Equal(("Net", net.Rows.Sum(r => Number(r[7])), "net"), (net.Headline.Label, net.Headline.Value, net.Headline.Kind));
        Assert.Equal([("Revenue", net.Rows.Sum(r => Number(r[2]))), ("Money out", net.Rows.Sum(r => Number(r[6]))), ("Saved", 4000m)],
            net.Figures.Select(f => (f.Label, f.Value)));
        Assert.Equal((new DateOnly(2026, 3, 1), Today, 1, ReportIds.PageSize, 3), (net.From, net.To, net.PageNumber, net.PageSize, net.Total));
        Assert.Equal([null, null, net.Rows.Sum(r => Number(r[2])), 8450m + 2150m, 1500m, 10000m, net.Rows.Sum(r => Number(r[6])),
            net.Headline.Value, 4000m], net.Totals);
    }

    [Fact]
    public async Task TargetAndGapsCountEachVehiclesCapturedNoRevenueAndMissingDays()
    {
        var w = await Arrange();
        await Records(app, w.A, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 1500m, skip: [new DateOnly(2026, 3, 10)]);
        await Garage(w.A, new DateOnly(2026, 3, 10));
        await Records(app, w.B, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 2000m, skip: [new DateOnly(2026, 3, 5), new DateOnly(2026, 3, 6)]);
        await Records(app, w.C, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 31), 500m);

        var target = await Report(w.Owner, "fleet/target", March);
        var rows = target.Rows.ToDictionary(r => Text(r[0]));
        // Today counts toward the target only once it is captured, and is never missing.
        Assert.Equal((29, 1, 0, 43500m), (Count(rows["KDA 482M"][2]), Count(rows["KDA 482M"][3]), Count(rows["KDA 482M"][4]), Number(rows["KDA 482M"][5])));
        Assert.Equal((28, 0, 2), (Count(rows["KDB 111A"][2]), Count(rows["KDB 111A"][3]), Count(rows["KDB 111A"][4])));
        Assert.Equal((31, 0), (Count(rows["KDC 222C"][2]), Count(rows["KDC 222C"][4])));
        foreach (var (registration, id) in new[] { ("KDA 482M", w.A), ("KDB 111A", w.B), ("KDC 222C", w.C) })
        {
            var report = (await w.Owner.GetFromJsonAsync<VehicleReport>($"/setup/vehicles/{id}/report?from=2026-03-01&through=2026-03-31"))!;
            Assert.Equal(report.Target, Number(rows[registration][6]));
            Assert.Equal(decimal.Round(report.MoneyIn / report.Target * 100, 1, MidpointRounding.AwayFromZero), Number(rows[registration][7]));
            Assert.Equal(report.MoneyIn - report.Target, Number(rows[registration][8]));
        }
        // Lowest share of the target first.
        Assert.Equal(target.Rows.Select(r => Number(r[7])).Order(), target.Rows.Select(r => Number(r[7])));
        Assert.Equal(("Missing days", 2m), (target.Figures[2].Label, target.Figures[2].Value));

        var gaps = await Report(w.Owner, "fleet/gaps", March);
        Assert.Equal([("KDB 111A", "Report Fleet", "2026-03-05", "Revenue not captured"), ("KDB 111A", "Report Fleet", "2026-03-06", "Revenue not captured")],
            gaps.Rows.Select(r => (Text(r[0]), Text(r[1]), Text(r[2]), Text(r[3]))));
        Assert.Equal((2m, 1m), (gaps.Headline.Value, gaps.Figures.Single().Value));
    }

    // A purchase shared by three vehicles counts its share of the quantity at the true unit cost, so the lowest and
    // highest unit cost are what was paid, not each vehicle's share.
    [Fact]
    public async Task MoneyOutGroupsEverySourceByItemAtTheTrueUnitCost()
    {
        var w = await Arrange();
        await Central(w.Owner, w.Tyres, new DateOnly(2026, 3, 20), 3, 1000m, (w.A, 1500m), (w.B, 1000m), (w.C, 500m));
        await Save(o => new RecurringItem(o, Cost("Stage parking", Weekly(1), ExpenseBucket.RecurringCharges, [new(w.A, 300m)], w.Parking)));
        await Save(o => new RecurringItem(o, Saving("Owner savings", [new(w.A, 1000m)])));
        await ScopeToCompany(app, Clerk, w.CompanyA);
        await Grant(app, Clerk, "pettycash.spend");
        using var clerk = await app.SignIn(Clerk);
        var spent = await PettyExpense(clerk, w.B, w.Tyres, new DateOnly(2026, 3, 18), 800m);
        (await w.Owner.PostAsJsonAsync($"/setup/pettycash/entries/{spent.Id}/approve", new { version = spent.Version })).EnsureSuccessStatusCode();

        var money = await Report(w.Owner, "fleet/moneyOut", "from=2026-03-16&to=2026-03-31");
        Assert.Equal(["category", "item", "entries", "quantity", "low", "high", "amount", "share"], money.Columns.Select(c => c.Key));
        Assert.Equal(
            [("Garage and repairs", "Tyres", 4, 4m, 800m, 1000m, 3800m, 80.9m), ("Charges", "Parking", 3, 3m, 300m, 300m, 900m, 19.1m)],
            money.Rows.Select(r => (Text(r[0]), Text(r[1]), Count(r[2]), Number(r[3]), Number(r[4]), Number(r[5]), Number(r[6]), Number(r[7]))));
        Assert.Equal(("Money out", 4700m), (money.Headline.Label, money.Headline.Value));
        Assert.Equal([3800m, 900m, 0m], money.Figures.Select(f => f.Value));
    }

    [Fact]
    public async Task SavingsCountRunsInThePeriodAndTheBalanceSinceEachSavingBegan()
    {
        var w = await Arrange();
        await Save(o => new RecurringItem(o, Saving("Owner savings", [new(w.A, 1000m)])));

        var savings = await Report(w.Owner, "fleet/savings", "from=2026-03-16&to=2026-03-31");
        // Fridays since KDA 482M joined: 6, 13, 20 and 27 February, 6, 13, 20 and 27 March; two in the period.
        var row = Assert.Single(savings.Rows);
        Assert.Equal(("KDA 482M", 2, 2000m, 8000m), (Text(row[0]), Count(row[2]), Number(row[3]), Number(row[4])));
        Assert.Equal((2000m, 8000m), (savings.Headline.Value, savings.Figures[0].Value));
    }

    [Fact]
    public async Task InvestmentShowsWhatCameBackSinceJoiningAndNeedsItsPermission()
    {
        var w = await Arrange();
        await Records(app, w.A, Joined, new DateOnly(2026, 3, 30), 1000m);
        (await w.Owner.PostAsJsonAsync($"/setup/vehicles/{w.A}/investment", new { date = Joined, description = "Purchase", amount = 100000m }))
            .EnsureSuccessStatusCode();

        var investment = await Report(w.Owner, "fleet/investment", "");
        Assert.Equal((null, null), (investment.From, investment.To));
        var row = investment.Rows.Single(r => Text(r[0]) == "KDA 482M");
        var returned = (await w.Owner.GetFromJsonAsync<InvestmentDto>($"/setup/vehicles/{w.A}/investment"))!.Returned!.Value;
        Assert.Equal(("2026-02-01", 100000m, returned, decimal.Round(returned / 1000m, 1)), (Text(row[2]), Number(row[3]), Number(row[4]), Number(row[5])));
        // Nothing invested in KDB 111A: nothing to recover against.
        var unfunded = investment.Rows.Single(r => Text(r[0]) == "KDB 111A");
        Assert.Equal(0m, Number(unfunded[3]));
        Assert.True(unfunded[5] is null || ((JsonElement)unfunded[5]!).ValueKind == JsonValueKind.Null);

        await Grant(app, Clerk, "reports.view");
        using var clerk = await app.SignIn(Clerk);
        var access = (await clerk.GetFromJsonAsync<ReportsAccessDto>("/setup/reports"))!;
        Assert.DoesNotContain("investment", access.Fleet);
        Assert.Equal(HttpStatusCode.Forbidden, (await clerk.GetAsync("/setup/reports/fleet/investment")).StatusCode);
    }

    [Fact]
    public async Task PettyCashReportsFollowTheFloatsAPersonMaySee()
    {
        var w = await Arrange();
        await ScopeToCompany(app, Clerk, w.CompanyA);
        await Grant(app, Clerk, "pettycash.spend");
        await Grant(app, Clerk, "reports.view");
        Guid clerkId = default;
        await app.WithDb(async db => clerkId = (await db.Users.SingleAsync(x => x.Email == Clerk)).Id);
        using var clerk = await app.SignIn(Clerk);
        await Petty(w.Owner, new { kind = "cash", date = new DateOnly(2026, 3, 1), holderId = clerkId, unitAmount = 1000m });
        await Petty(w.Owner, new { kind = "cash", date = new DateOnly(2026, 3, 2), holderId = clerkId, unitAmount = 10000m });
        var tyres = await PettyExpense(clerk, w.A, w.Tyres, new DateOnly(2026, 3, 3), 1500m, units: 2);
        (await w.Owner.PostAsJsonAsync($"/setup/pettycash/entries/{tyres.Id}/approve", new { version = tyres.Version })).EnsureSuccessStatusCode();
        await PettyExpense(clerk, w.B, w.Tyres, new DateOnly(2026, 3, 20), 700m);
        var credit = await Petty(clerk, new { kind = "credit", date = new DateOnly(2026, 3, 21), unitAmount = 200m, payee = "Kamau Motors", note = "Paid for parts" });
        (await w.Owner.PostAsJsonAsync($"/setup/pettycash/entries/{credit.Id}/send-back", new { version = credit.Version, comment = "Receipt missing" }))
            .EnsureSuccessStatusCode();
        const string period = "from=2026-03-02&to=2026-03-31";

        var book = await Report(w.Owner, "pettycash/cashBook", $"{period}&holderId={clerkId}");
        Assert.Equal(
            [("2026-03-02", 1000m, 10000m, 0m, 0m, 11000m, 0m), ("2026-03-03", 11000m, 0m, 3000m, 0m, 8000m, 0m),
                ("2026-03-20", 8000m, 0m, 700m, 0m, 7300m, 700m), ("2026-03-21", 7300m, 0m, 0m, 200m, 7100m, 0m)],
            book.Rows.Select(r => (Text(r[0]), Number(r[1]), Number(r[2]), Number(r[3]), Number(r[4]), Number(r[5]), Number(r[6]))));
        Assert.Equal((7100m, 1000m), (book.Headline.Value, book.Figures[0].Value));

        var managers = await Report(w.Owner, "pettycash/managers", period);
        var mine = managers.Rows.Single(r => Text(r[0]) == "Wanjiru Kamau");
        Assert.Equal((3, 10000m, 200m, 3000m, 700m, 200m, 7100m),
            (Count(mine[1]), Number(mine[2]), Number(mine[3]), Number(mine[4]), Number(mine[5]), Number(mine[6]), Number(mine[7])));

        var vehicles = await Report(w.Owner, "pettycash/vehicles", period);
        Assert.Equal([("KDA 482M", "Report Fleet", 3000m, 0m), ("KDB 111A", "Report Fleet", 0m, 700m)],
            vehicles.Rows.Select(r => (Text(r[0]), Text(r[1]), Number(r[3]), Number(r[4]))));

        var items = await Report(w.Owner, "pettycash/items", period);
        var row = Assert.Single(items.Rows);
        Assert.Equal(("Tyres", 2, 3m, 700m, 1500m, 3700m, 100m),
            (Text(row[1]), Count(row[2]), Number(row[3]), Number(row[4]), Number(row[5]), Number(row[6]), Number(row[7])));

        var waiting = await Report(w.Owner, "pettycash/waiting", "");
        var open = Assert.Single(waiting.Rows);
        Assert.Equal(("2026-03-20", "Wanjiru Kamau", "KDB 111A", "Tyres", 11, 700m),
            (Text(open[0]), Text(open[1]), Text(open[2]), Text(open[3]), Count(open[4]), Number(open[5])));

        var sent = await Report(w.Owner, "pettycash/sentBack", period);
        var back = Assert.Single(sent.Rows);
        Assert.Equal(("Credit note to Kamau Motors", "Receipt missing", 200m), (Text(back[3]), Text(back[4]), Number(back[5])));

        // Without "View every float" a person sees only their own float.
        var access = (await clerk.GetFromJsonAsync<ReportsAccessDto>("/setup/reports"))!;
        Assert.Equal([clerkId], access.Holders.Select(h => h.Id));
        Assert.Equal(ReportIds.PettyCashReports, access.PettyCash);
        Guid ownerId = default;
        await app.WithDb(async db => ownerId = (await db.Users.SingleAsync(x => x.Email == Owner)).Id);
        Assert.Equal(HttpStatusCode.NotFound, (await clerk.GetAsync($"/setup/reports/pettycash/cashBook?{period}&holderId={ownerId}")).StatusCode);
        Assert.Single((await Report(clerk, "pettycash/managers", period)).Rows);

        // Reports without any petty cash right show no petty cash reports.
        using var admin = await app.SignIn(Admin);
        Assert.Empty((await admin.GetFromJsonAsync<ReportsAccessDto>("/setup/reports"))!.PettyCash);
        Assert.Equal(HttpStatusCode.Forbidden, (await admin.GetAsync($"/setup/reports/pettycash/cashBook?{period}")).StatusCode);
    }

    [Fact]
    public async Task ReportsCoverOnlyTheVehiclesAPersonCanSee()
    {
        var w = await Arrange();
        await Records(app, w.C, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 1000m);
        await Central(w.Owner, w.Tyres, new DateOnly(2026, 3, 12), 1, 6000m, (w.C, 6000m));
        await Central(w.Owner, w.Tyres, new DateOnly(2026, 3, 12), 1, 900m, (w.A, 900m));
        await ScopeToCompany(app, Clerk, w.CompanyA);
        await Grant(app, Clerk, "reports.view");
        using var clerk = await app.SignIn(Clerk);

        Assert.Equal(["KDA 482M", "KDB 111A"], (await Report(clerk, "fleet/net", March)).Rows.Select(r => Text(r[0])).Order());
        Assert.Equal(900m, (await Report(clerk, "fleet/moneyOut", March)).Headline.Value);
        Assert.Equal(6900m, (await Report(w.Owner, "fleet/moneyOut", March)).Headline.Value);
        Assert.Equal(["KDC 222C"], (await Report(w.Owner, "fleet/net", $"{March}&companyId={(await CompanyOf(w.C))}")).Rows.Select(r => Text(r[0])));
    }

    [Fact]
    public async Task ExportIsAnExcelFileOfTheRowsShownAndIsWrittenToTheChangeLog()
    {
        var w = await Arrange();
        await Records(app, w.A, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 1500m);
        await Records(app, w.B, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 2000m);

        using var response = await w.Owner.GetAsync($"/setup/reports/fleet/net/export?{March}&q=kda&format=xlsx");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(ReportWorkbook.ContentType, response.Content.Headers.ContentType!.MediaType);
        using var zip = new ZipArchive(new MemoryStream(await response.Content.ReadAsByteArrayAsync()));
        Assert.Equal(["[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/_rels/workbook.xml.rels", "xl/styles.xml", "xl/worksheets/sheet1.xml"],
            zip.Entries.Select(e => e.FullName));
        var sheet = System.Xml.Linq.XDocument.Load(zip.GetEntry("xl/worksheets/sheet1.xml")!.Open());
        System.Xml.Linq.XNamespace main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
        string? CellText(string reference) => sheet.Descendants(main + "c").SingleOrDefault(c => (string?)c.Attribute("r") == reference) is { } cell
            ? (string?)cell.Element(main + "v") ?? string.Concat(cell.Descendants(main + "t").Select(t => t.Value))
            : null;
        // The title band, who and what it covers, the figures as tiles, then the table: header, rows, totals.
        Assert.Equal("Net by vehicle", CellText("A1"));
        Assert.Equal("XCODE  ·  1 Mar 2026 to 31 Mar 2026  ·  Search: kda", CellText("A2"));
        Assert.Equal("Exported 31 Mar 2026 by Antony Maina", CellText("A3"));
        Assert.Equal(["NET (KES)", "REVENUE (KES)", "MONEY OUT (KES)", "SAVED (KES)"], new[] { "A5", "B5", "C5", "D5" }.Select(CellText));
        // The figures cover the whole report, as on screen; the table holds only the rows the search left.
        Assert.Equal(["105000", "105000", "0", "0"], new[] { "A6", "B6", "C6", "D6" }.Select(CellText));
        Assert.Equal(["Vehicle", "PSV company", "Revenue"], new[] { "A8", "B8", "C8" }.Select(CellText));
        Assert.Equal(("KDA 482M", "45000"), (CellText("A9"), CellText("C9")));
        Assert.Equal(("1 row", "45000"), (CellText("A10"), CellText("C10")));
        Assert.Null(CellText("A11"));
        Assert.Equal(("frozen", "A8:I9"), ((string?)sheet.Descendants(main + "pane").Single().Attribute("state"),
            (string?)sheet.Descendants(main + "autoFilter").Single().Attribute("ref")));
        Assert.Equal(("landscape", "1"), ((string?)sheet.Descendants(main + "pageSetup").Single().Attribute("orientation"),
            (string?)sheet.Descendants(main + "pageSetup").Single().Attribute("fitToWidth")));

        string? reason = null;
        await app.WithDb(async db => reason = await db.Set<OrganizationSettingsVersion>().IgnoreQueryFilters()
            .Where(v => v.Section == "reports").Select(v => v.Reason).SingleAsync());
        Assert.Equal("Exported Net by vehicle for 1 Mar 2026 to 31 Mar 2026, searched for \"kda\" to Excel", reason);

        Assert.Equal(HttpStatusCode.BadRequest, (await w.Owner.GetAsync($"/setup/reports/fleet/net/export?{March}&format=csv")).StatusCode);
        await Deny(app, Owner, "reports.export");
        Assert.Equal(HttpStatusCode.Forbidden, (await w.Owner.GetAsync($"/setup/reports/fleet/net/export?{March}")).StatusCode);
        Assert.False((await w.Owner.GetFromJsonAsync<ReportsAccessDto>("/setup/reports"))!.CanExport);
    }

    // A4 landscape with Figtree and Fraunces embedded; a long table runs onto more pages, each with its header row.
    [Fact]
    public async Task ExportIsAPresentablePdfAcrossAsManyPagesAsTheRowsNeed()
    {
        var w = await Arrange();
        await Records(app, w.C, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 1), 1000m);

        using var response = await w.Owner.GetAsync($"/setup/reports/fleet/gaps/export?{March}&format=pdf");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("application/pdf", response.Content.Headers.ContentType!.MediaType);
        var bytes = await response.Content.ReadAsByteArrayAsync();
        Assert.Equal("%PDF", System.Text.Encoding.ASCII.GetString(bytes, 0, 4));
        using var pdf = PdfSharp.Pdf.IO.PdfReader.Open(new MemoryStream(bytes), PdfSharp.Pdf.IO.PdfDocumentOpenMode.Import);
        // 30 + 30 + 29 missing days, about 22 rows to a page.
        Assert.InRange(pdf.PageCount, 3, 6);
        Assert.All(pdf.Pages.Cast<PdfSharp.Pdf.PdfPage>(), page => Assert.Equal((842, 595), ((int)page.Width.Point, (int)page.Height.Point)));
        Assert.Equal(("Capture gaps", "XCODE"), (pdf.Info.Title, pdf.Info.Author));
        var raw = System.Text.Encoding.Latin1.GetString(bytes);
        Assert.Contains("Figtree", raw);
        Assert.Contains("Fraunces", raw);
        Assert.Contains("/FontFile2", raw);

        string? reason = null;
        await app.WithDb(async db => reason = await db.Set<OrganizationSettingsVersion>().IgnoreQueryFilters()
            .Where(v => v.Section == "reports").Select(v => v.Reason).SingleAsync());
        Assert.Equal("Exported Capture gaps for 1 Mar 2026 to 31 Mar 2026 to PDF", reason);

        // An empty report is still a page with the header and a note.
        using var empty = await w.Owner.GetAsync("/setup/reports/fleet/gaps/export?from=2026-03-31&to=2026-03-31&format=pdf&q=nothing");
        using var one = PdfSharp.Pdf.IO.PdfReader.Open(new MemoryStream(await empty.Content.ReadAsByteArrayAsync()), PdfSharp.Pdf.IO.PdfDocumentOpenMode.Import);
        Assert.Equal(1, one.PageCount);
    }

    // The server searches and pages: a page holds only its rows, and the count and footer cover every row that matches.
    [Fact]
    public async Task ReportsArePagedAndSearchedByTheServer()
    {
        var w = await Arrange();
        DateOnly[] skipped = [.. Enumerable.Range(1, 7).Select(day => new DateOnly(2026, 3, day))];
        await Records(app, w.A, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 1000m, skip: skipped[..4]);
        await Records(app, w.B, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 1000m, skip: skipped);
        await Records(app, w.C, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 1000m);

        var all = await Report(w.Owner, "fleet/gaps", March);
        Assert.Equal((11, 11), (all.Total, all.Rows.Count));
        var pages = new List<(string, string)>();
        for (var page = 1; page <= 4; page++)
        {
            var part = await Report(w.Owner, "fleet/gaps", $"{March}&page={page}&pageSize=3");
            Assert.Equal((page, 3, 11, 11m), (part.PageNumber, part.PageSize, part.Total, part.Headline.Value));
            Assert.Equal(page < 4 ? 3 : 2, part.Rows.Count);
            pages.AddRange(part.Rows.Select(r => (Text(r[0]), Text(r[2]))));
        }
        Assert.Equal(all.Rows.Select(r => (Text(r[0]), Text(r[2]))), pages);
        Assert.Empty((await Report(w.Owner, "fleet/gaps", $"{March}&page=5&pageSize=3")).Rows);

        // Every word must appear in the row; "mar" matches only the date as it reads, 7 Mar 2026.
        var searched = await Report(w.Owner, "fleet/gaps", $"{March}&q=7%20mar&pageSize=3");
        Assert.Equal((1, "KDB 111A", "2026-03-07"), (searched.Total, Text(Assert.Single(searched.Rows)[0]), Text(searched.Rows[0][2])));
        Assert.Equal(7, (await Report(w.Owner, "fleet/gaps", $"{March}&q=kdb")).Total);
        Assert.Equal(11m, searched.Headline.Value);

        // The footer adds up every matching row, not just the page.
        var target = await Report(w.Owner, "fleet/target", $"{March}&q=KD&pageSize=1");
        Assert.Equal((3, 1), (target.Total, target.Rows.Count));
        Assert.Equal((26m + 23m + 30m, 4m + 7m, 26000m + 23000m + 30000m), (target.Totals[2], target.Totals[4], target.Totals[5]));
        Assert.Null(target.Totals[7]);

        async Task Refused(string query, string detail)
        {
            using var response = await w.Owner.GetAsync($"/setup/reports/fleet/gaps?{March}&{query}");
            Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
            Assert.Equal(detail, (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString());
        }
        await Refused("pageSize=101", "Page must be 1–100000 and page size 1–100.");
        await Refused("page=0", "Page must be 1–100000 and page size 1–100.");
        await Refused($"q={new string('x', 201)}", "Search for 200 characters or fewer.");
    }

    [Fact]
    public async Task PeriodsAreCheckedAndUnknownReportsAreNotFound()
    {
        var w = await Arrange();
        async Task Refused(string path, string detail)
        {
            using var response = await w.Owner.GetAsync(path);
            Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
            Assert.Equal(detail, (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString());
        }
        await Refused("/setup/reports/fleet/net", "Choose the first and last day.");
        await Refused("/setup/reports/fleet/net?from=2026-03-31&to=2026-03-01", "The first date cannot be after the last date.");
        await Refused("/setup/reports/fleet/net?from=2025-03-01&to=2026-03-31", "Choose at most 367 days.");
        await Refused("/setup/reports/fleet/net?from=2026-04-01&to=2026-04-07", "Choose a period that starts on or before today.");
        Assert.Equal(HttpStatusCode.NotFound, (await w.Owner.GetAsync($"/setup/reports/fleet/cashBook?{March}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await w.Owner.GetAsync($"/setup/reports/other/net/export?{March}")).StatusCode);

        // A week that runs past today stops at today.
        var week = await Report(w.Owner, "fleet/net", "from=2026-03-30&to=2026-04-05");
        Assert.Equal((new DateOnly(2026, 3, 30), Today), (week.From, week.To));

        var access = (await w.Owner.GetFromJsonAsync<ReportsAccessDto>("/setup/reports"))!;
        Assert.Equal((Today, true), (access.BusinessDate, access.CanExport));
        Assert.Equal(ReportIds.FleetReports, access.Fleet);
        using var clerk = await app.SignIn(Clerk);
        Assert.Equal(HttpStatusCode.Forbidden, (await clerk.GetAsync("/setup/reports")).StatusCode);
    }

    [Fact]
    public void SearchKeepsRowsHoldingEveryWordAndAPageKeepsTheFooterOfAllMatches()
    {
        var table = Tables.Make("fleet", "gaps", "Capture gaps", Today, Today, Today, new("Missing days", 2, CellKinds.Count), [],
            [new("vehicle", "Vehicle", CellKinds.Vehicle), new("date", "Date", CellKinds.Date), new("amount", "Amount", CellKinds.Money, true)],
            [Tables.Row("KDA 482M", "2026-03-05", 12500m), Tables.Row("KDB 111A", "2026-03-06", 300.5m)]);
        Assert.Equal(["KDA 482M"], Tables.Search(table, "kda 5 mar").Select(r => r[0]));
        Assert.Equal(["KDA 482M"], Tables.Search(table, "12,500").Select(r => r[0]));
        Assert.Equal(["KDB 111A"], Tables.Search(table, "300.50").Select(r => r[0]));
        Assert.Equal(2, Tables.Search(table, "  ").Count);
        Assert.Equal([null, null, 12800.5m], Tables.Totals(table.Columns, table.Rows));
        Assert.Equal(((decimal?)33.3m, (decimal?)null), (Tables.Percent(1, 3), Tables.Percent(1, 0)));

        var many = Tables.Make("fleet", "gaps", "Capture gaps", Today, Today, Today, new("Missing days", 0, CellKinds.Count), [],
            [new("n", "N", CellKinds.Count, true)], Enumerable.Range(1, 120).Select(i => Tables.Row(i)));
        var third = Tables.Page(many, null, 3, 50);
        Assert.Equal((3, 50, 120, 20, 101m, 7260m), (third.PageNumber, third.PageSize, third.Total, third.Rows.Count, (decimal)(int)third.Rows[0][0]!,
            third.Totals[0]));
        var twos = Tables.Page(many, "2", 1, 10);
        // 2, 12, 20 to 29, 32 to 92 by tens, 102, 112 and 120.
        Assert.Equal((22, 10, 2m), (twos.Total, twos.Rows.Count, (decimal)(int)twos.Rows[0][0]!));
    }

    private static RecurringSchedule Weekly(int day) => new(RecurrenceFrequency.Weekly, day);
    private static RecurringSchedule Monthly(int day) => new(RecurrenceFrequency.Monthly, day);

    private static RecurringDefinition Cost(string name, RecurringSchedule schedule, ExpenseBucket bucket, IReadOnlyList<VehicleShare> shares,
        Guid? item = null) =>
        new(name, RecurringKind.Cost, shares.Sum(s => s.Amount), schedule, Start, null, shares, item, bucket);

    // Every Friday.
    private static RecurringDefinition Saving(string name, IReadOnlyList<VehicleShare> shares) =>
        new(name, RecurringKind.Savings, shares.Sum(s => s.Amount), Weekly(5), Start, null, shares);

    private Task Save(Func<Guid, RecurringItem> build) => app.WithDb(async db =>
    {
        db.Provisioning = true;
        db.Add(build((await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id));
        await db.SaveChangesAsync();
    });

    private Task Garage(Guid vehicle, DateOnly date) => app.WithDb(async db =>
    {
        db.Provisioning = true;
        var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
        var actor = (await db.Users.SingleAsync(x => x.Email == Owner)).Id;
        db.Add(new RevenueRecord(organizationId, vehicle, date, new RevenueEntry(null, RevenueNoEarningsReason.Garage, null),
            app.Clock.UtcNow.ToUniversalTime(), actor));
        await db.SaveChangesAsync();
    });

    private async Task<Guid> CompanyOf(Guid vehicle)
    {
        var company = Guid.Empty;
        await app.WithDb(async db => company = await db.Set<FleetVehicle>().IgnoreQueryFilters().Where(v => v.Id == vehicle)
            .Select(v => v.CompanyId).SingleAsync());
        return company;
    }

    private static async Task Central(HttpClient client, Guid item, DateOnly date, decimal units, decimal unitAmount,
        params (Guid Vehicle, decimal Amount)[] shares)
    {
        using var response = await client.PostAsJsonAsync("/setup/expenses/entries", new
        {
            date, expenseItemId = item, units, unitAmount, allocations = shares.Select(s => new { vehicleId = s.Vehicle, amount = s.Amount })
        });
        Assert.True(response.IsSuccessStatusCode, await response.Content.ReadAsStringAsync());
    }

    private static Task<PettyCashSaved> PettyExpense(HttpClient client, Guid vehicle, Guid item, DateOnly date, decimal amount, decimal units = 1) =>
        Petty(client, new { kind = "expense", date, vehicleId = vehicle, expenseItemId = item, units, unitAmount = amount });

    private static async Task<PettyCashSaved> Petty(HttpClient client, object body)
    {
        using var response = await client.PostAsJsonAsync("/setup/pettycash/entries", body);
        Assert.True(response.IsSuccessStatusCode, await response.Content.ReadAsStringAsync());
        return (await response.Content.ReadFromJsonAsync<PettyCashSaved>())!;
    }

    private static async Task<ReportTableDto> Report(HttpClient client, string path, string query)
    {
        using var response = await client.GetAsync($"/setup/reports/{path}{(query.Length == 0 ? "" : "?" + query)}");
        Assert.True(response.IsSuccessStatusCode, $"{(int)response.StatusCode}: {await response.Content.ReadAsStringAsync()}");
        return (await response.Content.ReadFromJsonAsync<ReportTableDto>())!;
    }

    private static string Text(object? cell) => ((JsonElement)cell!).GetString()!;
    private static decimal Number(object? cell) => ((JsonElement)cell!).GetDecimal();
    private static int Count(object? cell) => ((JsonElement)cell!).GetInt32();

    public void Dispose() => app.Dispose();
}
