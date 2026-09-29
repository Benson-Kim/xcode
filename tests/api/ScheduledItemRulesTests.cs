using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application.Setup;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace Auth.Tests;

// Addendum 1: scheduled items run weekly, monthly or yearly, savings weekly or monthly, a cost picks an expense
// item, and nothing starts before the first of the business month. Versions saved before stay history and keep posting.
public sealed class ScheduledItemRulesTests : IDisposable
{
    private readonly AuthFactory app = new();
    private static readonly DateOnly Today = new(2026, 3, 15); // A Sunday.
    private HttpClient owner = null!;
    private Guid vehicle;

    private SaveRecurring Cost(Guid? item, RecurrenceFrequency frequency, int? day, bool lastDay = false, int? month = null,
        DateOnly? start = null, string? note = null) =>
        new(null, RecurringKind.Cost, null, 500m, frequency, day, lastDay, start ?? Today, null, [new VehicleShare(vehicle, 500m)],
            "Schedule it", item, note, month);

    private SaveRecurring Saving(RecurrenceFrequency frequency, int? day, bool lastDay = false, int? month = null) =>
        new("Owner savings", RecurringKind.Savings, null, 500m, frequency, day, lastDay, Today, null, [new VehicleShare(vehicle, 500m)],
            "Set it aside", null, null, month);

