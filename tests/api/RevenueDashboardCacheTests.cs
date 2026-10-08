using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application.Revenue;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Xunit;
using Xunit.Abstractions;
using static Auth.Tests.RevenueTestData;

namespace Auth.Tests;

// Dashboard figures are kept per organization, settings version, business date, period, company filter and data scope,
// and masked per request after the cache.
public sealed class RevenueDashboardCacheTests(ITestOutputHelper output) : IDisposable
{
    private static readonly RevenueDashboardDto Figures = new("week", new(2026, 3, 2), new(2026, 3, 5), new(2026, 3, 5),
        2000m, 4000m, 50, 0, 1, 1, 1, 0);

    private readonly AuthFactory app = new();

    [Fact]
    public async Task ARepeatedDashboardIsServedFromTheCache()
    {
        var (_, company, _) = await Arrange();
        using var owner = await app.SignIn(Owner);
        await Dashboard(owner, "today");

        foreach (var filter in new Guid?[] { null, company })
        {
            var miss = await Measure(() => Dashboard(owner, "week", filter));
            var hit = await Measure(() => Dashboard(owner, "week", filter));
            output.WriteLine($"week dashboard, company {filter?.ToString() ?? "all"}: miss {miss.Commands} commands, hit {hit.Commands}");
            Assert.True(hit.Commands < miss.Commands, $"A hit issued {hit.Commands} commands and a miss {miss.Commands}.");
            Assert.Equal(miss.Figures.GetRawText(), hit.Figures.GetRawText());
            Assert.Equal(2000m, hit.Figures.GetProperty("revenue").GetDecimal());
        }
    }

    [Fact]
    public async Task SavingRevenueGivesFreshFigures()
    {
        var (today, _, vehicle) = await Arrange();
        using var owner = await app.SignIn(Owner);

        var (before, after) = await AroundChange(owner, () => owner.PutAsJsonAsync($"/setup/revenue/{vehicle}/{Text(today.AddDays(-1))}", new { amount = 500m }));
        Assert.Equal((2000m, 1), (before.GetProperty("revenue").GetDecimal(), before.GetProperty("missingDays").GetInt32()));
        Assert.Equal((2500m, 0), (after.GetProperty("revenue").GetDecimal(), after.GetProperty("missingDays").GetInt32()));
    }

