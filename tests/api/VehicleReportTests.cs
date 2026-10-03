using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;
using Xunit;
using static Auth.Tests.RevenueTestData;

namespace Auth.Tests;

// Contract C6 and C5's "come back". The business date is Tuesday 31 March 2026. KDA 482M joined the fleet on
// 1 February with a weekly target of 7,000 (1,000 a day), raised to 14,000 (2,000 a day) from 16 March.
public sealed class VehicleReportTests : IDisposable
{
    private static readonly DateOnly Today = new(2026, 3, 31);
    private static readonly DateOnly Joined = new(2026, 2, 1);
    private static readonly DateOnly Start = new(2026, 1, 1);
    private readonly AuthFactory app = new();

    private async Task<(HttpClient Owner, Guid Vehicle, Guid Other)> Arrange()
    {
        await app.SeedDemo();
        await SetBusinessDate(app, Today);
        var company = await Company(app, "Report Fleet");
        var vehicle = await Vehicle(app, company, "KDA 482M", Joined, 7000m, revision: (14000m, new DateOnly(2026, 3, 16)));
        var other = await Vehicle(app, company, "KDB 111A", Joined);
        return (await app.SignIn(Owner), vehicle, other);
    }

    // Every kind of posting, saved straight into the database so that versions take effect on past days.
    // March for KDA 482M: repairs 2,000 + 2,500 + 5 x 100 = 5,000; charges 3 x 300 + 5 x 50 + 6,000 = 7,150;
    // loans 10,000; savings 4 x 1,000.
    private async Task Fleet(Guid vehicle, Guid other)
    {
        // Revised on 20 March from the 10th of each month to the 25th, with a larger share.
        var service = Cost("Service", Monthly(10), ExpenseBucket.RepairsAndMaintenance, [new(vehicle, 2000m), new(other, 1000m)]);
        await Save(organization =>
        {
            var item = new RecurringItem(organization, service);
            item.Revise(service with { Amount = 3500m, Schedule = Monthly(25), Allocations = [new(vehicle, 2500m), new(other, 1000m)] }, new DateOnly(2026, 3, 20));
            return item;
        });
        // Mondays, stopped from Monday 23 March.
        await Save(organization =>
        {
            var item = new RecurringItem(organization, Cost("Parking", Weekly(1), ExpenseBucket.RecurringCharges, [new(vehicle, 300m)]));
            item.Stop(new DateOnly(2026, 3, 23));
            return item;
        });
        // Phase 1 versions: an old category, and in one case no stored bucket at all (assumption A2 maps both).
        var tyres = await Save(organization => new RecurringItem(organization, new RecurringDefinition("Tyres", RecurringKind.Cost,
            CostCategory.RepairsAndUpkeep, 200m, Weekly(0), Start, null, [new(vehicle, 100m), new(other, 100m)])));
        await app.WithDb(db => db.Set<RecurringVersion>().IgnoreQueryFilters().Where(v => v.ItemId == tyres)
            .ExecuteUpdateAsync(s => s.SetProperty(v => v.Bucket, (ExpenseBucket?)null)));
        await Save(organization => new RecurringItem(organization, new RecurringDefinition("Crew lunch", RecurringKind.Cost,
            CostCategory.CrewCosts, 50m, new RecurringSchedule(RecurrenceFrequency.Daily), Start, new DateOnly(2026, 3, 5), [new(vehicle, 50m)])));
        await Save(organization => new RecurringItem(organization, Cost("Loan repayment",
            new RecurringSchedule(RecurrenceFrequency.Monthly, null, lastDay: true), ExpenseBucket.LoanRepayments, [new(vehicle, 10000m)])));
        await Save(organization => new RecurringItem(organization, Cost("Insurance",
            new RecurringSchedule(RecurrenceFrequency.Yearly, 15, month: 3), ExpenseBucket.RecurringCharges, [new(vehicle, 6000m)])));
        await Save(organization => new RecurringItem(organization, new RecurringDefinition("Owner savings", RecurringKind.Savings, null,
            1000m, Weekly(5), Start, null, [new(vehicle, 1000m)])));
        // Only the other vehicle's.
        await Save(organization => new RecurringItem(organization, Cost("Stage fee", Weekly(1), ExpenseBucket.RecurringCharges, [new(other, 999m)])));
    }

