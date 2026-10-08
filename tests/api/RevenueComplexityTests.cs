using System.Data.Common;
using Auth.Application;
using Auth.Application.Revenue;
using Auth.Application.Settings;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.Extensions.DependencyInjection;
using Xunit;
using Xunit.Abstractions;
using static Auth.Tests.RevenueTestData;

namespace Auth.Tests;

// Evidence for the revenue complexity claims: commands issued and rows read by the repository, as fleet size V and history D grow.
public sealed class RevenueComplexityTests(ITestOutputHelper output) : IDisposable
{
    private readonly AuthFactory app = new();

    // From 2 to 500 vehicles: the same commands, rows that grow with the fleet but never with its history, and a page
    // that lists its own vehicles while carrying the whole fleet's figures.
    [Fact]
    public async Task WeekAndDashboardCommandsStayFlatFromTwoToFiveHundredVehicles()
    {
        var today = await Arrange();
        var fleets = new[]
        {
            (Vehicles: 2, Company: await Fleet("Small Fleet", "KAB", vehicles: 2, days: 10, today)),
            (Vehicles: 100, Company: await BulkFleet("Hundred Fleet", "KBA", vehicles: 100, days: 10, today)),
            (Vehicles: 500, Company: await BulkFleet("Five Hundred Fleet", "KBB", vehicles: 500, days: 10, today)),
        };

        var commands = new HashSet<(int Week, int Page, int Month)>();
        foreach (var (vehicles, company) in fleets)
        {
            var week = await Measure((repository, actor) => repository.Week(actor, null, company, null, null, CancellationToken.None));
            var page = await Measure((repository, actor) => repository.Week(actor, null, company, null, new RevenueWeekPage(1, 10), CancellationToken.None));
            var month = await Measure((repository, actor) => repository.Dashboard(actor, "month", company, CancellationToken.None));
            output.WriteLine($"V={vehicles}: week {week.Commands} commands, {week.Reads} rows; page of 10 {page.Commands} commands, {page.Reads} rows; " +
                $"month dashboard {month.Commands} commands, {month.Reads} rows");
            commands.Add((week.Commands, page.Commands, month.Commands));

            Assert.Equal(vehicles, week.Result.Vehicles.Count);
            Assert.Equal(Math.Min(vehicles, 10), page.Result.Vehicles.Count);
            Assert.Equal(vehicles, page.Result.TotalVehicles);
            Assert.Equal((week.Result.TotalAmount, week.Result.TotalExpected, week.Result.Percent),
                (page.Result.TotalAmount, page.Result.TotalExpected, page.Result.Percent));
            // Every vehicle has three records this week before today. A page reads the records of its own ten vehicles
            // and nothing else of the others': its figures come from a few summed rows.
            Assert.Equal(3 * (vehicles - Math.Min(vehicles, 10)), week.Reads - page.Reads);
            Assert.True(page.Reads <= 3 * vehicles + 7 * 10 + 10, $"A page of 10 read {page.Reads} rows for {vehicles} vehicles.");
            // Each vehicle, its target, its aggregate row and at most seven records, plus a few option rows.
            Assert.True(week.Reads <= 10 * vehicles + 10, $"Read {week.Reads} rows for a week of {vehicles} vehicles.");
            // Each vehicle, its target and one summed row: never a row per recorded day.
            Assert.True(month.Reads <= 3 * vehicles + 10, $"Read {month.Reads} rows for a month of {vehicles} vehicles.");
        }
        Assert.Single(commands);
    }

    [Fact]
    public async Task SaveFindsTheEarliestMissingDayFromOneAggregateRowWhateverTheHistoryLength()
    {
        var today = await Arrange();
        var company = await Company(app, "Complexity Fleet");
        var contiguous = await Vehicle(app, company, "KAA 301A", today.AddDays(-120));
        await Records(app, contiguous, today.AddDays(-120), today.AddDays(-1));
        var holed = await Vehicle(app, company, "KAA 302A", today.AddDays(-120));
        await Records(app, holed, today.AddDays(-120), today.AddDays(-1), skip: [today.AddDays(-7)]);

        var fullVehicle = await LoadVehicle(contiguous);
        var full = await Measure((repository, actor) => repository.EarliestMissing(actor, fullVehicle, today, CancellationToken.None));
        Assert.Null(full.Result);
        Assert.Equal(1, full.Commands);
        Assert.True(full.Reads <= 2, $"Read {full.Reads} rows for one vehicle's aggregate.");

        // A hole in the history falls back to that one vehicle's dates.
        var holedVehicle = await LoadVehicle(holed);
        var gap = await Measure((repository, actor) => repository.EarliestMissing(actor, holedVehicle, today, CancellationToken.None));
        Assert.Equal(today.AddDays(-7), gap.Result);
        Assert.Equal(2, gap.Commands);
    }