    [Fact]
    public async Task RetiringAVehicleGivesFreshFigures()
    {
        var (today, _, vehicle) = await Arrange();
        using var owner = await app.SignIn(Owner);

        var (before, after) = await AroundChange(owner, () => owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/retire", new { leftOn = Text(today.AddDays(-1)) }));
        // Leaving from yesterday takes yesterday out of the expected revenue and the gaps.
        Assert.Equal((3000m, 1), (before.GetProperty("expected").GetDecimal(), before.GetProperty("missingDays").GetInt32()));
        Assert.Equal((2000m, 0), (after.GetProperty("expected").GetDecimal(), after.GetProperty("missingDays").GetInt32()));
    }

    [Fact]
    public async Task MovingTheBusinessDateGivesFreshFigures()
    {
        var (today, _, _) = await Arrange();
        using var owner = await app.SignIn(Owner);

        var (before, after) = await AroundChange(owner, () => owner.PutAsJsonAsync("/setup/organization/settings/businessDate", new { value = Text(today.AddDays(1)) }));
        Assert.Equal(Text(today), before.GetProperty("businessDate").GetString());
        Assert.Equal(Text(today.AddDays(1)), after.GetProperty("businessDate").GetString());
        // The old business date joins the expected and the missing days.
        Assert.Equal((3000m, 1), (before.GetProperty("expected").GetDecimal(), before.GetProperty("missingDays").GetInt32()));
        Assert.Equal((4000m, 2), (after.GetProperty("expected").GetDecimal(), after.GetProperty("missingDays").GetInt32()));
    }

    [Fact]
    public async Task ChangingTheFirstDayOfTheWeekGivesFreshFigures()
    {
        var (today, _, _) = await Arrange();
        using var owner = await app.SignIn(Owner);

        var (before, after) = await AroundChange(owner, () => owner.PutAsJsonAsync("/setup/organization/settings/localization",
            new { value = new { timeZone = "UTC", firstDayOfWeek = (int)DayOfWeek.Thursday } }));
        // A week that starts on the business date leaves Monday's and Tuesday's revenue out.
        Assert.Equal((Text(today.AddDays(-3)), 2000m), (before.GetProperty("from").GetString(), before.GetProperty("revenue").GetDecimal()));
        Assert.Equal((Text(today), 0m), (after.GetProperty("from").GetString(), after.GetProperty("revenue").GetDecimal()));
    }

    [Fact]
    public async Task MovingAVehicleToAnotherCompanyGivesFreshFigures()
    {
        var (today, company, vehicle) = await Arrange();
        var other = await Company(app, "Other Cache Fleet");
        using var owner = await app.SignIn(Owner);

        var (before, after) = await AroundChange(owner, () => owner.PutAsJsonAsync($"/setup/vehicles/{vehicle}",
            new { companyId = other, registration = "KAA 501A", joinedOn = Text(today.AddDays(-10)), weeklyTarget = 7000m }), company);
        // The company's only vehicle has left it, and its figures with it.
        Assert.Equal((2000m, 1), (before.GetProperty("revenue").GetDecimal(), before.GetProperty("missingDays").GetInt32()));
        Assert.Equal((0m, 0), (after.GetProperty("revenue").GetDecimal(), after.GetProperty("missingDays").GetInt32()));
    }

    // Both orders: whoever fills an entry first, the other never reads it.
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task TheOwnerAndAClerkScopedToOneCompanyKeepTheirOwnFigures(bool ownerFirst)
    {
        var (today, company, _) = await Arrange();
        var other = await Company(app, "Other Cache Fleet");
        foreach (var registration in new[] { "KAA 511A", "KAA 512A" })
            await Records(app, await Vehicle(app, other, registration, today.AddDays(-10)), today.AddDays(-10), today.AddDays(-3));
        await ScopeToCompany(app, Clerk, company);
        using var owner = await app.SignIn(Owner);
        using var clerk = await app.SignIn(Clerk);

        JsonElement ownerFigures, clerkFigures;
        if (ownerFirst)
        {
            ownerFigures = await Dashboard(owner, "week");
            clerkFigures = await Dashboard(clerk, "week");
        }
        else
        {
            clerkFigures = await Dashboard(clerk, "week");
            ownerFigures = await Dashboard(owner, "week");
        }

        // The clerk's company misses yesterday; the other company's two vehicles miss Tuesday and yesterday.
        Assert.Equal((5, 3), Gaps(ownerFigures));
        Assert.Equal(4000m, ownerFigures.GetProperty("revenue").GetDecimal());
        Assert.Equal((1, 1), Gaps(clerkFigures));
        Assert.Equal(1, clerkFigures.GetProperty("vehiclesToday").GetInt32());
    }

    // The office admin reaches every company, as the owner does, so the two share an entry; only the owner sees revenue.
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ASharedEntryShowsEachViewerOnlyTheirOwnCards(bool ownerFirst)
    {
        await Arrange();
        await Grant(app, Admin, "dash.gaps");
        await Deny(app, Admin, "dash.revenue");
        using var owner = await app.SignIn(Owner);
        using var admin = await app.SignIn(Admin);
        await Dashboard(owner, "today");
        await Dashboard(admin, "today");

        var (first, second) = ownerFirst ? (owner, admin) : (admin, owner);
        var miss = await Measure(() => Dashboard(first, "week"));
        var hit = await Measure(() => Dashboard(second, "week"));
        output.WriteLine($"week dashboard: {(ownerFirst ? "owner" : "admin")} miss {miss.Commands} commands, {(ownerFirst ? "admin" : "owner")} hit {hit.Commands}");
        Assert.True(hit.Commands < miss.Commands, $"The second viewer issued {hit.Commands} commands and the first {miss.Commands}.");
        var (ownerFigures, adminFigures) = ownerFirst ? (miss.Figures, hit.Figures) : (hit.Figures, miss.Figures);

        Assert.Equal((2000m, 3000m, 67), (ownerFigures.GetProperty("revenue").GetDecimal(), ownerFigures.GetProperty("expected").GetDecimal(),
            ownerFigures.GetProperty("percent").GetInt32()));
        foreach (var hidden in new[] { "revenue", "expected", "percent" })
            Assert.Equal(JsonValueKind.Null, adminFigures.GetProperty(hidden).ValueKind);
        Assert.Equal((1, 1), Gaps(adminFigures));
    }

    [Fact]
    public async Task TwoOrganizationsNeverShareAnEntry()
    {
        using var cache = new RevenueDashboardCache();
        var first = Actor();
        var second = first with { OrganizationId = Guid.NewGuid() };
        var secondFigures = Figures with { Revenue = 9000m };
        var computed = 0;
        Func<Task<RevenueDashboardDto>> Compute(RevenueDashboardDto figures) => () =>
        {
            computed++;
            return Task.FromResult(figures);
        };

        Assert.Same(Figures, await cache.Get(first, "week", null, Compute(Figures), CancellationToken.None));
        Assert.Same(secondFigures, await cache.Get(second, "week", null, Compute(secondFigures), CancellationToken.None));
        Assert.Same(Figures, await cache.Get(first, "week", null, Compute(secondFigures), CancellationToken.None));
        Assert.Same(secondFigures, await cache.Get(second, "week", null, Compute(Figures), CancellationToken.None));
        Assert.Equal(2, computed);
    }

    [Fact]
    public async Task ConcurrentRequestsForOneEntryWorkTheFiguresOutOnce()
    {
        using var cache = new RevenueDashboardCache();
        var actor = Actor();
        const int Callers = 16;
        var computed = 0;
        var entered = 0;
        var allWaiting = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource<RevenueDashboardDto>(TaskCreationOptions.RunContinuationsAsynchronously);

        var callers = Enumerable.Range(0, Callers).Select(_ => Task.Run(() =>
        {
            var pending = cache.Get(actor, "week", null, () =>
            {
                Interlocked.Increment(ref computed);
                return release.Task;
            }, CancellationToken.None);
            if (Interlocked.Increment(ref entered) == Callers) allWaiting.SetResult();
            return pending;
        })).ToArray();
        await allWaiting.Task.WaitAsync(TimeSpan.FromSeconds(10));
        release.SetResult(Figures);

        Assert.All(await Task.WhenAll(callers), x => Assert.Same(Figures, x));
        Assert.Equal(1, computed);
    }

    [Fact]
    public async Task AFailedComputationIsNotKept()
    {
        using var cache = new RevenueDashboardCache();
        var actor = Actor();
        var failing = new TaskCompletionSource<RevenueDashboardDto>(TaskCreationOptions.RunContinuationsAsynchronously);
        var computed = 0;
        Task<RevenueDashboardDto> Compute() => Interlocked.Increment(ref computed) == 1 ? failing.Task : Task.FromResult(Figures);

        var first = cache.Get(actor, "week", null, Compute, CancellationToken.None);
        var waiter = cache.Get(actor, "week", null, Compute, CancellationToken.None);
        failing.SetException(new InvalidOperationException("The database went away."));

        await Assert.ThrowsAsync<InvalidOperationException>(() => first);
        // The waiter is not handed the failure: it works the figures out itself.
        Assert.Same(Figures, await waiter);
        Assert.Equal(2, computed);
        // The next request computes again, and that answer is kept.
        Assert.Same(Figures, await cache.Get(actor, "week", null, Compute, CancellationToken.None));
        Assert.Same(Figures, await cache.Get(actor, "week", null, Compute, CancellationToken.None));
        Assert.Equal(3, computed);
    }

    [Fact]
    public async Task AWaiterThatIsCancelledLeavesTheComputationToTheOthers()
    {
        using var cache = new RevenueDashboardCache();
        var actor = Actor();
        var computed = 0;
        var release = new TaskCompletionSource<RevenueDashboardDto>(TaskCreationOptions.RunContinuationsAsynchronously);
        Task<RevenueDashboardDto> Compute()
        {
            Interlocked.Increment(ref computed);
            return release.Task;
        }

        var first = cache.Get(actor, "week", null, Compute, CancellationToken.None);
        using var leaving = new CancellationTokenSource();
        var cancelled = cache.Get(actor, "week", null, Compute, leaving.Token);
        var patient = cache.Get(actor, "week", null, Compute, CancellationToken.None);
        leaving.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => cancelled);
        Assert.False(first.IsCompleted);
        Assert.False(patient.IsCompleted);
        release.SetResult(Figures);
        Assert.Same(Figures, await first);
        Assert.Same(Figures, await patient);
        Assert.Same(Figures, await cache.Get(actor, "week", null, Compute, CancellationToken.None));
        Assert.Equal(1, computed);
    }

