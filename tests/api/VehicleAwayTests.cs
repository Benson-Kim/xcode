using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Xunit;
using static Auth.Tests.RevenueTestData;

namespace Auth.Tests;

// D4: recorded revenue never disappears. Restoring a vehicle whose leave already took effect records the stretch it
// was away, and those days are neither expected nor missing. The business date T is a pinned Thursday, so the
// Monday-first week runs from T-3 to T+3.
public sealed class VehicleAwayTests : IDisposable
{
    private readonly AuthFactory app = new();

    private async Task<(DateOnly Today, Guid Company)> Arrange()
    {
        await app.SeedDemo();
        var today = PinnedThursday(app);
        await SetBusinessDate(app, today);
        return (today, await Company(app, "Away Fleet"));
    }

    [Fact]
    public async Task RestoringAVehicleRecordsTheDaysItWasAwayAndNamesThemInTheChangeLog()
    {
        var (today, company) = await Arrange();
        var vehicle = await Vehicle(app, company, "KAA 101A", today.AddDays(-20));
        using var owner = await app.SignIn(Owner);

        Assert.Equal(HttpStatusCode.OK, (await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/retire", new { leftOn = Text(today.AddDays(-5)) })).StatusCode);
        // No return date: it comes back on the business date.
        Assert.Equal(HttpStatusCode.OK, (await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/restore", new { })).StatusCode);

        var row = await Row(owner, vehicle);
        Assert.Null(row.GetProperty("leftOn").GetString());
        Assert.True(row.GetProperty("active").GetBoolean());
        var away = Assert.Single(row.GetProperty("away").EnumerateArray());
        Assert.Equal(Text(today.AddDays(-5)), away.GetProperty("leftOn").GetString());
        Assert.Equal(Text(today), away.GetProperty("returnedOn").GetString());

        // The change log is the only place the away days are stated in words, so it names both ends.
        var reason = (await owner.GetFromJsonAsync<JsonElement>("/setup/history?page=1&pageSize=1"))
            .GetProperty("items")[0].GetProperty("reason").GetString();
        Assert.Contains($"returned to the fleet on {Text(today)}", reason);
        Assert.Contains($"away from {Text(today.AddDays(-5))} to {Text(today.AddDays(-1))}", reason);
    }

    [Fact]
    public async Task AwayDaysAreNeitherExpectedNorMissingInTheWeekTheDashboardOrTheReport()
    {
        var (today, company) = await Arrange();
        var monday = today.AddDays(-3);
        // Away for Tuesday and Wednesday, back on the business date; the week has records on Monday and today.
        var vehicle = await Vehicle(app, company, "KAB 202B", today.AddDays(-20), away: (monday.AddDays(1), today));
        await Records(app, vehicle, today.AddDays(-20), monday, 1000m);
        await Records(app, vehicle, today, today, 1000m);
        using var owner = await app.SignIn(Owner);

        var week = (await owner.GetFromJsonAsync<JsonElement>($"/setup/revenue?vehicleId={vehicle}")).GetProperty("vehicles")[0];
        var cells = week.GetProperty("days").EnumerateArray().ToDictionary(x => x.GetProperty("date").GetString()!);
        Assert.Equal("amount", cells[Text(monday)].GetProperty("status").GetString());
        Assert.Equal("none", cells[Text(monday.AddDays(1))].GetProperty("status").GetString());
        Assert.Equal("none", cells[Text(monday.AddDays(2))].GetProperty("status").GetString());
        Assert.Equal("amount", cells[Text(today)].GetProperty("status").GetString());
        // Two days away carry no expected figure, so the week expects two days of the weekly target, not four.
        Assert.Equal(0m, cells[Text(monday.AddDays(1))].GetProperty("expected").GetDecimal());
        Assert.Equal(decimal.Round(7000m / 7m, 2) * 2, week.GetProperty("totalExpected").GetDecimal());
        // Nothing is missing: the only days in the fleet this week both have a record.
        Assert.Null(week.GetProperty("earliestMissing").GetString());

        var dashboard = await owner.GetFromJsonAsync<JsonElement>("/setup/revenue/dashboard?period=week");
        Assert.Equal(0, dashboard.GetProperty("missingDays").GetInt32());
        Assert.Equal(0, dashboard.GetProperty("missingVehicles").GetInt32());

        // The vehicle's own report expects the same days the revenue grid does.
        var report = await owner.GetFromJsonAsync<JsonElement>(
            $"/setup/vehicles/{vehicle}/report?from={Text(monday)}&through={Text(today)}");
        Assert.Equal(2000m, report.GetProperty("moneyIn").GetDecimal());
        Assert.Equal(decimal.Round(7000m / 7m * 2, 2), report.GetProperty("target").GetDecimal());
    }

    [Fact]
    public async Task ADayTheVehicleWasAwayCannotBeCapturedAndDoesNotHoldUpTheDaysAfterIt()
    {
        var (today, company) = await Arrange();
        var joined = today.AddDays(-10);
        // Away for the two days before the business date, so the earliest missing day must step over them.
        var vehicle = await Vehicle(app, company, "KAC 303C", joined, away: (today.AddDays(-2), today));
        await Records(app, vehicle, joined, today.AddDays(-4), 1000m);
        using var owner = await app.SignIn(Owner);

        var refused = await owner.PutAsJsonAsync($"/setup/revenue/{vehicle}/{Text(today.AddDays(-1))}", new { amount = 900m });
        Assert.Equal(HttpStatusCode.BadRequest, refused.StatusCode);
        Assert.Contains("away from the fleet", (await refused.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString());

        // T-3 is the open day: the last recorded day was T-4, and T-2 and T-1 were away.
        var row = await WeekRow(owner, vehicle);
        Assert.Equal(Text(today.AddDays(-3)), row.GetProperty("earliestMissing").GetString());

        Assert.Equal(HttpStatusCode.OK, (await owner.PutAsJsonAsync($"/setup/revenue/{vehicle}/{Text(today.AddDays(-3))}", new { amount = 900m })).StatusCode);
        // With the hole filled nothing earlier is missing, so the business date opens even though two away days
        // sit between it and the last record.
        var filled = await WeekRow(owner, vehicle);
        Assert.Null(filled.GetProperty("earliestMissing").GetString());
        Assert.True(filled.GetProperty("days").EnumerateArray()
            .Single(x => x.GetProperty("date").GetString() == Text(today)).GetProperty("canEdit").GetBoolean());
    }

    [Fact]
    public async Task AReturnDateOutsideTheTimeAwayIsRefused()
    {
        var (today, company) = await Arrange();
        var vehicle = await Vehicle(app, company, "KAD 404D", today.AddDays(-20));
        using var owner = await app.SignIn(Owner);
        await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/retire", new { leftOn = Text(today.AddDays(-5)) });

        foreach (var date in new[] { today.AddDays(-6), today.AddDays(1) })
        {
            var refused = await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/restore", new { returnedOn = Text(date) });
            Assert.Equal(HttpStatusCode.BadRequest, refused.StatusCode);
        }
        // The day it left is allowed and undoes the leave outright, leaving no stretch behind.
        Assert.Equal(HttpStatusCode.OK, (await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/restore",
            new { returnedOn = Text(today.AddDays(-5)) })).StatusCode);
        Assert.Empty((await Row(owner, vehicle)).GetProperty("away").EnumerateArray());
    }

    private static string Text(DateOnly date) => date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    private static async Task<JsonElement> Row(HttpClient client, Guid vehicle) =>
        (await client.GetFromJsonAsync<JsonElement>("/setup/vehicles?page=1&pageSize=50")).GetProperty("items")
        .EnumerateArray().Single(x => x.GetProperty("id").GetGuid() == vehicle);

    private static async Task<JsonElement> WeekRow(HttpClient client, Guid vehicle) =>
        (await client.GetFromJsonAsync<JsonElement>($"/setup/revenue?vehicleId={vehicle}")).GetProperty("vehicles")[0];

    public void Dispose() => app.Dispose();
}
