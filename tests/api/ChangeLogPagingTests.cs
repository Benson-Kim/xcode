using System.Net;
using System.Net.Http.Json;
using Auth.Api.Infrastructure.Migrations;
using Auth.Application;
using Auth.Application.Setup;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;
using Xunit;
using Xunit.Abstractions;

namespace Auth.Tests;

// The change log pages by version as well as by number, counts each scope and filter once per change, shows scoped
// viewers revenue for the vehicles they can see today, and costs the same however long it grows.
public sealed class ChangeLogPagingTests(ITestOutputHelper output) : IDisposable
{
    private readonly AuthFactory app = new();
    private const string Owner = "antony.maina@shamayah.co.ke";
    private const string RevenueClerk = "wanjiru.kamau@zurigenesis.co.ke";

    private sealed record IdResponse(Guid Id);

    private static async Task<Guid> Id(HttpResponseMessage response)
    {
        response.EnsureSuccessStatusCode();
        return (await response.Content.ReadFromJsonAsync<IdResponse>())!.Id;
    }

    private static async Task<HistoryPage> Log(HttpClient client, string query) =>
        (await client.GetFromJsonAsync<HistoryPage>($"/setup/history?{query}"))!;

    // Writes count change-log rows straight to the database, each with the organization's next version, as a save would.
    private Task AddChanges(int count, string section = "expenses") => app.WithDb(async db =>
    {
        db.Provisioning = true;
        var organization = await db.Organizations.IgnoreQueryFilters().SingleAsync();
        var actor = (await db.Users.SingleAsync(x => x.Email == Owner)).Id;
        for (var i = 0; i < count; i++)
        {
            organization.SettingsChanged();
            db.Set<OrganizationSettingsVersion>().Add(new(organization.Id, actor, organization.SettingsVersion, section, Guid.NewGuid(),
                app.Clock.UtcNow, "{}", "{}", $"Generated change {i}", "test"));
        }
        await db.SaveChangesAsync();
    });

    // A clerk who sees North only and may read the change log.
    private Task ScopeClerkTo(Guid company) => app.WithDb(async db =>
    {
        db.Provisioning = true;
        var clerk = await db.Users.SingleAsync(x => x.Email == RevenueClerk);
        var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
        db.PermissionOverrides.Add(new() { OrganizationId = organizationId, UserId = clerk.Id, Permission = "audit.view", Granted = true });
        db.SetupCompanyScopes.Add(new() { OrganizationId = organizationId, UserId = clerk.Id, CompanyId = company });
        await db.SaveChangesAsync();
    });