    [Fact]
    public async Task WithoutASettingsVersionNothingIsKept()
    {
        using var cache = new RevenueDashboardCache();
        var actor = Actor() with { SettingsVersion = null };
        var computed = 0;
        Task<RevenueDashboardDto> Compute()
        {
            computed++;
            return Task.FromResult(Figures);
        }

        Assert.Same(Figures, await cache.Get(actor, "week", null, Compute, CancellationToken.None));
        Assert.Same(Figures, await cache.Get(actor, "week", null, Compute, CancellationToken.None));
        Assert.Equal(2, computed);
    }

    // A Thursday business date in a week that starts on Monday: Monday and Tuesday are recorded and Wednesday is missing.
    // The business date itself is not yet expected or missing.
    private async Task<(DateOnly Today, Guid Company, Guid Vehicle)> Arrange()
    {
        await app.SeedDemo();
        var today = PinnedThursday(app);
        await SetBusinessDate(app, today);
        await SetFirstDayOfWeek(app, DayOfWeek.Monday);
        var company = await Company(app, "Cache Fleet");
        var vehicle = await Vehicle(app, company, "KAA 501A", today.AddDays(-10));
        await Records(app, vehicle, today.AddDays(-10), today.AddDays(-2));
        return (today, company, vehicle);
    }