    [Fact]
    public async Task TheReportCountsMoneyInTargetEachBucketAndSavingsOnce()
    {
        var (owner, vehicle, other) = await Arrange();
        await Fleet(vehicle, other);
        await Records(app, vehicle, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 1500m, skip: [new DateOnly(2026, 3, 10)]);
        await Revenue(vehicle, new DateOnly(2026, 3, 10), null);
        await Records(app, other, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 9999m);
        // Money put into the vehicle is never money out.
        await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/investment", new { date = "2026-02-01", description = "Deposit", amount = 500000m }));

        var march = await Report(owner, vehicle, "from=2026-03-01&through=2026-03-31");
        // 29 days at 1,500 and a garage day. Today is not captured yet, so its target is left out: 15 days at 1,000, 15 at 2,000.
        Assert.Equal((43500m, 45000m), (march.MoneyIn, march.Target));
        Assert.Equal((5000m, 7150m, 10000m, 22150m), (march.Repairs, march.Charges, march.Loans, march.MoneyOut));
        Assert.Equal((21350m, 4000m, 17350m, 22150m), (march.Net, march.Savings, march.AfterSavings, march.Costs));

        // Each posting counts once: a cost in exactly one bucket, a saving apart from money out.
        Assert.Equal(march.MoneyOut, march.Postings.Where(p => p.Kind == RecurringKind.Cost).Sum(p => p.Amount));
        Assert.Equal(march.Savings, march.Postings.Where(p => p.Kind == RecurringKind.Savings).Sum(p => p.Amount));
        Assert.All(march.Postings, p => Assert.Equal(p.Kind == RecurringKind.Cost, p.Bucket is not null));
        Assert.Equal(march.Postings.OrderBy(p => p.Date), march.Postings);
        var posted = march.Postings.GroupBy(p => p.Name).ToDictionary(g => g.Key, g => g.Select(p => (p.Date.Day, p.Amount)).ToArray());
        Assert.Equal([(10, 2000m), (25, 2500m)], posted["Service"]);
        Assert.Equal([(2, 300m), (9, 300m), (16, 300m)], posted["Parking"]);
        Assert.Equal([(1, 100m), (8, 100m), (15, 100m), (22, 100m), (29, 100m)], posted["Tyres"]);
        Assert.Equal([1, 2, 3, 4, 5], posted["Crew lunch"].Select(x => x.Day));
        Assert.Equal([(31, 10000m)], posted["Loan repayment"]);
        Assert.Equal([(15, 6000m)], posted["Insurance"]);
        Assert.Equal([6, 13, 20, 27], posted["Owner savings"].Select(x => x.Day));
        Assert.False(posted.ContainsKey("Stage fee"));
        Assert.All(march.Postings.Where(p => p.Name == "Tyres"), p => Assert.Equal((CostCategory.RepairsAndUpkeep, ExpenseBucket.RepairsAndMaintenance), (p.Category!.Value, p.Bucket!.Value)));
        Assert.All(march.Postings.Where(p => p.Name == "Crew lunch"), p => Assert.Equal(ExpenseBucket.RecurringCharges, p.Bucket));

        // Once today is captured, its target counts too, exactly as the revenue week counts it.
        await Revenue(vehicle, Today, 2000m);
        var captured = await Report(owner, vehicle, "from=2026-03-01&through=2026-03-31");
        Assert.Equal((45500m, 47000m, 23350m), (captured.MoneyIn, captured.Target, captured.Net));
        var week = await owner.GetFromJsonAsync<JsonElement>($"/setup/revenue?vehicleId={vehicle}");
        var thisWeek = await Report(owner, vehicle, $"from={week.GetProperty("weekStart").GetString()}&through=2026-03-31");
        Assert.Equal((week.GetProperty("totalAmount").GetDecimal(), week.GetProperty("totalExpected").GetDecimal()), (thisWeek.MoneyIn, thisWeek.Target));
    }

    [Fact]
    public async Task TheReportKeepsTheContractShape()
    {
        var (owner, vehicle, other) = await Arrange();
        await Fleet(vehicle, other);

        var report = await owner.GetFromJsonAsync<JsonElement>($"/setup/vehicles/{vehicle}/report?period=month");
        Assert.Equal(["vehicleId", "from", "through", "moneyIn", "target", "repairs", "charges", "loans", "moneyOut", "net", "savings", "afterSavings", "costs", "postings"],
            report.EnumerateObject().Select(x => x.Name));
        Assert.Equal(["itemId", "versionId", "date", "name", "kind", "category", "amount", "bucket"],
            report.GetProperty("postings")[0].EnumerateObject().Select(x => x.Name));
    }

    [Fact]
    public async Task AVehicleThatLeftPostsNothingFromItsLeaveDateAndStaysInPastReports()
    {
        var (owner, vehicle, other) = await Arrange();
        await Save(organization => new RecurringItem(organization, Cost("Parking", Weekly(1), ExpenseBucket.RecurringCharges, [new(vehicle, 300m)])));
        await Save(organization => new RecurringItem(organization, Cost("Service", Monthly(19), ExpenseBucket.RepairsAndMaintenance, [new(vehicle, 2000m), new(other, 1000m)])));
        await Save(organization => new RecurringItem(organization, Cost("Loan repayment", Monthly(20), ExpenseBucket.LoanRepayments, [new(vehicle, 10000m)])));
        // Captured while it was running, up to its last day in service. A leave date on or before a day that
        // has a record is refused (D4), so the records stop on the 19th and the vehicle leaves on the 20th.
        await Records(app, vehicle, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 19), 1000m);
        await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/retire", new { leftOn = "2026-03-20" }));

