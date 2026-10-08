using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application.Revenue;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;
using Xunit;
using static Auth.Tests.RevenueTestData;

namespace Auth.Tests;

// The week grid pages its vehicles in registration order, while its figures (totals, day totals and the first gap)
// always cover the whole grid. Without page or pageSize it lists the whole grid as released clients expect.
// T is a pinned Thursday, so the Monday-first week runs from T-3 to T+3; every weekly target is 7,000 (1,000 a day).
public sealed class RevenueWeekPagingTests : IDisposable
{
    private readonly AuthFactory app = new();

    private sealed record Fleet(DateOnly Today, Guid Paging, Guid Other, Guid[] Vehicles);

    // In grid order: KAA 601A complete through T-1; 602A through T-3; 603A through T-5; 604A through T-1 and 1,500 on
    // T; 605A joined on T-1 with nothing recorded; then, in another company, KAB 611A through T-6 and 612A through T-1.
    private async Task<Fleet> Arrange()
    {
        await app.SeedDemo();
        var today = PinnedThursday(app);
        await SetBusinessDate(app, today);
        var paging = await Company(app, "Paging Fleet");
        var other = await Company(app, "Other Paging Fleet");
        var joined = today.AddDays(-20);
        var complete = await Vehicle(app, paging, "KAA 601A", joined);
        await Records(app, complete, joined, today.AddDays(-1));
        var behind = await Vehicle(app, paging, "KAA 602A", joined);
        await Records(app, behind, joined, today.AddDays(-3));
        var further = await Vehicle(app, paging, "KAA 603A", joined);
        await Records(app, further, joined, today.AddDays(-5));
        var captured = await Vehicle(app, paging, "KAA 604A", joined);
        await Records(app, captured, joined, today.AddDays(-1));
        await Records(app, captured, today, today, 1500m);
        var midweek = await Vehicle(app, paging, "KAA 605A", today.AddDays(-1));
        var furthest = await Vehicle(app, other, "KAB 611A", joined);
        await Records(app, furthest, joined, today.AddDays(-6));
        var done = await Vehicle(app, other, "KAB 612A", joined);
        await Records(app, done, joined, today.AddDays(-1));
        return new(today, paging, other, [complete, behind, further, captured, midweek, furthest, done]);
    }

    private static readonly string[] WholeGridFields =
        ["weekStart", "weekThrough", "currentWeekStart", "businessDate", "companies", "totalAmount", "totalExpected", "percent", "dayTotals", "firstGap"];

    [Fact]
    public async Task PagesSplitTheGridInRegistrationOrderAndEachCarriesTheWholeWeeksFigures()
    {
        var fleet = await Arrange();
        var today = fleet.Today;
        using var owner = await app.SignIn(Owner);

        var whole = await Week(owner, "");
        var pages = new List<JsonElement>();
        for (var number = 1; number <= 5; number++)
            pages.Add(await Week(owner, $"?page={number}&pageSize=2"));

        Assert.Equal(fleet.Vehicles, Ids(whole));
        Assert.Equal([fleet.Vehicles[2], fleet.Vehicles[3]], Ids(pages[1]));
        Assert.Equal([fleet.Vehicles[6]], Ids(pages[3]));
        Assert.Empty(Ids(pages[4]));
        // Each page's rows are exactly the whole grid's rows, in the same order.
        Assert.Equal(Rows(whole), pages.SelectMany(Rows));
        foreach (var (page, number) in pages.Select((page, index) => (page, index + 1)))
        {
            Assert.Equal(number, page.GetProperty("pageNumber").GetInt32());
            Assert.Equal(2, page.GetProperty("pageSize").GetInt32());
            Assert.Equal(7, page.GetProperty("totalVehicles").GetInt32());
            Assert.False(page.GetProperty("truncated").GetBoolean());
            foreach (var field in WholeGridFields)
                Assert.Equal(whole.GetProperty(field).GetRawText(), page.GetProperty(field).GetRawText());
        }

        // Summed unrounded over all seven vehicles, then rounded once: 11,500 of 20,000 is 57.5%, shown as 58.
        Assert.Equal(11500m, whole.GetProperty("totalAmount").GetDecimal());
        Assert.Equal(20000m, whole.GetProperty("totalExpected").GetDecimal());
        Assert.Equal(58, whole.GetProperty("percent").GetInt32());
        // A day's amount is what its cells show as recorded amounts; its expected figure counts the days that count
        // toward the totals, so today expects only the vehicle already recorded and later days expect nothing.
        Assert.Equal([
            (Text(today.AddDays(-3)), 4000m, 6000m), (Text(today.AddDays(-2)), 3000m, 6000m), (Text(today.AddDays(-1)), 3000m, 7000m),
            (Text(today), 1500m, 1000m), (Text(today.AddDays(1)), 0m, 0m), (Text(today.AddDays(2)), 0m, 0m), (Text(today.AddDays(3)), 0m, 0m)],
            DayTotals(whole));
        // KAB 611A has the earliest missing day of the grid, on a page of its own.
        Assert.Equal((fleet.Vehicles[5], Text(today.AddDays(-5))), FirstGap(whole));
    }