    private async Task Setup()
    {
        await app.SeedDemo();
        owner = await app.SignIn("antony.maina@shamayah.co.ke");
        (await owner.PutAsJsonAsync("/setup/organization/settings/businessDate",
            new { value = Today.ToString("yyyy-MM-dd"), reason = "Work on a fixed business date" })).EnsureSuccessStatusCode();
        var company = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("Rules Fleet", "Add Rules Fleet")));
        vehicle = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(company, "KDA 482M", new DateOnly(2026, 1, 1), 15000m, "Add KDA 482M")));
    }

    private Task<HttpResponseMessage> Create(SaveRecurring input) => owner.PostAsJsonAsync("/setup/recurring", input);

    [Fact]
    public async Task NewSchedulesAreWeeklyMonthlyOrYearlyAndSavingsWeeklyOrMonthly()
    {
        await Setup();
        var insurance = await ExpenseItemTestData.Id(owner, "Insurance");

        using var daily = await Create(Cost(insurance, RecurrenceFrequency.Daily, null));
        Assert.Equal(HttpStatusCode.BadRequest, daily.StatusCode);
        Assert.Contains("Daily", (await daily.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString());
        foreach (var refused in new[]
        {
            Cost(insurance, RecurrenceFrequency.Yearly, 10),
            Cost(insurance, RecurrenceFrequency.Yearly, 10, month: 13),
            Cost(insurance, RecurrenceFrequency.Yearly, 29, month: 3),
            Cost(insurance, RecurrenceFrequency.Monthly, 10, month: 3),
            Saving(RecurrenceFrequency.Yearly, 10, month: 3),
            Saving(RecurrenceFrequency.Daily, null),
        })
            Assert.Equal(HttpStatusCode.BadRequest, (await Create(refused)).StatusCode);

        foreach (var accepted in new[]
        {
            Cost(insurance, RecurrenceFrequency.Yearly, 10, month: 3),
            Cost(insurance, RecurrenceFrequency.Yearly, null, lastDay: true, month: 2),
            Saving(RecurrenceFrequency.Weekly, 6),
            Saving(RecurrenceFrequency.Monthly, null, lastDay: true),
        })
            (await Create(accepted)).EnsureSuccessStatusCode();
        var items = (await owner.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring"))!.Items;
        Assert.Contains(items, x => x is { Frequency: RecurrenceFrequency.Yearly, Month: 3, Day: 10 });
        Assert.Contains(items, x => x is { Frequency: RecurrenceFrequency.Yearly, Month: 2, LastDay: true });
    }

    [Fact]
    public async Task CostsNeedAnExpenseItemInUseAndSavingsNeverHaveOne()
    {
        await Setup();
        var options = (await owner.GetFromJsonAsync<List<ExpenseItemOption>>("/setup/expense-items/options"))!;
        var towing = options.Single(x => x.Name == "Towing");
        var loan = options.Single(x => x.Name == "Loan repayment");
        (await owner.PostAsync($"/setup/expense-items/{towing.Id}/stop", null)).EnsureSuccessStatusCode();
        (await owner.PostAsync($"/setup/expense-categories/{loan.CategoryId}/stop", null)).EnsureSuccessStatusCode();

        foreach (var refused in new[]
        {
            Cost(null, RecurrenceFrequency.Monthly, 5),
            Cost(Guid.NewGuid(), RecurrenceFrequency.Monthly, 5),
            Cost(towing.Id, RecurrenceFrequency.Monthly, 5),
            Cost(loan.Id, RecurrenceFrequency.Monthly, 5),
            Cost(options.Single(x => x.Name == "Spares").Id, RecurrenceFrequency.Monthly, 5, note: new string('n', 201)),
            Saving(RecurrenceFrequency.Monthly, 5) with { ExpenseItemId = towing.Id },
            Saving(RecurrenceFrequency.Monthly, 5) with { Category = CostCategory.FixedCommitments },
        })
            Assert.Equal(HttpStatusCode.BadRequest, (await Create(refused)).StatusCode);

        (await Create(Cost(options.Single(x => x.Name == "Spares").Id, RecurrenceFrequency.Monthly, 5, note: new string('n', 200)))).EnsureSuccessStatusCode();
        var spares = Assert.Single((await owner.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring"))!.Items);
        Assert.Equal(("Spares", ExpenseBucket.RepairsAndMaintenance, 200), (spares.Name, spares.Bucket!.Value, spares.Note!.Length));
    }

    [Fact]
    public async Task SchedulesStartNoEarlierThanTheFirstOfTheBusinessMonth()
    {
        await Setup();
        var parking = await ExpenseItemTestData.Id(owner, "Parking");

        Assert.Equal(HttpStatusCode.BadRequest, (await Create(Cost(parking, RecurrenceFrequency.Weekly, 1, start: new DateOnly(2026, 2, 28)))).StatusCode);
        var running = await Id(await Create(Cost(parking, RecurrenceFrequency.Weekly, 1, start: new DateOnly(2026, 3, 1))));
        var pending = await Id(await Create(Cost(parking, RecurrenceFrequency.Weekly, 1, start: new DateOnly(2026, 3, 20))));

        Assert.Equal(HttpStatusCode.BadRequest,
            (await owner.PutAsJsonAsync($"/setup/recurring/{pending}", Cost(parking, RecurrenceFrequency.Weekly, 1, start: new DateOnly(2026, 2, 20)))).StatusCode);
        (await owner.PutAsJsonAsync($"/setup/recurring/{pending}", Cost(parking, RecurrenceFrequency.Weekly, 1, start: new DateOnly(2026, 3, 2)))).EnsureSuccessStatusCode();
        (await owner.PutAsJsonAsync($"/setup/recurring/{running}", Cost(parking, RecurrenceFrequency.Weekly, 2, start: new DateOnly(2026, 3, 1)))).EnsureSuccessStatusCode();
    }

    [Fact]
    public async Task YearlyItemsPostOnTheirDayWithTheirBucket()
    {
        await Setup();
        await Id(await Create(Cost(await ExpenseItemTestData.Id(owner, "Insurance"), RecurrenceFrequency.Yearly, 10, month: 3, start: new DateOnly(2026, 3, 1))));

        var report = await owner.GetFromJsonAsync<VehicleReport>($"/setup/vehicles/{vehicle}/report?from=2026-03-01&through=2026-03-15");
        var posting = Assert.Single(report!.Postings);
        Assert.Equal((new DateOnly(2026, 3, 10), "Insurance", ExpenseBucket.RecurringCharges), (posting.Date, posting.Name, posting.Bucket!.Value));
        Assert.Equal(500m, report.Costs);
    }

    [Fact]
    public async Task LegacyDailyVersionsKeepPostingAndOnlyNewRevisionsFollowTheNewRules()
    {
        await Setup();
        // A Phase 1 item, saved daily under an old category before the rules changed.
        var legacy = Guid.Empty;
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
            var item = new RecurringItem(organizationId, new RecurringDefinition("Fuel", RecurringKind.Cost, CostCategory.RunningCosts, 100m,
                new RecurringSchedule(RecurrenceFrequency.Daily), new DateOnly(2026, 1, 1), null, [new VehicleShare(vehicle, 100m)]));
            db.Add(item);
            await db.SaveChangesAsync();
            legacy = item.Id;
        });

        var before = await owner.GetFromJsonAsync<VehicleReport>($"/setup/vehicles/{vehicle}/report?from=2026-03-01&through=2026-03-14");
        Assert.Equal(14, before!.Postings.Count);
        Assert.All(before.Postings, p => Assert.Equal(("Fuel", CostCategory.RunningCosts, ExpenseBucket.RecurringCharges), (p.Name, p.Category!.Value, p.Bucket!.Value)));

        var parking = await ExpenseItemTestData.Id(owner, "Parking");
        var start = new DateOnly(2026, 1, 1);
        Assert.Equal(HttpStatusCode.BadRequest,
            (await owner.PutAsJsonAsync($"/setup/recurring/{legacy}", Cost(parking, RecurrenceFrequency.Daily, null, start: start))).StatusCode);
        (await owner.PutAsJsonAsync($"/setup/recurring/{legacy}", Cost(parking, RecurrenceFrequency.Weekly, 0, start: start))).EnsureSuccessStatusCode();

        var after = await owner.GetFromJsonAsync<VehicleReport>($"/setup/vehicles/{vehicle}/report?from=2026-03-01&through=2026-03-15");
        Assert.Equal(before.Postings, after!.Postings.Take(14));
        var revised = after.Postings[14];
        Assert.Equal((Today, "Parking", 500m, ExpenseBucket.RecurringCharges), (revised.Date, revised.Name, revised.Amount, revised.Bucket!.Value));
        Assert.Null(revised.Category);

        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync($"/setup/recurring/{legacy}/stop", new StopRecurring(true, " "))).StatusCode);
    }

    [Theory]
    [InlineData("2027-03-14", true)]
    [InlineData("2027-03-13", false)]
    [InlineData("2027-04-14", false)]
    public void YearlyIsDueOnlyOnItsMonthAndDay(string date, bool due) =>
        Assert.Equal(due, new RecurringSchedule(RecurrenceFrequency.Yearly, 14, month: 3).IsDue(DateOnly.Parse(date)));

    [Fact]
    public void YearlyOnTheLastDayFollowsLeapYears()
    {
        var schedule = new RecurringSchedule(RecurrenceFrequency.Yearly, null, lastDay: true, month: 2);
        Assert.True(schedule.IsDue(new DateOnly(2028, 2, 29)));
        Assert.False(schedule.IsDue(new DateOnly(2028, 2, 28)));
        Assert.True(schedule.IsDue(new DateOnly(2027, 2, 28)));
        Assert.Throws<ArgumentException>(() => new RecurringSchedule(RecurrenceFrequency.Yearly, 5, lastDay: true, month: 2));
        Assert.Throws<ArgumentException>(() => new RecurringSchedule(RecurrenceFrequency.Weekly, 1, month: 2));
    }

    [Theory]
    [InlineData(CostCategory.RepairsAndUpkeep, ExpenseBucket.RepairsAndMaintenance)]
    [InlineData(CostCategory.RunningCosts, ExpenseBucket.RecurringCharges)]
    [InlineData(CostCategory.CrewCosts, ExpenseBucket.RecurringCharges)]
    [InlineData(CostCategory.FixedCommitments, ExpenseBucket.RecurringCharges)]
    public void LegacyCategoriesReportUnderTheirAssumedBucket(CostCategory category, ExpenseBucket bucket) =>
        Assert.Equal(bucket, ExpenseBuckets.FromLegacy(category));

    private static async Task<Guid> Id(HttpResponseMessage response)
    {
        using (response)
        {
            response.EnsureSuccessStatusCode();
            return (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetGuid();
        }
    }

    public void Dispose() { owner?.Dispose(); app.Dispose(); }
}