        // The leave date is its first day away, as for revenue: it was active from 1 to 19 March.
        var march = await Report(owner, vehicle, "from=2026-03-01&through=2026-03-31");
        Assert.Equal((19000m, 15 * 1000m + 4 * 2000m), (march.MoneyIn, march.Target));
        Assert.Equal([(2, 300m), (9, 300m), (16, 300m), (19, 2000m)], march.Postings.Select(p => (p.Date.Day, p.Amount)));
        Assert.Equal((2000m, 900m, 0m, 2900m, 16100m), (march.Repairs, march.Charges, march.Loans, march.MoneyOut, march.Net));

        var february = await Report(owner, vehicle, "from=2026-02-01&through=2026-02-28");
        Assert.Equal((0m, 28000m), (february.MoneyIn, february.Target));
        Assert.Equal((2000m, 1200m, 10000m, -13200m), (february.Repairs, february.Charges, february.Loans, february.Net));
    }

    [Fact]
    public async Task AReportOutsideThePersonsDataScopeIsNotFound()
    {
        await app.SeedDemo();
        await SetBusinessDate(app, Today);
        var (north, south) = (await Company(app, "North Star"), await Company(app, "South Line"));
        var mine = await Vehicle(app, north, "KDA 482M", Joined);
        var theirs = await Vehicle(app, south, "KDB 111A", Joined);
        await Records(app, theirs, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 5000m);
        await Grant(Clerk, "vehicles.manage");
        await ScopeToCompany(app, Clerk, north);

        using var clerk = await app.SignIn(Clerk);
        Assert.Equal(0m, (await Report(clerk, mine, "period=month")).MoneyIn);
        Assert.Equal(HttpStatusCode.NotFound, (await clerk.GetAsync($"/setup/vehicles/{theirs}/report?period=month")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await clerk.GetAsync($"/setup/vehicles/{Guid.NewGuid()}/report?period=month")).StatusCode);
    }

    [Fact]
    public async Task WhatHasComeBackIsTheNetContributionSinceJoiningAgainstWhatWentIn()
    {
        var (owner, vehicle, other) = await Arrange();
        await Fleet(vehicle, other);
        await Records(app, vehicle, new DateOnly(2026, 3, 1), Today, 1500m, skip: [new DateOnly(2026, 3, 10), Today]);
        await Revenue(vehicle, new DateOnly(2026, 3, 10), null);
        await Revenue(vehicle, Today, 2000m);
        // Joined on 1 February: January's postings are not its own. February has no revenue and costs
        // 2,000 + 4 x 300 + 4 x 100 + 28 x 50 + 10,000 = 15,000; March nets 23,350.
        var nothingIn = await Investment(owner, vehicle);
        Assert.Equal((0m, 8350m), (nothingIn.TotalInvested, nothingIn.Returned!.Value));
        Assert.Null(nothingIn.PercentPaidOff);

        await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/investment", new { date = "2026-01-20", description = "Deposit", amount = 12000m }));
        await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/investment", new { date = "2026-01-25", description = "Refit", amount = 8000m }));
        var investment = await Investment(owner, vehicle);
        Assert.Equal((20000m, 8350m, 42m), (investment.TotalInvested, investment.Returned!.Value, investment.PercentPaidOff!.Value));
        // The same figure as the report from the join date through the business date.
        Assert.Equal((await Report(owner, vehicle, "from=2026-02-01&through=2026-03-31")).Net, investment.Returned);

        // A vehicle that has cost more than it brought in shows how far behind it is.
        await Save(organization => new RecurringItem(organization, Cost("Loan repayment", Monthly(1), ExpenseBucket.LoanRepayments, [new(other, 5000m)])));
        await Records(app, other, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 2), 1000m);
        await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{other}/investment", new { date = "2026-01-20", description = "Deposit", amount = 32000m }));
        var behind = await Investment(owner, other);
        // Revenue 2,000 against the stage fee on 9 Mondays at 999, service 3 x 1,000, tyres on 9 Sundays at 100 and the loan 2 x 5,000.
        Assert.Equal((-20891m, -65m), (behind.Returned!.Value, behind.PercentPaidOff!.Value));
    }

    [Fact]
    public async Task TheReportReadsTheSameNumberOfTimesHoweverManyItemsAndOtherSharesThereAre()
    {
        var (owner, vehicle, other) = await Arrange();
        await Records(app, vehicle, new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 30), 1500m);
        await Save(organization => new RecurringItem(organization, Cost("Parking", Weekly(1), ExpenseBucket.RecurringCharges, [new(vehicle, 300m), new(other, 300m)])));

        async Task<(int Reads, int Rows)> Measure()
        {
            app.Database.Reset();
            using var response = await owner.GetAsync($"/setup/vehicles/{vehicle}/report?from=2026-01-01&through=2026-03-31");
            response.EnsureSuccessStatusCode();
            return (app.Database.Sql.Count(sql => sql.TrimStart().StartsWith("SELECT", StringComparison.OrdinalIgnoreCase)), app.Database.Rows);
        }

        var one = await Measure();
        Assert.Equal(one, await Measure());
        // One more item shared with a hundred other vehicles loads one more version row, not a hundred shares.
        var crowd = await Vehicles(100);
        await Save(organization => new RecurringItem(organization, Cost("Stage fee", Weekly(2), ExpenseBucket.RecurringCharges,
            [new(vehicle, 100m), .. crowd.Select(id => new VehicleShare(id, 100m))])));
        var shared = await Measure();
        Assert.Equal((one.Reads, one.Rows + 1), shared);
        // Forty more daily items: many more postings, the same queries, and one row per version.
        for (var i = 0; i < 40; i++)
            await Save(organization => new RecurringItem(organization, new RecurringDefinition($"Daily {i}", RecurringKind.Cost, CostCategory.RunningCosts,
                10m, new RecurringSchedule(RecurrenceFrequency.Daily), Start, null, [new(vehicle, 10m)])));
        var many = await Measure();
        Assert.Equal((one.Reads, one.Rows + 41), many);
    }

    private static RecurringSchedule Weekly(int day) => new(RecurrenceFrequency.Weekly, day);
    private static RecurringSchedule Monthly(int day) => new(RecurrenceFrequency.Monthly, day);

    private static RecurringDefinition Cost(string name, RecurringSchedule schedule, ExpenseBucket bucket, IReadOnlyList<VehicleShare> shares) =>
        new(name, RecurringKind.Cost, null, shares.Sum(s => s.Amount), schedule, Start, null, shares, Bucket: bucket);

    private static async Task<VehicleReport> Report(HttpClient client, Guid vehicle, string query) =>
        (await client.GetFromJsonAsync<VehicleReport>($"/setup/vehicles/{vehicle}/report?{query}"))!;

    private static async Task<InvestmentDto> Investment(HttpClient client, Guid vehicle) =>
        (await client.GetFromJsonAsync<InvestmentDto>($"/setup/vehicles/{vehicle}/investment"))!;

    private async Task<Guid> Save(Func<Guid, RecurringItem> build)
    {
        var id = Guid.Empty;
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var item = build((await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id);
            db.Add(item);
            await db.SaveChangesAsync();
            id = item.Id;
        });
        return id;
    }

    // A record with no money in: the vehicle was at the garage.
    private Task Revenue(Guid vehicle, DateOnly date, decimal? amount) => app.WithDb(async db =>
    {
        db.Provisioning = true;
        var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
        var actor = (await db.Users.SingleAsync(x => x.Email == Owner)).Id;
        db.Add(new RevenueRecord(organizationId, vehicle, date, new RevenueEntry(amount, amount is null ? RevenueNoEarningsReason.Garage : null, null),
            app.Clock.UtcNow.ToUniversalTime(), actor));
        await db.SaveChangesAsync();
    });

    private async Task<List<Guid>> Vehicles(int count)
    {
        var ids = new List<Guid>();
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
            var company = new PsvCompany(organizationId, "Crowd Fleet");
            db.Add(company);
            var vehicles = Enumerable.Range(0, count)
                .Select(i => new FleetVehicle(organizationId, company.Id, new VehicleRegistration($"KC{(char)('A' + i / 100)}{i % 100:D3}A"), Joined, 7000m))
                .ToList();
            db.AddRange(vehicles);
            await db.SaveChangesAsync();
            ids.AddRange(vehicles.Select(v => v.Id));
        });
        return ids;
    }

    private Task Grant(string email, string permission) => app.WithDb(async db =>
    {
        db.Provisioning = true;
        var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
        var user = (await db.Users.SingleAsync(x => x.Email == email)).Id;
        db.PermissionOverrides.Add(new PersonPermissionOverride { OrganizationId = organizationId, UserId = user, Permission = permission, Granted = true });
        await db.SaveChangesAsync();
    });

    private static async Task<Guid> Id(HttpResponseMessage response)
    {
        using (response)
        {
            Assert.True(response.IsSuccessStatusCode, await response.Content.ReadAsStringAsync());
            return (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetGuid();
        }
    }

    public void Dispose() => app.Dispose();
}