    [Fact]
    public async Task ACompanyFilterAndADataScopeEachNarrowThePagesAndTheirFigures()
    {
        var fleet = await Arrange();
        var today = fleet.Today;
        await ScopeToCompany(app, Clerk, fleet.Other);
        using var owner = await app.SignIn(Owner);
        using var clerk = await app.SignIn(Clerk);

        var company = await Week(owner, $"?companyId={fleet.Paging}");
        var last = await Week(owner, $"?companyId={fleet.Paging}&page=3&pageSize=2");
        Assert.Equal([fleet.Vehicles[4]], Ids(last));
        Assert.Equal(5, last.GetProperty("totalVehicles").GetInt32());
        foreach (var field in WholeGridFields)
            Assert.Equal(company.GetProperty(field).GetRawText(), last.GetProperty(field).GetRawText());
        Assert.Equal(8500m, last.GetProperty("totalAmount").GetDecimal());
        Assert.Equal(14000m, last.GetProperty("totalExpected").GetDecimal());
        Assert.Equal(61, last.GetProperty("percent").GetInt32());
        Assert.Equal((fleet.Vehicles[2], Text(today.AddDays(-4))), FirstGap(last));

        // The clerk reaches only the other company: its two vehicles, and their figures alone.
        var scoped = await Week(clerk, "?page=2&pageSize=1");
        Assert.Equal([fleet.Vehicles[6]], Ids(scoped));
        Assert.Equal(2, scoped.GetProperty("totalVehicles").GetInt32());
        Assert.Equal(3000m, scoped.GetProperty("totalAmount").GetDecimal());
        Assert.Equal(6000m, scoped.GetProperty("totalExpected").GetDecimal());
        Assert.Equal((fleet.Vehicles[5], Text(today.AddDays(-5))), FirstGap(scoped));
        Assert.Equal([(Text(today.AddDays(-3)), 1000m, 2000m), (Text(today.AddDays(-2)), 1000m, 2000m),
            (Text(today.AddDays(-1)), 1000m, 2000m), (Text(today), 0m, 0m)], DayTotals(scoped).Take(4));
    }

    [Fact]
    public async Task AVehiclesOwnWeekIgnoresPaging()
    {
        var fleet = await Arrange();
        await ScopeToCompany(app, Clerk, fleet.Other);
        using var clerk = await app.SignIn(Clerk);
        var mine = fleet.Vehicles[5];

        foreach (var paging in new[] { "", "&page=2&pageSize=1", "&page=0&pageSize=1000" })
        {
            var week = await Week(clerk, $"?vehicleId={mine}{paging}");
            Assert.Equal([mine], Ids(week));
            Assert.Equal(1, week.GetProperty("totalVehicles").GetInt32());
            Assert.Equal((mine, Text(fleet.Today.AddDays(-5))), FirstGap(week));
        }
        // A vehicle outside the person's scope is still not found, paged or not.
        Assert.Equal(HttpStatusCode.NotFound, (await clerk.GetAsync($"/setup/revenue?vehicleId={fleet.Vehicles[0]}&page=1&pageSize=1")).StatusCode);
    }

