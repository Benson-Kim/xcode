using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace Auth.Tests;

// The change log covers people and access, records what was really saved, and scoped viewers can tell
// when a recurring item reaches beyond what they can see.
public sealed class ChangeLogAndScopeTests : IDisposable
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

    private static async Task<List<HistoryEntry>> History(HttpClient client) =>
        [.. (await client.GetFromJsonAsync<Page<HistoryEntry>>("/setup/history?pageSize=100"))!.Items];

    [Fact]
    public async Task PeopleAndAccessChangesJoinTheChangeLog()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var roles = (await owner.GetFromJsonAsync<List<AccessRole>>("/setup/access/roles"))!;
        SavePerson Jane(string role) => new("Jane", "Njeri", "jane.one@example.com", "0711000001", role, "all", [], [],
            roles.Single(x => x.Name == role).Permissions.ToList(), null);

        var id = await Id(await owner.PostAsJsonAsync("/setup/people", Jane("Revenue clerk")));
        var created = await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{id}");
        (await owner.PutAsJsonAsync($"/setup/people/{id}", Jane("Revenue clerk") with { Version = created!.Version })).EnsureSuccessStatusCode(); // nothing changed
        var beforeRoleChange = await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{id}");
        (await owner.PutAsJsonAsync($"/setup/people/{id}", Jane("Fleet manager") with { Version = beforeRoleChange!.Version })).EnsureSuccessStatusCode();
        (await owner.PostAsync($"/setup/people/{id}/sign-out", null)).EnsureSuccessStatusCode();
        var beforeRemoval = await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{id}");
        (await owner.PostAsJsonAsync($"/setup/people/{id}/deactivate", new { version = beforeRemoval!.Version, reason = "Left the organization" })).EnsureSuccessStatusCode();
        (await owner.PostAsJsonAsync($"/setup/people/{id}/deactivate", new { })).EnsureSuccessStatusCode(); // already removed

        var people = (await History(owner)).Where(x => x.Section == "people").ToList();
        Assert.All(people, x => Assert.Equal(id, x.EntityId));
        Assert.Equal(
            ["Left the organization", "Signed Jane Njeri out of every device", "Changed role for Jane Njeri", "Added Jane Njeri as Revenue clerk"],
            people.Select(x => x.Reason));
        Assert.All(people, x => Assert.Equal("Antony Maina", x.ActorName));

        await app.WithDb(async db =>
        {
            var roleChange = await db.Set<OrganizationSettingsVersion>().IgnoreQueryFilters().SingleAsync(x => x.Reason == "Changed role for Jane Njeri");
            Assert.Contains("\"Role\":\"Revenue clerk\"", roleChange.Before);
            Assert.Contains("\"Role\":\"Fleet manager\"", roleChange.After);
        });
    }

    [Fact]
    public async Task SharedRecurringItemsAreMarkedPartialForScopedViewers()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var north = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North Star", "Add North Star")));
        var south = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("South Line", "Add South Line")));
        var mine = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(north, "KDA 482M", new DateOnly(2026, 1, 1), 15000m, "Add")));
        var theirs = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(south, "KDB 111A", new DateOnly(2026, 1, 1), 15000m, "Add")));
        var today = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);
        SaveRecurring Cost(string name, params VehicleShare[] shares) => new(name, RecurringKind.Cost, CostCategory.FixedCommitments,
            shares.Sum(x => x.Amount), RecurrenceFrequency.Monthly, 1, false, today, null, [.. shares], "Add " + name);
        await Id(await owner.PostAsJsonAsync("/setup/recurring", Cost("Office rent", new VehicleShare(mine, 500m), new VehicleShare(theirs, 500m))));
        await Id(await owner.PostAsJsonAsync("/setup/recurring", Cost("Insurance", new VehicleShare(mine, 900m))));

        // The clerk manages commitments for North Star only.
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var clerk = await db.Users.SingleAsync(x => x.Email == RevenueClerk);
            var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
            db.PermissionOverrides.AddRange(
                new PersonPermissionOverride { OrganizationId = organizationId, UserId = clerk.Id, Permission = "commitments.view", Granted = true },
                new PersonPermissionOverride { OrganizationId = organizationId, UserId = clerk.Id, Permission = "commitments.manage", Granted = true });
            db.SetupCompanyScopes.Add(new SetupCompanyScope { OrganizationId = organizationId, UserId = clerk.Id, CompanyId = north });
            await db.SaveChangesAsync();
        });
        using var clerk = await app.SignIn(RevenueClerk);

        var seen = (await clerk.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring"))!.Items;
        var rent = seen.Single(x => x.Name == "Office rent");
        Assert.True(rent.Partial);
        Assert.Equal(500m, rent.Amount);
        Assert.Equal(mine, Assert.Single(rent.Allocations).VehicleId);
        Assert.False(seen.Single(x => x.Name == "Insurance").Partial);

        // Everyone sees items in name order, page after page.
        var all = (await owner.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring?pageSize=1"))!;
        var next = (await owner.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring?page=2&pageSize=1"))!;
        Assert.Equal(["Insurance", "Office rent"], [Assert.Single(all.Items).Name, Assert.Single(next.Items).Name]);
        Assert.False(next.Items[0].Partial);
    }

    [Fact]
    public async Task SettingsHistoryRecordsWhatWasSavedAndSkipsUnchangedSaves()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var change = new { value = new { lockoutThreshold = 3 }, reason = "Tighten lockout" };
        (await owner.PutAsJsonAsync("/setup/organization/settings/securityPolicy", change)).EnsureSuccessStatusCode();
        (await owner.PutAsJsonAsync("/setup/organization/settings/securityPolicy", change)).EnsureSuccessStatusCode();

        await app.WithDb(async db =>
        {
            var version = await db.Set<OrganizationSettingsVersion>().IgnoreQueryFilters().SingleAsync(x => x.Section == "securityPolicy");
            // Omitted fields were saved with their defaults, so the history shows them too.
            Assert.Contains("\"lockoutThreshold\":3", version.After);
            Assert.Contains("\"pinLength\":4", version.After);
        });
    }

    [Fact]
    public async Task PreferencesSayWhichOverridesTheOrganizationAllows()
    {
        await app.SeedDemo();
        using var clerk = await app.SignIn(RevenueClerk);
        var preferences = await clerk.GetFromJsonAsync<JsonElement>("/setup/preferences");
        Assert.True(preferences.GetProperty("allowLocaleOverride").GetBoolean());
        Assert.False(preferences.GetProperty("allowTimeZoneOverride").GetBoolean());
        Assert.Equal("UTC", preferences.GetProperty("organization").GetProperty("timeZone").GetString());
        Assert.Equal(1, preferences.GetProperty("fontScale").GetDouble());
    }

    [Fact]
    public void OversizedLogosAreRefusedBeforeTheyAreRead()
    {
        var now = DateTimeOffset.UtcNow;
        var oversized = Assert.Throws<ArgumentException>(() => OrganizationLogo.FromDataUrl(Guid.NewGuid(), "data:image/png;base64," + new string('!', 400_000), now));
        Assert.Contains("256 KB", oversized.Message);

        // The largest allowed image still fits under the pre-check.
        var largest = new byte[OrganizationLogo.MaxBytes];
        new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A }.CopyTo(largest, 0);
        var logo = OrganizationLogo.FromDataUrl(Guid.NewGuid(), "data:image/png;base64," + Convert.ToBase64String(largest), now);
        Assert.Equal(OrganizationLogo.MaxBytes, logo.Data.Length);
    }

    public void Dispose() => app.Dispose();
}