    // Fills the entry, makes the change over HTTP, and returns the figures from before and after it.
    private async Task<(JsonElement Before, JsonElement After)> AroundChange(HttpClient owner, Func<Task<HttpResponseMessage>> change,
        Guid? companyId = null)
    {
        var before = await Dashboard(owner, "week", companyId);
        var version = await SettingsVersion();
        using (var response = await change())
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.True(await SettingsVersion() > version, "The change did not move the settings version.");
        return (before, await Dashboard(owner, "week", companyId));
    }

    private async Task<(JsonElement Figures, int Commands)> Measure(Func<Task<JsonElement>> request)
    {
        app.Database.Reset();
        var figures = await request();
        return (figures, app.Database.Commands);
    }

    private async Task<long> SettingsVersion()
    {
        long version = 0;
        await app.WithDb(async db => version = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).SettingsVersion);
        return version;
    }

    private static Task<JsonElement> Dashboard(HttpClient client, string period, Guid? companyId = null) =>
        client.GetFromJsonAsync<JsonElement>($"/setup/revenue/dashboard?period={period}" + (companyId is { } id ? $"&companyId={id}" : ""));

    private static (int Days, int Vehicles) Gaps(JsonElement figures) =>
        (figures.GetProperty("missingDays").GetInt32(), figures.GetProperty("missingVehicles").GetInt32());

    private static SetupActor Actor() => new(Guid.NewGuid(), Guid.NewGuid(), new DateOnly(2026, 3, 5), true, [], [], "cache",
        new HashSet<string>(), SettingsVersion: 1);

    private static string Text(DateOnly date) => date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    public void Dispose() => app.Dispose();
}