    [Fact]
    public async Task PagingOutsideItsLimitsIsRefused()
    {
        await Arrange();
        using var owner = await app.SignIn(Owner);

        foreach (var query in new[] { "?pageSize=101", "?page=1&pageSize=0", "?page=0", "?page=100001&pageSize=1" })
        {
            using var refused = await owner.GetAsync("/setup/revenue" + query);
            Assert.Equal(HttpStatusCode.BadRequest, refused.StatusCode);
            Phase1.Problem(await Phase1.Body(refused));
        }
        // Either one alone asks for paging: page defaults to 1 and pageSize to 100.
        var sized = await Week(owner, "?pageSize=100");
        Assert.Equal((1, 100, 7), (sized.GetProperty("pageNumber").GetInt32(), sized.GetProperty("pageSize").GetInt32(), Ids(sized).Length));
        var numbered = await Week(owner, "?page=1");
        Assert.Equal((1, RevenueWeekPage.DefaultSize), (numbered.GetProperty("pageNumber").GetInt32(), numbered.GetProperty("pageSize").GetInt32()));
    }

    // Released phones and web tabs read this response as raw JSON: every field they read keeps its name, type and value,
    // and the new fields only follow them.
    [Fact]
    public async Task TheWeekWithoutPagingKeepsItsReleasedShape()
    {
        var fleet = await Arrange();
        var today = fleet.Today;
        using var owner = await app.SignIn(Owner);
        var week = await Week(owner, "");

        Assert.Equal(["weekStart", "weekThrough", "currentWeekStart", "businessDate", "companies", "vehicles", "totalAmount", "totalExpected",
            "percent", "pageNumber", "pageSize", "totalVehicles", "truncated", "dayTotals", "firstGap"], week.EnumerateObject().Select(x => x.Name));
        foreach (var date in new[] { "weekStart", "weekThrough", "currentWeekStart", "businessDate" })
            Phase1.Has(week, date, J.Str);
        Assert.Equal(Text(today.AddDays(-3)), week.GetProperty("weekStart").GetString());
        Assert.Equal(Text(today.AddDays(3)), week.GetProperty("weekThrough").GetString());
        Assert.Equal(Text(today), week.GetProperty("businessDate").GetString());
        Assert.Equal(["Other Paging Fleet", "Paging Fleet"], Phase1.Items(week, "companies").Select(x => Phase1.Has(x, "name", J.Str).GetString()));
        Phase1.Has(week, "totalAmount", J.Num);
        Phase1.Has(week, "totalExpected", J.Num);
        Phase1.Has(week, "percent", J.Num, J.Null);
        Assert.Equal((1, RevenueWeekPage.LegacyLimit, 7, false), (week.GetProperty("pageNumber").GetInt32(), week.GetProperty("pageSize").GetInt32(),
            week.GetProperty("totalVehicles").GetInt32(), week.GetProperty("truncated").GetBoolean()));

        var rows = Phase1.Items(week, "vehicles");
        Assert.Equal(7, rows.Length);
        foreach (var row in rows)
        {
            Assert.Equal(["id", "companyId", "companyName", "registration", "joinedOn", "leftOn", "earliestMissing", "days", "totalAmount",
                "totalExpected", "percent"], row.EnumerateObject().Select(x => x.Name));
            Phase1.Has(row, "leftOn", J.Str, J.Null);
            Phase1.Has(row, "earliestMissing", J.Str, J.Null);
            Assert.Equal(7, Phase1.Items(row, "days").Length);
            foreach (var cell in Phase1.Items(row, "days"))
            {
                Assert.Equal(["date", "status", "expected", "amount", "reason", "note", "canEdit", "editedAfterCapture", "version"],
                    cell.EnumerateObject().Select(x => x.Name));
                Phase1.Has(cell, "amount", J.Num, J.Null);
                Phase1.Has(cell, "reason", J.Str, J.Null);
                Phase1.Has(cell, "note", J.Str, J.Null);
                Phase1.Has(cell, "version", J.Num, J.Null);
            }
        }

        // Each vehicle's own figures, as they were before the week had pages.
        Assert.Equal([
            ("KAA 601A", null, 3000m, 3000m, 100), ("KAA 602A", Text(today.AddDays(-2)), 1000m, 3000m, 33),
            ("KAA 603A", Text(today.AddDays(-4)), 0m, 3000m, 0), ("KAA 604A", null, 4500m, 4000m, 113),
            ("KAA 605A", Text(today.AddDays(-1)), 0m, 1000m, 0), ("KAB 611A", Text(today.AddDays(-5)), 0m, 3000m, 0),
            ("KAB 612A", null, 3000m, 3000m, 100)],
            rows.Select(row => (row.GetProperty("registration").GetString(), row.GetProperty("earliestMissing").GetString(),
                row.GetProperty("totalAmount").GetDecimal(), row.GetProperty("totalExpected").GetDecimal(), (int?)row.GetProperty("percent").GetInt32())));
        var behind = rows[1].GetProperty("days").EnumerateArray().ToArray();
        Assert.Equal(["amount", "missing", "missing", "missing", "future", "future", "future"], behind.Select(x => x.GetProperty("status").GetString()));
        Assert.Equal(1000m, behind[0].GetProperty("amount").GetDecimal());
        Assert.Equal(1, behind[0].GetProperty("version").GetInt64());
        Assert.Equal(JsonValueKind.Null, behind[1].GetProperty("amount").ValueKind);
        Assert.Equal(JsonValueKind.Null, behind[1].GetProperty("version").ValueKind);
        // The owner may correct the recorded day; the earliest missing day opens and a later one stays shut until it is filled.
        Assert.Equal([true, true, false, false], behind.Take(4).Select(x => x.GetProperty("canEdit").GetBoolean()));
        Assert.Equal(1000m, behind[1].GetProperty("expected").GetDecimal());
        var midweek = rows[4].GetProperty("days").EnumerateArray().ToArray();
        Assert.Equal(("none", 0m), (midweek[0].GetProperty("status").GetString(), midweek[0].GetProperty("expected").GetDecimal()));
        Assert.Equal(11500m, week.GetProperty("totalAmount").GetDecimal());
        Assert.Equal(20000m, week.GetProperty("totalExpected").GetDecimal());
        Assert.Equal(58, week.GetProperty("percent").GetInt32());
    }

