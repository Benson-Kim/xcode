using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application.Setup;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;
using Xunit;
using static Auth.Tests.RevenueTestData;

namespace Auth.Tests;

// The business date starts on Tuesday 31 March 2026. Engine fund saves 1,000 on KDA 482M and 500 on KDB 111A every
// Friday (6, 13, 20 and 27 March); Parking costs 300 on KDA 482M every Monday. Both started on 1 March.
public sealed class RecurringPauseTests : IDisposable
{
    private static readonly DateOnly Today = new(2026, 3, 31);
    private static readonly DateOnly Start = new(2026, 3, 1);
    private readonly AuthFactory app = new();

    private sealed record World(HttpClient Owner, Guid A, Guid B, Guid Saving, Guid Parking);

    private async Task<World> Arrange()
    {
        await app.SeedDemo();
        await SetBusinessDate(app, Today);
        var company = await Company(app, "Pause Fleet");
        var a = await Vehicle(app, company, "KDA 482M", new DateOnly(2026, 2, 1));
        var b = await Vehicle(app, company, "KDB 111A", new DateOnly(2026, 2, 1));
        var saving = await Save(o => new RecurringItem(o, new RecurringDefinition("Engine fund", RecurringKind.Savings, 1500m,
            new RecurringSchedule(RecurrenceFrequency.Weekly, 5), Start, null, [new(a, 1000m), new(b, 500m)])));
        var parking = await Save(o => new RecurringItem(o, new RecurringDefinition("Parking", RecurringKind.Cost, 300m,
            new RecurringSchedule(RecurrenceFrequency.Weekly, 1), Start, null, [new(a, 300m)], null, ExpenseBucket.RecurringCharges)));
        return new(await app.SignIn(Owner), a, b, saving, parking);
    }

    [Fact]
    public async Task ASavingShowsItsLastRunBalanceAndRuns()
    {
        var w = await Arrange();

        var listed = Assert.Single((await List(w.Owner, "savings")).Items);
        Assert.Equal((new DateOnly(2026, 3, 27), 2, 6000m, (DateOnly?)null), (listed.LastRun, listed.LastRunVehicles, listed.Balance, listed.PausedFrom));
        var cost = Assert.Single((await List(w.Owner, "cost")).Items);
        Assert.Equal(((DateOnly?)null, (decimal?)null), (cost.LastRun, cost.Balance));

        var runs = (await w.Owner.GetFromJsonAsync<RecurringRunsDto>($"/setup/recurring/{w.Saving}/runs"))!;
        Assert.Equal(("Engine fund", Start, 6000m, 4), (runs.Name, runs.Start, runs.Total, runs.RunCount));
        Assert.Equal([27, 20, 13, 6], runs.Runs.Select(r => r.Date.Day));
        Assert.Equal([("KDA 482M", 1000m), ("KDB 111A", 500m)], runs.Runs[0].Shares.Select(s => (s.Registration, s.Amount)));
        Assert.Equal(1500m, runs.Runs[0].Amount);
        Assert.Equal(HttpStatusCode.NotFound, (await w.Owner.GetAsync($"/setup/recurring/{Guid.NewGuid()}/runs")).StatusCode);

        // March: five Mondays of parking, four Fridays saved.
        var march = (await w.Owner.GetFromJsonAsync<RecurringSummaryDto>("/setup/recurring/summary"))!;
        Assert.Equal(new RecurringSummaryDto(Start, Today, 1500m, 6000m, 6000m), march);
    }

