using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace Auth.Tests;

// A scoped person with audit.view sees the people changes of the people they could see in the people list, and the
// snapshots show only the companies and vehicles in their own scope.
public sealed class PeopleHistoryTests : IDisposable
{
    private readonly AuthFactory app = new();
    private const string Owner = "antony.maina@shamayah.co.ke";
    private const string RevenueClerk = "wanjiru.kamau@zurigenesis.co.ke";

    [Fact]
    public async Task ScopedAuditorsSeeChangesToVisiblePeopleWithHiddenScopeRedacted()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var north = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North Star")));
        var south = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("South Line")));
        var mine = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(north, "KDA 482M", new DateOnly(2026, 1, 1), 15000m)));
        var theirs = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(south, "KDB 111A", new DateOnly(2026, 1, 1), 15000m)));
        var clerkDefaults = (await owner.GetFromJsonAsync<List<AccessRole>>("/setup/access/roles"))!.Single(x => x.Name == "Revenue clerk").Permissions;
        async Task<Guid> Person(string email, string phone, string mode, List<Guid> companies, List<Guid> vehicles) => await Id(await owner.PostAsJsonAsync("/setup/people",
            new SavePerson("Jane", email[..4], email, phone, "Revenue clerk", mode, companies, vehicles, [.. clerkDefaults], null)));
        var both = await Person("both@example.com", "0711000001", "companies", [north, south], []);
        var southOnly = await Person("south@example.com", "0711000002", "companies", [south], []);
        var mixedVehicles = await Person("cars@example.com", "0711000003", "vehicles", [], [mine, theirs]);
        var current = await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{both}");
        await Id(await owner.PutAsJsonAsync($"/setup/people/{both}", new SavePerson("Janet", "both", "both@example.com", "0711000001", "Revenue clerk",
            "companies", [north, south], [], [.. clerkDefaults], null, current!.Version)));

        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var clerk = await db.Users.SingleAsync(x => x.Email == RevenueClerk);
            var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
            // D11: the people section carries contact details and permissions, so it needs people.view as well.
            db.PermissionOverrides.Add(new PersonPermissionOverride { OrganizationId = organizationId, UserId = clerk.Id, Permission = "audit.view", Granted = true });
            db.PermissionOverrides.Add(new PersonPermissionOverride { OrganizationId = organizationId, UserId = clerk.Id, Permission = "people.view", Granted = true });
            db.SetupCompanyScopes.Add(new SetupCompanyScope { OrganizationId = organizationId, UserId = clerk.Id, CompanyId = north });
            await db.SaveChangesAsync();
        });
        using var auditor = await app.SignIn(RevenueClerk);

        var seen = (await auditor.GetFromJsonAsync<Page<HistoryEntry>>("/setup/history?pageSize=100"))!.Items.Where(x => x.Section == "people").ToList();
        Assert.Equal(new[] { both, mixedVehicles }.Order(), seen.Select(x => x.EntityId).Distinct().Order());
        foreach (var hidden in new[] { south, theirs })
            Assert.All(seen, entry => Assert.DoesNotContain(hidden.ToString(), entry.Before + entry.After, StringComparison.OrdinalIgnoreCase));
        var renamed = seen.Single(x => x.EntityId == both && x.Before != "null");
        Assert.Equal([north], Ids(renamed.Before, "CompanyIds"));
        Assert.Equal([north], Ids(renamed.After, "CompanyIds"));
        Assert.Equal("Janet", JsonDocument.Parse(renamed.After!).RootElement.GetProperty("FirstName").GetString());
        Assert.Equal([mine], Ids(seen.Single(x => x.EntityId == mixedVehicles).After, "VehicleIds"));

        // Someone who sees every company sees every change in full.
        var all = (await owner.GetFromJsonAsync<Page<HistoryEntry>>("/setup/history?pageSize=100"))!.Items.Where(x => x.Section == "people").ToList();
        Assert.Contains(all, x => x.EntityId == southOnly);
        Assert.Equal(new[] { north, south }.Order(), Ids(all.First(x => x.EntityId == both).After, "CompanyIds").Order());
    }

    private static List<Guid> Ids(string? snapshot, string field) =>
        [.. JsonDocument.Parse(snapshot!).RootElement.GetProperty(field).EnumerateArray().Select(x => x.GetGuid())];

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