    [Fact]
    public async Task TheWeekWithoutPagingStopsAtItsLimitAndSaysSo()
    {
        await app.SeedDemo();
        var today = PinnedThursday(app);
        await SetBusinessDate(app, today);
        var company = await Company(app, "Large Paging Fleet");
        // One more vehicle than the limit, each joined on T-1 with nothing recorded, so each expects 1,000 this week.
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
            for (var i = 0; i <= RevenueWeekPage.LegacyLimit; i++)
                db.Set<FleetVehicle>().Add(new(organizationId, company, new VehicleRegistration($"KCA {i:000}A"), today.AddDays(-1), 7000m));
            await db.SaveChangesAsync();
        });
        using var owner = await app.SignIn(Owner);

        var legacy = await Week(owner, "");
        Assert.Equal(RevenueWeekPage.LegacyLimit, Ids(legacy).Length);
        Assert.True(legacy.GetProperty("truncated").GetBoolean());
        Assert.Equal(RevenueWeekPage.LegacyLimit + 1, legacy.GetProperty("totalVehicles").GetInt32());
        // The figures still cover the vehicle left off the list.
        Assert.Equal((RevenueWeekPage.LegacyLimit + 1) * 1000m, legacy.GetProperty("totalExpected").GetDecimal());

        var last = await Week(owner, "?page=6&pageSize=100");
        Assert.Equal([$"KCA {RevenueWeekPage.LegacyLimit:000}A"], last.GetProperty("vehicles").EnumerateArray().Select(x => x.GetProperty("registration").GetString()));
        Assert.False(last.GetProperty("truncated").GetBoolean());
    }

    [Fact]
    public async Task TheFirstGapIsTheEarliestMissingDayAndTheFirstVehicleInGridOrderOnATie()
    {
        await app.SeedDemo();
        var today = PinnedThursday(app);
        await SetBusinessDate(app, today);
        var company = await Company(app, "Gap Fleet");
        var first = await Vehicle(app, company, "KAA 701A", today.AddDays(-10));
        await Records(app, first, today.AddDays(-10), today.AddDays(-3));
        var second = await Vehicle(app, company, "KAA 702A", today.AddDays(-10));
        await Records(app, second, today.AddDays(-10), today.AddDays(-3));
        using var owner = await app.SignIn(Owner);

        Assert.Equal((first, Text(today.AddDays(-2))), FirstGap(await Week(owner, $"?companyId={company}")));
        // A vehicle later in the grid with an earlier gap takes its place.
        var third = await Vehicle(app, company, "KAA 703A", today.AddDays(-10));
        await Records(app, third, today.AddDays(-10), today.AddDays(-4));
        Assert.Equal((third, Text(today.AddDays(-3))), FirstGap(await Week(owner, $"?companyId={company}&page=1&pageSize=1")));

        // With every earlier day recorded, capture starts at the first vehicle still missing today, but only in a week
        // that holds today.
        var current = await Company(app, "Current Fleet");
        var open = await Vehicle(app, current, "KAB 711A", today.AddDays(-10));
        await Records(app, open, today.AddDays(-10), today.AddDays(-1));
        var closed = await Vehicle(app, current, "KAB 712A", today.AddDays(-10));
        await Records(app, closed, today.AddDays(-10), today);
        Assert.Equal((open, Text(today)), FirstGap(await Week(owner, $"?companyId={current}")));
        var lastWeek = await Week(owner, $"?companyId={current}&weekStart={Text(today.AddDays(-7))}");
        Assert.Equal(JsonValueKind.Null, lastWeek.GetProperty("firstGap").ValueKind);
        await Records(app, open, today, today);
        Assert.Equal(JsonValueKind.Null, (await Week(owner, $"?companyId={current}")).GetProperty("firstGap").ValueKind);
    }

    // The grid reads targets and away periods in queries of their own, so one never multiplies the other's rows, and
    // reads only the record columns a cell shows.
    [Fact]
    public async Task TheWeekReadsTargetsAndAwayPeriodsApartAndOnlyTheRecordColumnsItShows()
    {
        var fleet = await Arrange();
        var away = await Vehicle(app, fleet.Paging, "KAA 606A", fleet.Today.AddDays(-20), revision: (8000m, fleet.Today.AddDays(-10)),
            away: (fleet.Today.AddDays(-12), fleet.Today.AddDays(-11)));
        await Records(app, away, fleet.Today.AddDays(-20), fleet.Today.AddDays(-13));
        using var owner = await app.SignIn(Owner);
        await Week(owner, "?page=1&pageSize=2");

        app.Database.Reset();
        var week = await Week(owner, "?page=1&pageSize=2");
        var sql = app.Database.Sql.ToArray();
        Assert.Contains(sql, x => x.Contains("\"VehicleTarget\""));
        Assert.Contains(sql, x => x.Contains("\"VehicleAwayPeriod\""));
        Assert.DoesNotContain(sql, x => x.Contains("\"VehicleTarget\"") && x.Contains("\"VehicleAwayPeriod\""));
        var records = sql.Where(x => x.Contains("\"RevenueRecords\"")).ToArray();
        Assert.NotEmpty(records);
        foreach (var column in new[] { "CapturedAt", "CapturedBy", "UpdatedAt", "UpdatedBy" })
            Assert.DoesNotContain(records, x => x.Contains(column));
        Assert.Equal(8, week.GetProperty("totalVehicles").GetInt32());
    }

    private async Task<JsonElement> Week(HttpClient client, string query)
    {
        using var response = await client.GetAsync("/setup/revenue" + query);
        Assert.True(response.IsSuccessStatusCode, $"GET /setup/revenue{query} answered {(int)response.StatusCode}: {await response.Content.ReadAsStringAsync()}");
        return await response.Content.ReadFromJsonAsync<JsonElement>();
    }

    private static Guid[] Ids(JsonElement week) =>
        [.. week.GetProperty("vehicles").EnumerateArray().Select(x => x.GetProperty("id").GetGuid())];

    private static IEnumerable<string> Rows(JsonElement week) =>
        week.GetProperty("vehicles").EnumerateArray().Select(x => x.GetRawText());

    private static (string?, decimal, decimal)[] DayTotals(JsonElement week) =>
        [.. week.GetProperty("dayTotals").EnumerateArray()
            .Select(x => (x.GetProperty("date").GetString(), x.GetProperty("amount").GetDecimal(), x.GetProperty("expected").GetDecimal()))];

    private static (Guid, string?) FirstGap(JsonElement week)
    {
        var gap = Phase1.Has(week, "firstGap", J.Obj);
        return (gap.GetProperty("vehicleId").GetGuid(), gap.GetProperty("date").GetString());
    }

    private static string Text(DateOnly date) => date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    public void Dispose() => app.Dispose();
}