    [Fact]
    public async Task WeekAndDashboardIssueTheSameCommandsWhateverTheFleetSizeAndHistory()
    {
        var today = await Arrange();
        var small = await Fleet("Small Fleet", "KAB", vehicles: 2, days: 10, today);
        var large = await Fleet("Large Fleet", "KAC", vehicles: 12, days: 150, today);

        var smallWeek = await Measure((repository, actor) => repository.Week(actor, null, small, null, null, CancellationToken.None));
        var largeWeek = await Measure((repository, actor) => repository.Week(actor, null, large, null, null, CancellationToken.None));
        Assert.Equal(smallWeek.Commands, largeWeek.Commands);
        Assert.All(largeWeek.Result.Vehicles, x => Assert.Null(x.EarliestMissing));
        // Vehicles with targets, one aggregate row each, at most seven records each and a few option rows: O(V), not O(V·D).
        Assert.True(largeWeek.Reads <= 10 * 12 + 10, $"Read {largeWeek.Reads} rows for a week of 12 vehicles.");

        var smallMonth = await Measure((repository, actor) => repository.Dashboard(actor, "month", null, CancellationToken.None));
        await Fleet("Second Large Fleet", "KAD", vehicles: 12, days: 150, today);
        var largeMonth = await Measure((repository, actor) => repository.Dashboard(actor, "month", null, CancellationToken.None));
        Assert.Equal(smallMonth.Commands, largeMonth.Commands);
    }

    private async Task<DateOnly> Arrange()
    {
        await app.SeedDemo();
        var today = PinnedThursday(app);
        await SetBusinessDate(app, today);
        return today;
    }

    private async Task<Guid> Fleet(string name, string prefix, int vehicles, int days, DateOnly today)
    {
        var company = await Company(app, name);
        for (var i = 1; i <= vehicles; i++)
        {
            var vehicle = await Vehicle(app, company, $"{prefix} {i:000}A", today.AddDays(-days));
            await Records(app, vehicle, today.AddDays(-days), today.AddDays(-1));
        }
        return company;
    }

    // The same fleet as Fleet, written in one save so hundreds of vehicles and thousands of records seed quickly.
    private async Task<Guid> BulkFleet(string name, string prefix, int vehicles, int days, DateOnly today)
    {
        var company = await Company(app, name);
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
            var actor = (await db.Users.SingleAsync(x => x.Email == Owner)).Id;
            for (var i = 0; i < vehicles; i++)
            {
                var vehicle = new FleetVehicle(organizationId, company, new VehicleRegistration($"{prefix} {i:000}A"), today.AddDays(-days), 7000m);
                db.Set<FleetVehicle>().Add(vehicle);
                for (var date = today.AddDays(-days); date < today; date = date.AddDays(1))
                    db.Set<RevenueRecord>().Add(new(organizationId, vehicle.Id, date, new(1000m, null, null), app.Clock.UtcNow.ToUniversalTime(), actor));
            }
            await db.SaveChangesAsync();
            db.Provisioning = false;
        });
        return company;
    }

    private async Task<FleetVehicle> LoadVehicle(Guid id)
    {
        FleetVehicle vehicle = null!;
        await app.WithDb(async db => vehicle = await db.Set<FleetVehicle>().IgnoreQueryFilters().AsNoTracking().SingleAsync(x => x.Id == id));
        return vehicle;
    }

    private async Task<(T Result, int Commands, int Reads)> Measure<T>(Func<RevenueRepository, SetupActor, Task<T>> action)
    {
        DbConnection connection = null!;
        Guid organizationId = default, ownerId = default;
        DateOnly today = default;
        await app.WithDb(async db =>
        {
            connection = db.Database.GetDbConnection();
            var organization = await db.Organizations.IgnoreQueryFilters().SingleAsync();
            organizationId = organization.Id;
            today = organization.BusinessDate!.Value;
            ownerId = (await db.Users.SingleAsync(x => x.Email == Owner)).Id;
        });

        var counter = new Counter();
        var context = new FixedOrganization(organizationId, ownerId);
        using var db = new AuthDb(new DbContextOptionsBuilder<AuthDb>().UseSqlite(connection).AddInterceptors(counter).Options, context);
        var organizations = new OrganizationRepository(db, app.Services.GetRequiredService<EffectiveSettingsResolver>(), app.Services.GetRequiredService<EffectivePermissionResolver>());
        var repository = new RevenueRepository(db, new UnitOfWork(db, context, app.Clock, organizations), new SettingsChangeLog(db, organizations, app.Clock));
        var actor = new SetupActor(organizationId, ownerId, today, true, [], [], "complexity",
            new HashSet<string>(["revenue.view", "revenue.capture", "revenue.no_earnings", "revenue.correct"]));
        var result = await action(repository, actor);
        return (result, counter.Commands, counter.Reads);
    }

    private sealed record FixedOrganization(Guid OrganizationId, Guid ActorId) : IOrganizationContext
    {
        public string CorrelationId => "complexity";
    }

    private sealed class Counter : DbCommandInterceptor
    {
        public int Commands { get; private set; }
        public int Reads { get; private set; }

        public override ValueTask<DbDataReader> ReaderExecutedAsync(DbCommand command, CommandExecutedEventData eventData,
            DbDataReader result, CancellationToken cancellationToken = default)
        {
            Commands++;
            return ValueTask.FromResult(result);
        }

        public override ValueTask<object?> ScalarExecutedAsync(DbCommand command, CommandExecutedEventData eventData,
            object? result, CancellationToken cancellationToken = default)
        {
            Commands++;
            return ValueTask.FromResult(result);
        }

        public override InterceptionResult DataReaderDisposing(DbCommand command, DataReaderDisposingEventData eventData, InterceptionResult result)
        {
            Reads += eventData.ReadCount;
            return result;
        }
    }

    public void Dispose() => app.Dispose();
}