    [Fact]
    public async Task APausedItemSkipsItsRunsUntilResumedAndThenRunsAgain()
    {
        var w = await Arrange();

        using (var paused = await w.Owner.PostAsync($"/setup/recurring/{w.Saving}/pause", null))
            Assert.Equal(HttpStatusCode.OK, paused.StatusCode);
        // Pausing again changes nothing.
        using (var again = await w.Owner.PostAsync($"/setup/recurring/{w.Saving}/pause", null))
            Assert.Equal(HttpStatusCode.OK, again.StatusCode);
        Assert.Equal(Today, Assert.Single((await List(w.Owner, "savings")).Items).PausedFrom);

        // Two weeks on: Fridays 3 and 10 April did not run. Parking ran on Mondays 6 and 13 and still runs 20 and 27.
        await SetBusinessDate(app, new DateOnly(2026, 4, 14));
        var april = (await w.Owner.GetFromJsonAsync<RecurringSummaryDto>("/setup/recurring/summary"))!;
        Assert.Equal(new RecurringSummaryDto(new DateOnly(2026, 4, 1), new DateOnly(2026, 4, 30), 1200m, 0m, 6000m), april);
        var whilePaused = Assert.Single((await List(w.Owner, "savings")).Items);
        Assert.Equal((new DateOnly(2026, 3, 27), 6000m), (whilePaused.LastRun, whilePaused.Balance));

        using (var resumed = await w.Owner.PostAsync($"/setup/recurring/{w.Saving}/resume", null))
            Assert.Equal(HttpStatusCode.OK, resumed.StatusCode);
        await SetBusinessDate(app, new DateOnly(2026, 4, 18));
        var running = Assert.Single((await List(w.Owner, "savings")).Items);
        Assert.Equal(((DateOnly?)null, new DateOnly(2026, 4, 17), 7500m), (running.PausedFrom, running.LastRun, running.Balance));
        Assert.Equal([17, 27, 20], (await w.Owner.GetFromJsonAsync<RecurringRunsDto>($"/setup/recurring/{w.Saving}/runs"))!
            .Runs.Take(3).Select(r => r.Date.Day));

        // The vehicle reports count only the runs that happened: one Friday in April.
        var report = (await w.Owner.GetFromJsonAsync<VehicleReport>($"/setup/vehicles/{w.A}/report?from=2026-04-01&through=2026-04-18"))!;
        Assert.Equal(1000m, report.Savings);

        string[] reasons = [];
        await app.WithDb(async db => reasons = await db.Set<OrganizationSettingsVersion>().IgnoreQueryFilters()
            .Where(v => v.Section == "recurring").OrderBy(v => v.Version).Select(v => v.Reason).ToArrayAsync());
        Assert.Equal(["Paused Engine fund from 2026-03-31", "Resumed Engine fund from 2026-04-14"], reasons);
    }

    [Fact]
    public async Task ResumingOnTheDayItWasPausedSkipsNothing()
    {
        var w = await Arrange();
        await SetBusinessDate(app, new DateOnly(2026, 4, 3));
        (await w.Owner.PostAsync($"/setup/recurring/{w.Saving}/pause", null)).EnsureSuccessStatusCode();
        (await w.Owner.PostAsync($"/setup/recurring/{w.Saving}/resume", null)).EnsureSuccessStatusCode();
        // Resuming an item that runs changes nothing.
        (await w.Owner.PostAsync($"/setup/recurring/{w.Saving}/resume", null)).EnsureSuccessStatusCode();

        var item = Assert.Single((await List(w.Owner, "savings")).Items);
        Assert.Equal(((DateOnly?)null, new DateOnly(2026, 4, 3), 7500m), (item.PausedFrom, item.LastRun, item.Balance));
    }

    [Fact]
    public async Task OnlyAnEditorWhoSeesEveryVehicleMayPauseAndAStoppedItemCannotBePaused()
    {
        var w = await Arrange();
        using (var stop = await w.Owner.PostAsJsonAsync($"/setup/recurring/{w.Parking}/stop", new { confirmed = true, reason = "Moved to a stage" }))
            Assert.Equal(HttpStatusCode.OK, stop.StatusCode);
        using (var refused = await w.Owner.PostAsync($"/setup/recurring/{w.Parking}/pause", null))
        {
            Assert.Equal(HttpStatusCode.BadRequest, refused.StatusCode);
            Assert.Equal("The item is already stopped.", (await refused.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString());
        }

        using var clerk = await app.SignIn(Clerk);
        Assert.Equal(HttpStatusCode.Forbidden, (await clerk.PostAsync($"/setup/recurring/{w.Saving}/pause", null)).StatusCode);
        Assert.Null(Assert.Single((await List(w.Owner, "savings")).Items).PausedFrom);
    }

    private static async Task<Page<RecurringDto>> List(HttpClient client, string kind) =>
        (await client.GetFromJsonAsync<Page<RecurringDto>>($"/setup/recurring?kind={kind}"))!;

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

    public void Dispose() => app.Dispose();
}