    [Fact]
    public async Task PagingByVersionReturnsTheSameRowsAsPagingByNumber()
    {
        await app.SeedDemo();
        await AddChanges(40);
        await AddChanges(15, "companies");
        using var owner = await app.SignIn(Owner);

        foreach (var filter in new[] { "", "&section=expenses", "&text=Generated" })
        {
            var byNumber = new List<long>();
            for (var page = 1; ; page++)
            {
                var items = (await Log(owner, $"page={page}&pageSize=7{filter}")).Items;
                if (items.Count == 0) break;
                byNumber.AddRange(items.Select(x => x.Version));
            }

            var byVersion = new List<long>();
            var next = await Log(owner, $"pageSize=7{filter}");
            while (true)
            {
                byVersion.AddRange(next.Items.Select(x => x.Version));
                Assert.Equal(next.HasMore, next.NextBefore is not null);
                if (!next.HasMore) break;
                Assert.Equal(next.Items[^1].Version, next.NextBefore);
                next = await Log(owner, $"pageSize=7&before={next.NextBefore}{filter}");
            }

            Assert.True(byNumber.Count > 7, filter);
            Assert.Equal(byNumber, byVersion);
            Assert.Equal(byVersion.OrderDescending(), byVersion);
        }

        // A page that ends exactly at the last row says there is nothing more, and a version is a positive number.
        var companies = (await Log(owner, "pageSize=100&section=companies")).Total!.Value;
        Assert.False((await Log(owner, $"pageSize={companies}&section=companies")).HasMore);
        Assert.True((await Log(owner, $"pageSize={companies - 1}&section=companies")).HasMore);
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.GetAsync("/setup/history?before=0")).StatusCode);
    }

    [Fact]
    public async Task TheCountIsSkippedOnRequestAndCountedOncePerChange()
    {
        await app.SeedDemo();
        await AddChanges(30);
        using var owner = await app.SignIn(Owner);
        var company = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North", "Add North")));
        static bool Counts(string sql) => sql.Contains("COUNT(", StringComparison.OrdinalIgnoreCase);
        await Log(owner, "pageSize=5&includeTotal=false");

        app.Database.Reset();
        var first = await Log(owner, "pageSize=5");
        var counted = app.Database.Commands;
        Assert.Contains(app.Database.Sql, Counts);

        // The same question at the same version reuses the count: one command fewer, the same answer.
        app.Database.Reset();
        var again = await Log(owner, "pageSize=5&page=2");
        Assert.DoesNotContain(app.Database.Sql, Counts);
        Assert.Equal(counted - 1, app.Database.Commands);
        Assert.Equal(first.Total, again.Total);

        // A different filter is a different count.
        app.Database.Reset();
        var narrowed = await Log(owner, "pageSize=5&section=companies");
        Assert.Contains(app.Database.Sql, Counts);
        Assert.True(narrowed.Total < first.Total);

        // Any change moves the version, so the next page counts again and includes it.
        await Id(await owner.PutAsJsonAsync($"/setup/companies/{company}", new SaveCompany("North Star", "Rename")));
        app.Database.Reset();
        var after = await Log(owner, "pageSize=5");
        Assert.Contains(app.Database.Sql, Counts);
        Assert.Equal(first.Total + 1, after.Total);

        // A caller that shows no total can skip the count altogether.
        app.Database.Reset();
        var noTotal = await Log(owner, "pageSize=3&includeTotal=false");
        Assert.DoesNotContain(app.Database.Sql, Counts);
        Assert.Null(noTotal.Total);
        Assert.Equal(3, noTotal.Items.Count);
        Assert.True(noTotal.HasMore);
    }

    [Fact]
    public async Task ScopedViewersSeeRevenueOnlyForTheVehiclesTheyCanSeeToday()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var north = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North Star", "Add North Star")));
        var south = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("South Line", "Add South Line")));
        var today = RevenueTestData.CalendarDate(app);
        var mine = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(north, "KDA 482M", today, 15000m, "Add")));
        var theirs = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(south, "KDB 111A", today, 15000m, "Add")));
        foreach (var vehicle in new[] { mine, theirs })
            (await owner.PutAsJsonAsync($"/setup/revenue/{vehicle}/{today:yyyy-MM-dd}",
                new { amount = 1000m, reason = (string?)null, note = (string?)null })).EnsureSuccessStatusCode();
        await ScopeClerkTo(north);
        using var clerk = await app.SignIn(RevenueClerk);

        // The owner asks first, at the same version, so a count shared across scopes would show here.
        var everything = await Log(owner, "pageSize=100&section=revenue");
        Assert.Equal(2, everything.Items.Count);
        var seen = await Log(clerk, "pageSize=100&section=revenue");
        Assert.Contains("KDA 482M", Assert.Single(seen.Items).Reason);
        Assert.Equal(1, seen.Total);
        var log = await Log(clerk, "pageSize=100");
        Assert.DoesNotContain(log.Items, x => x.Reason.Contains("KDB 111A") || x.Reason.Contains("South Line"));
        Assert.Equal(log.Items.Count, log.Total);

        // Visibility follows where a vehicle is now: once it moves to North, its earlier revenue shows too.
        await Id(await owner.PutAsJsonAsync($"/setup/vehicles/{theirs}", new SaveVehicle(north, "KDB 111A", today, 15000m, "Move to North")));
        var moved = await Log(clerk, "pageSize=100&section=revenue");
        Assert.Equal(2, moved.Items.Count);
        Assert.Equal(2, moved.Total);
    }

    [Fact]
    public async Task ReadingTheChangeLogCostsTheSameHoweverLongItGrows()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var north = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North Star", "Add North Star")));
        await ScopeClerkTo(north);
        using var clerk = await app.SignIn(RevenueClerk);

        async Task<(int Commands, int Rows)> Cost(HttpClient client, string query)
        {
            app.Database.Reset();
            await Log(client, query);
            return (app.Database.Commands, app.Database.Rows);
        }
        var requests = new (HttpClient Client, string Who, string Query)[]
        {
            (owner, "owner", "pageSize=25"), (owner, "owner", "pageSize=25&before=1000000"),
            (owner, "owner", "pageSize=25&text=Generated"), (clerk, "clerk", "pageSize=25"),
        };

        // Once through first, so each viewer's first-request work is behind them; the new rows then move the version.
        foreach (var (client, _, query) in requests) await Cost(client, query);
        await AddChanges(30);
        var small = new List<(int, int)>();
        foreach (var (client, _, query) in requests) small.Add(await Cost(client, query));
        await AddChanges(600);
        var large = new List<(int, int)>();
        foreach (var (client, _, query) in requests) large.Add(await Cost(client, query));

        for (var i = 0; i < requests.Length; i++)
            output.WriteLine($"{requests[i].Who} {requests[i].Query}: {small[i]} at ~30 rows, {large[i]} at ~630 rows (commands, rows read)");
        Assert.Equal(small, large);
    }

    // What the database is asked: a version bound instead of an offset, and no visibility subqueries for someone who
    // sees every company.
    [Fact]
    public async Task VersionPagesSeekAndUnscopedViewersSkipTheVisibilityChecks()
    {
        await app.SeedDemo();
        await AddChanges(10);
        using var owner = await app.SignIn(Owner);
        var north = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North Star", "Add North Star")));
        await ScopeClerkTo(north);
        using var clerk = await app.SignIn(RevenueClerk);

        string HistorySql() => app.Database.Sql.Single(x => x.Contains("FROM \"OrganizationSettingsVersion\"") && !x.Contains("COUNT("));

        app.Database.Reset();
        await Log(owner, "pageSize=5&page=2&includeTotal=false");
        Assert.Contains("OFFSET", HistorySql());

        app.Database.Reset();
        await Log(owner, "pageSize=5&before=8&includeTotal=false");
        var seek = HistorySql();
        Assert.DoesNotContain("OFFSET", seek);
        Assert.Contains("\"Version\" < @", seek);
        Assert.DoesNotContain("\"FleetVehicle\"", seek);
        Assert.DoesNotContain("\"RecurringItem\"", seek);

        // A scoped viewer's revenue rows are matched on their own vehicle, not through the records table.
        app.Database.Reset();
        await Log(clerk, "pageSize=5&includeTotal=false");
        var scoped = HistorySql();
        Assert.Contains("\"FleetVehicle\"", scoped);
        Assert.Contains("\"RecurringItem\"", scoped);
        Assert.Contains("\"VehicleId\" IS NOT NULL", scoped);
        Assert.DoesNotContain("\"RevenueRecords\"", scoped);
    }

    // The migration's own backfill, run on rows logged before the column existed.
    [Fact]
    public async Task TheBackfillGivesEarlierRowsTheirVehicle()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var company = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North Star", "Add North Star")));
        var today = RevenueTestData.CalendarDate(app);
        var vehicle = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(company, "KDA 482M", today, 15000m, "Add")));
        await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/investment", new { date = today, description = "Deposit", amount = 100000m }));
        (await owner.PutAsJsonAsync($"/setup/revenue/{vehicle}/{today:yyyy-MM-dd}",
            new { amount = 1000m, reason = (string?)null, note = (string?)null })).EnsureSuccessStatusCode();

        await app.WithDb(async db =>
        {
            var rows = db.Set<OrganizationSettingsVersion>().IgnoreQueryFilters().AsNoTracking();
            var written = await rows.Where(x => x.VehicleId != null).Select(x => new { x.Id, x.Section, x.VehicleId }).ToListAsync();
            Assert.Equal(["investment", "revenue", "vehicles"], written.Select(x => x.Section).Distinct().Order());
            Assert.All(written, x => Assert.Equal(vehicle, x.VehicleId));

            await db.Database.ExecuteSqlRawAsync("UPDATE \"OrganizationSettingsVersion\" SET \"VehicleId\" = NULL");
            await db.Database.ExecuteSqlRawAsync(ChangeLogVehicle.BackfillVehiclesSql);
            await db.Database.ExecuteSqlRawAsync(ChangeLogVehicle.BackfillRevenueSql);

            var filled = await rows.Where(x => x.VehicleId != null).Select(x => new { x.Id, x.Section, x.VehicleId }).ToListAsync();
            Assert.Equal(written.OrderBy(x => x.Id), filled.OrderBy(x => x.Id));
            // A second run finds nothing left to fill, which is what ends the batched loop on SQL Server.
            Assert.Equal(0, await db.Database.ExecuteSqlRawAsync(ChangeLogVehicle.BackfillVehiclesSql));
            Assert.Equal(0, await db.Database.ExecuteSqlRawAsync(ChangeLogVehicle.BackfillRevenueSql));
        });

        Assert.Contains("UPDATE TOP (5000) [OrganizationSettingsVersion] SET [VehicleId] = (", ChangeLogVehicle.Batched(ChangeLogVehicle.BackfillRevenueSql));
        Assert.Contains("[VehicleId] IS NULL AND [Section] = 'revenue' AND EXISTS", ChangeLogVehicle.Batched(ChangeLogVehicle.BackfillRevenueSql));
    }

    public void Dispose() => app.Dispose();
}
