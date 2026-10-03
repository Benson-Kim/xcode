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
            ["Removed access for Jane Njeri. Reason: Left the organization.", "Signed Jane Njeri out of every device", "Changed role for Jane Njeri", "Added Jane Njeri as Revenue clerk"],
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
        var items = new Dictionary<string, Guid> { ["Office rent"] = await ExpenseItemTestData.Id(owner, "Office rent"), ["Insurance"] = await ExpenseItemTestData.Id(owner, "Insurance") };
        SaveRecurring Cost(string name, params VehicleShare[] shares) => new(name, RecurringKind.Cost, null,
            shares.Sum(x => x.Amount), RecurrenceFrequency.Monthly, 1, false, today, null, [.. shares], "Add " + name, items[name]);
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

    // What another writer's change-log entry does to the organization row it shares with every write.
    private const string BumpChangeLog = "UPDATE \"Organizations\" SET \"SettingsVersion\" = \"SettingsVersion\" + 1";

    [Fact]
    public async Task WritesToDifferentRecordsRetryWhenOnlyTheChangeLogCollides()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var north = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North", "Add North")));
        var south = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("South", "Add South")));

        // Each rename's change-log entry collides with another writer's entry for a different record: the unit of
        // work runs again from scratch, in a new transaction, and succeeds.
        foreach (var (id, name) in new[] { (north, "North Star"), (south, "South Line") })
        {
            app.Database.Reset();
            app.Database.Interleave("Organizations", BumpChangeLog);
            Assert.Equal(HttpStatusCode.OK, (await owner.PutAsJsonAsync($"/setup/companies/{id}", new SaveCompany(name, "Rename"))).StatusCode);
            Assert.Equal(2, app.Database.Transactions);
        }
        var companies = (await owner.GetFromJsonAsync<Page<CompanyDto>>("/setup/companies"))!.Items;
        Assert.Equal(["North Star", "South Line"], companies.Select(x => x.Name).Order());
        Assert.Equal(2, (await History(owner)).Count(x => x.Reason is "Renamed company North to North Star. Reason: Rename." or "Renamed company South to South Line. Reason: Rename."));

        // A collision that keeps happening gives up after three retries.
        app.Database.Reset();
        app.Database.Interleave("Organizations", BumpChangeLog, times: 4);
        Assert.Equal(HttpStatusCode.Conflict,
            (await owner.PutAsJsonAsync($"/setup/companies/{north}", new SaveCompany("North Again", "Rename"))).StatusCode);
        Assert.Equal(4, app.Database.Transactions);
    }

    // Taken from the Owner after the first attempt rolled back and before the retry: a single permission, or the membership.
    [Theory]
    [InlineData("INSERT INTO \"PermissionOverrides\" (\"OrganizationId\", \"UserId\", \"Permission\", \"Granted\") SELECT \"OrganizationId\", \"UserId\", 'companies.manage', 0 FROM \"Memberships\" WHERE \"UserId\" = (SELECT \"Id\" FROM \"Users\" WHERE \"Email\" = 'antony.maina@shamayah.co.ke')")]
    [InlineData("UPDATE \"Memberships\" SET \"Active\" = 0 WHERE \"UserId\" = (SELECT \"Id\" FROM \"Users\" WHERE \"Email\" = 'antony.maina@shamayah.co.ke')")]
    public async Task ARetryChecksAccessAgain(string revocation)
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var north = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North", "Add North")));

        app.Database.Reset();
        app.Database.Interleave("Organizations", BumpChangeLog);
        app.Database.BetweenAttempts(revocation);
        using var renamed = await owner.PutAsJsonAsync($"/setup/companies/{north}", new SaveCompany("North Star", "Rename"));

        Assert.Equal(2, app.Database.Transactions);
        Assert.Equal(HttpStatusCode.Forbidden, renamed.StatusCode);
        await app.WithDb(async db => Assert.Equal("North", (await db.Set<PsvCompany>().IgnoreQueryFilters().SingleAsync(x => x.Id == north)).Name));
    }

    [Fact]
    public async Task AStaleRecordStillConflictsAtOnce()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var clerk = (await owner.GetFromJsonAsync<Page<PersonDto>>("/setup/people"))!.Items.Single(x => x.Email == RevenueClerk);

        // Someone else saves this person between this save's read and its write: a real conflict, so no retry.
        app.Database.Reset();
        app.Database.Interleave("Memberships", "UPDATE \"Memberships\" SET \"Version\" = \"Version\" + 1");
        using var stale = await owner.PutAsJsonAsync($"/setup/people/{clerk.Id}", new SavePerson(clerk.FirstName, "Renamed", clerk.Email,
            clerk.PhoneNumber, clerk.Role, "all", [], [], [.. clerk.Permissions], clerk.ApprovalLimit, clerk.Version));
        Assert.Equal(HttpStatusCode.Conflict, stale.StatusCode);
        Assert.Equal(1, app.Database.Transactions);
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
