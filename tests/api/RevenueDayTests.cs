using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Xunit;
using static Auth.Tests.RevenueTestData;

namespace Auth.Tests;

// Capture revenue for one day: every vehicle active that day, its record and the same day last week, saved together.
public sealed class RevenueDayTests : IDisposable
{
    private readonly AuthFactory app = new();
    // Signed in once by Arrange: a second sign-in of the same person in one test is refused.
    private HttpClient owner = null!;

    private sealed record Fleet(DateOnly Today, Guid Company, Guid A, Guid B, Guid C, Guid Other);

    // A has every day but last week's, which is a Garage day, and 1200 today; B has 1500 on the same day last week and
    // nothing since; C joined three days ago; D left yesterday; Other runs in a second company.
    private async Task<Fleet> Arrange()
    {
        await app.SeedDemo();
        var today = PinnedThursday(app);
        await SetBusinessDate(app, today);
        var company = await Company(app, "Day Capture Fleet");
        var second = await Company(app, "Second Day Fleet");
        var a = await Vehicle(app, company, "KDA 101A", today.AddDays(-20));
        await Records(app, a, today.AddDays(-10), today.AddDays(-1), 1000m, today.AddDays(-7));
        var b = await Vehicle(app, company, "KDA 102A", today.AddDays(-20));
        await Records(app, b, today.AddDays(-7), today.AddDays(-7), 1500m);
        var c = await Vehicle(app, company, "KDA 103A", today.AddDays(-3));
        await Vehicle(app, company, "KDA 104A", today.AddDays(-20), leftOn: today);
        var other = await Vehicle(app, second, "KDB 201A", today.AddDays(-20));
        owner = await app.SignIn(Owner);
        Assert.Equal(HttpStatusCode.OK, (await Put(owner, a, today.AddDays(-7), new { reason = "Garage" })).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await Put(owner, a, today, new { amount = 1200m })).StatusCode);
        return new(today, company, a, b, c, other);
    }

    [Fact]
    public async Task TheDayListsEveryActiveVehicleWithItsRecordAndTheSameDayLastWeek()
    {
        var fleet = await Arrange();

        var day = await Day(owner, $"?companyId={fleet.Company}");
        Assert.Equal((Text(fleet.Today), Text(fleet.Today), false),
            (day.GetProperty("date").GetString(), day.GetProperty("businessDate").GetString(), day.GetProperty("truncated").GetBoolean()));
        Assert.Equal([
            new RowView("KDA 101A", "amount", 1200m, 1, true, null, "Garage"),
            new RowView("KDA 102A", "missing", null, null, true, 1500m, null),
            new RowView("KDA 103A", "missing", null, null, true, null, null)], Rows(day));
        Assert.Equal(JsonValueKind.Null, Vehicles(day)[2].GetProperty("lastWeek").ValueKind);
        Assert.Equal(1000m, Vehicles(day)[1].GetProperty("day").GetProperty("expected").GetDecimal());

        var everyCompany = await Day(owner, "");
        Assert.Contains("KDB 201A", Vehicles(everyCompany).Select(x => x.GetProperty("registration").GetString()));

        var lastWeek = await Day(owner, $"?companyId={fleet.Company}&date={Text(fleet.Today.AddDays(-7))}");
        Assert.Equal([
            new RowView("KDA 101A", "reason", null, 1, true, null, null),
            new RowView("KDA 102A", "amount", 1500m, 1, true, null, null),
            new RowView("KDA 104A", "missing", null, null, true, null, null)], Rows(lastWeek));

        Assert.Equal(HttpStatusCode.BadRequest, (await owner.GetAsync($"/setup/revenue/day?date={Text(fleet.Today.AddDays(1))}")).StatusCode);

        // A clerk sees the vehicles in their own scope only.
        await ScopeToCompany(app, Clerk, fleet.Company);
        using var clerk = await app.SignIn(Clerk);
        Assert.Equal(["KDA 101A", "KDA 102A", "KDA 103A"],
            Vehicles(await Day(clerk, "")).Select(x => x.GetProperty("registration").GetString()));
    }

    [Fact]
    public async Task SavingADaySavesEveryRowAndAReplayChangesNothing()
    {
        var fleet = await Arrange();
        var logged = await RevenueChanges(owner);

        var rows = new object[]
        {
            new { vehicleId = fleet.A, amount = 1300m, version = 1 },
            new { vehicleId = fleet.B, amount = 900m },
            new { vehicleId = fleet.C, reason = "Other", note = "Flat tyre" }
        };
        var saved = await SaveDay(owner, fleet.Today, rows);
        Assert.Equal(HttpStatusCode.OK, saved.StatusCode);
        Assert.Equal([(fleet.A, 2L), (fleet.B, 1L), (fleet.C, 1L)], Saved(await Body(saved)));
        Assert.Equal(logged + 3, await RevenueChanges(owner));

        // The same rows again, with A's old version: identical to what is saved, so nothing changes or conflicts.
        var replay = await SaveDay(owner, fleet.Today, rows);
        Assert.Equal(HttpStatusCode.OK, replay.StatusCode);
        Assert.Equal([(fleet.A, 2L), (fleet.B, 1L), (fleet.C, 1L)], Saved(await Body(replay)));
        Assert.Equal(logged + 3, await RevenueChanges(owner));

        Assert.Equal([
            new RowView("KDA 101A", "amount", 1300m, 2, true, null, "Garage"),
            new RowView("KDA 102A", "amount", 900m, 1, true, 1500m, null),
            new RowView("KDA 103A", "reason", null, 1, true, null, null)], Rows(await Day(owner, $"?companyId={fleet.Company}")));
    }

    [Fact]
    public async Task ADayWithOneRefusedRowSavesNothingAndNamesTheVehicle()
    {
        var fleet = await Arrange();
        var b = new { vehicleId = fleet.B, amount = 900m };

        var noNote = await SaveDay(owner, fleet.Today, [b, new { vehicleId = fleet.C, reason = "Other" }]);
        Assert.Equal(HttpStatusCode.BadRequest, noNote.StatusCode);
        Assert.StartsWith("KDA 103A: ", Detail(await Body(noNote)));

        var stale = await SaveDay(owner, fleet.Today, [b, new { vehicleId = fleet.A, amount = 1300m }]);
        Assert.Equal(HttpStatusCode.Conflict, stale.StatusCode);
        var conflict = await Body(stale);
        Assert.Equal(fleet.A, conflict.GetProperty("vehicleId").GetGuid());
        Assert.Equal(1200m, conflict.GetProperty("current").GetProperty("amount").GetDecimal());
        Assert.StartsWith("KDA 101A was changed", Detail(conflict));

        var duplicate = await SaveDay(owner, fleet.Today, [b, b]);
        Assert.Equal("Each vehicle can be in the day only once.", Detail(await Body(duplicate)));
        Assert.Equal(HttpStatusCode.BadRequest, (await SaveDay(owner, fleet.Today, [])).StatusCode);
        var future = await SaveDay(owner, fleet.Today.AddDays(1), [b]);
        Assert.Equal("KDA 102A: Revenue cannot be recorded for a future date.", Detail(await Body(future)));

        // Nothing of the refused days was saved.
        Assert.Equal("missing", Vehicles(await Day(owner, $"?companyId={fleet.Company}"))[1].GetProperty("day").GetProperty("status").GetString());
    }

    [Fact]
    public async Task EachRowOfADayChecksTheSavePermissionsAndScope()
    {
        var fleet = await Arrange();
        await ScopeToCompany(app, Clerk, fleet.Company);
        using var clerk = await app.SignIn(Clerk);
        var yesterday = fleet.Today.AddDays(-1);

        // B has no record yesterday, but A's needs a correction, which a clerk may not make: neither is saved.
        var correction = await SaveDay(clerk, yesterday,
            [new { vehicleId = fleet.B, amount = 800m }, new { vehicleId = fleet.A, amount = 1100m, version = 1 }]);
        Assert.Equal(HttpStatusCode.Forbidden, correction.StatusCode);
        var day = await Day(clerk, $"?date={Text(yesterday)}");
        Assert.Equal("missing", Vehicles(day)[1].GetProperty("day").GetProperty("status").GetString());
        // A clerk can capture B's missing day but not change A's recorded one.
        Assert.Equal([false, true], Vehicles(day).Take(2).Select(x => x.GetProperty("day").GetProperty("canEdit").GetBoolean()));

        Assert.Equal(HttpStatusCode.NotFound, (await SaveDay(clerk, fleet.Today, [new { vehicleId = fleet.Other, amount = 800m }])).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await SaveDay(clerk, yesterday, [new { vehicleId = fleet.B, amount = 800m }])).StatusCode);
    }

    private static string Text(DateOnly date) => date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    private static Task<HttpResponseMessage> Put(HttpClient client, Guid vehicle, DateOnly date, object body) =>
        client.PutAsJsonAsync($"/setup/revenue/{vehicle}/{Text(date)}", body);

    private static Task<HttpResponseMessage> SaveDay(HttpClient client, DateOnly date, object[] rows) =>
        client.PutAsJsonAsync($"/setup/revenue/day/{Text(date)}", new { rows });

    private static async Task<JsonElement> Day(HttpClient client, string query)
    {
        var response = await client.GetAsync("/setup/revenue/day" + query);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        return await Body(response);
    }

    private static JsonElement[] Vehicles(JsonElement day) => day.GetProperty("vehicles").EnumerateArray().ToArray();

    private static decimal? Amount(JsonElement value) => value.ValueKind == JsonValueKind.Null ? null : value.GetDecimal();

    private sealed record RowView(string? Registration, string? Status, decimal? Amount, long? Version, bool CanEdit,
        decimal? LastWeekAmount, string? LastWeekReason);

    private static RowView[] Rows(JsonElement day) =>
        Vehicles(day).Select(row =>
        {
            var cell = row.GetProperty("day");
            var lastWeek = row.GetProperty("lastWeek");
            (decimal? Amount, string? Reason) before = lastWeek.ValueKind == JsonValueKind.Null ? (null, null)
                : (Amount(lastWeek.GetProperty("amount")), lastWeek.GetProperty("reason").GetString());
            var version = cell.GetProperty("version");
            return new RowView(row.GetProperty("registration").GetString(), cell.GetProperty("status").GetString(), Amount(cell.GetProperty("amount")),
                version.ValueKind == JsonValueKind.Null ? (long?)null : version.GetInt64(), cell.GetProperty("canEdit").GetBoolean(),
                before.Amount, before.Reason);
        }).ToArray();

    private static (Guid, long)[] Saved(JsonElement body) =>
        body.GetProperty("rows").EnumerateArray().Select(x => (x.GetProperty("vehicleId").GetGuid(), x.GetProperty("version").GetInt64())).ToArray();

    private static async Task<int> RevenueChanges(HttpClient client) =>
        (await client.GetFromJsonAsync<JsonElement>("/setup/history?pageSize=100&section=revenue")).GetProperty("total").GetInt32();

    private static Task<JsonElement> Body(HttpResponseMessage response) => response.Content.ReadFromJsonAsync<JsonElement>();

    private static string? Detail(JsonElement problem) => problem.GetProperty("detail").GetString();

    public void Dispose()
    {
        owner?.Dispose();
        app.Dispose();
    }
}
