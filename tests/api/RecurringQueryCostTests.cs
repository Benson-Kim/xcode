using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Xunit;
using Xunit.Abstractions;

namespace Auth.Tests;

// Saving and stopping a scheduled item check every share's vehicle and company. Those checks read in batches, so the
// number of queries does not grow with the number of vehicles; the rules they enforce are pinned down here too.
public sealed class RecurringQueryCostTests(ITestOutputHelper output) : IDisposable
{
    private readonly AuthFactory app = new();
    private const string Owner = "antony.maina@shamayah.co.ke";
    private const string RevenueClerk = "wanjiru.kamau@zurigenesis.co.ke";
    private DateOnly Today => DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);

    private object Parking(Guid item, IEnumerable<Guid> vehicles, decimal each) => new
    {
        kind = 1, amount = vehicles.Count() * each, frequency = 2, day = 1, lastDay = false, start = Today.ToString("yyyy-MM-dd"),
        allocations = vehicles.Select(vehicleId => new { vehicleId, amount = each }), expenseItemId = item
    };

    // Reads are what the share checks add; inserts of the shares themselves naturally grow with them.
    private int Reads() => app.Database.Sql.Count(sql => sql.TrimStart().StartsWith("SELECT", StringComparison.OrdinalIgnoreCase));

    [Fact]
    public async Task SavingAndStoppingReadTheSameNumberOfTimesForTwoOrTwoHundredVehicles()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var vehicles = await AddVehicles(200);
        var parking = await ExpenseItemTestData.Id(owner, "Parking");

        async Task<(int Create, int Revise, int Stop, int StopCommands)> Measure(int shares)
        {
            var chosen = vehicles.Take(shares).ToList();
            app.Database.Reset();
            var item = await Id(await owner.PostAsJsonAsync("/setup/recurring", Parking(parking, chosen, 100m)));
            var create = Reads();
            app.Database.Reset();
            await Id(await owner.PutAsJsonAsync($"/setup/recurring/{item}", Parking(parking, chosen, 150m)));
            var revise = Reads();
            app.Database.Reset();
            await Id(await owner.PostAsJsonAsync($"/setup/recurring/{item}/stop", new { confirmed = true, reason = "Parking is now in the SACCO fee" }));
            var (stop, stopCommands) = (Reads(), app.Database.Commands);
            output.WriteLine($"{shares} shares: create {create} reads, revise {revise} reads, stop {stop} reads / {stopCommands} commands");
            return (create, revise, stop, stopCommands);
        }

        Assert.Equal(await Measure(2), await Measure(200));
    }

    [Fact]
    public async Task ShareChecksKeepTheirScopeAndRetiredVehicleRules()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var north = await Id(await owner.PostAsJsonAsync("/setup/companies", new { name = "North Star" }));
        var south = await Id(await owner.PostAsJsonAsync("/setup/companies", new { name = "South Line" }));
        async Task<Guid> Vehicle(Guid company, string registration) => await Id(await owner.PostAsJsonAsync("/setup/vehicles",
            new { companyId = company, registration, joinedOn = "2026-01-01", weeklyTarget = 15000m }));
        var (mine, retiring, theirs) = (await Vehicle(north, "KDA 482M"), await Vehicle(north, "KDA 483M"), await Vehicle(south, "KDB 111A"));
        var parking = await ExpenseItemTestData.Id(owner, "Parking");
        var shared = await Id(await owner.PostAsJsonAsync("/setup/recurring", Parking(parking, [mine, retiring, theirs], 100m)));
        await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{retiring}/retire", new { leftOn = Today.ToString("yyyy-MM-dd") }));

        // A retired vehicle already on the item may stay on it; a new share needs an active vehicle.
        await Id(await owner.PutAsJsonAsync($"/setup/recurring/{shared}", Parking(parking, [mine, retiring, theirs], 200m)));
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync("/setup/recurring", Parking(parking, [mine, retiring], 100m))).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await owner.PostAsJsonAsync("/setup/recurring", Parking(parking, [mine, Guid.NewGuid()], 100m))).StatusCode);

        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var clerk = await db.Users.SingleAsync(x => x.Email == RevenueClerk);
            var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
            db.PermissionOverrides.Add(new PersonPermissionOverride { OrganizationId = organizationId, UserId = clerk.Id, Permission = "commitments.manage", Granted = true });
            db.SetupCompanyScopes.Add(new SetupCompanyScope { OrganizationId = organizationId, UserId = clerk.Id, CompanyId = north });
            await db.SaveChangesAsync();
        });
        using var clerk = await app.SignIn(RevenueClerk);
        // Shares are checked in order: the retired vehicle comes before the one outside the clerk's scope.
        Assert.Equal(HttpStatusCode.BadRequest, (await clerk.PostAsJsonAsync("/setup/recurring", Parking(parking, [retiring, theirs], 100m))).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await clerk.PostAsJsonAsync("/setup/recurring", Parking(parking, [mine, theirs], 100m))).StatusCode);
        // An item that also posts outside the clerk's scope is theirs to see in part, never to change or stop.
        Assert.Equal(HttpStatusCode.Forbidden, (await clerk.PutAsJsonAsync($"/setup/recurring/{shared}", Parking(parking, [mine], 100m))).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await clerk.PostAsJsonAsync($"/setup/recurring/{shared}/stop", new { confirmed = true, reason = "Not ours" })).StatusCode);
        var own = await Id(await clerk.PostAsJsonAsync("/setup/recurring", Parking(parking, [mine], 100m)));
        await Id(await clerk.PostAsJsonAsync($"/setup/recurring/{own}/stop", new { confirmed = true, reason = "Moved to the SACCO fee" }));
    }

    private Task<List<Guid>> AddVehicles(int count) => WithResult(async db =>
    {
        db.Provisioning = true;
        var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
        var company = new PsvCompany(organizationId, "Big Fleet");
        db.Add(company);
        var vehicles = Enumerable.Range(0, count)
            .Select(i => new FleetVehicle(organizationId, company.Id, new VehicleRegistration($"KD{(char)('A' + i / 100)}{i % 100:D3}A"), new DateOnly(2026, 1, 1), 15000m))
            .ToList();
        db.AddRange(vehicles);
        await db.SaveChangesAsync();
        return vehicles.Select(v => v.Id).ToList();
    });

    private async Task<T> WithResult<T>(Func<AuthDb, Task<T>> action)
    {
        T result = default!;
        await app.WithDb(async db => result = await action(db));
        return result;
    }

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
