using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace Auth.Tests;

public sealed class AccessAndSetupTests : IDisposable
{
    private readonly AuthFactory app = new();
    private const string Owner = "antony.maina@shamayah.co.ke";
    private const string OfficeAdmin = "peter.otieno@zurigenesis.co.ke";
    private const string RevenueClerk = "wanjiru.kamau@zurigenesis.co.ke";

    private static SavePerson Person(string email, string phone, IEnumerable<string> permissions, string role = "Revenue clerk", decimal? approvalLimit = null,
        string scopeMode = "all", List<Guid>? vehicleIds = null) =>
        new("Jane", "Njeri", email, phone, role, scopeMode, [], vehicleIds ?? [], permissions.ToList(), approvalLimit);

    private static async Task<IReadOnlyList<string>> Defaults(HttpClient client, string role) =>
        (await client.GetFromJsonAsync<List<AccessRole>>("/setup/access/roles"))!.Single(x => x.Name == role).Permissions;

    private sealed record IdResponse(Guid Id);

    [Fact]
    public async Task PeopleManagersAssignRolesButOnlyAccessManagersChangeSinglePermissions()
    {
        await app.SeedDemo();
        using var admin = await app.SignIn(OfficeAdmin);
        var clerkDefaults = await Defaults(admin, "Revenue clerk");
        Assert.Contains("revenue.capture", clerkDefaults);

        using var withDefaults = await admin.PostAsJsonAsync("/setup/people", Person("jane.one@example.com", "0711000001", clerkDefaults));
        Assert.Equal(HttpStatusCode.OK, withDefaults.StatusCode);
        using var escalated = await admin.PostAsJsonAsync("/setup/people", Person("jane.two@example.com", "0711000002", clerkDefaults.Append("organization.manage")));
        Assert.Equal(HttpStatusCode.Forbidden, escalated.StatusCode);
        using var withLimit = await admin.PostAsJsonAsync("/setup/people", Person("jane.three@example.com", "0711000003", clerkDefaults, approvalLimit: 5000m));
        Assert.Equal(HttpStatusCode.Forbidden, withLimit.StatusCode);

        using var owner = await app.SignIn(Owner);
        using var granted = await owner.PostAsJsonAsync("/setup/people", Person("jane.four@example.com", "0711000004", clerkDefaults.Append("reports.view"), approvalLimit: 5000m));
        Assert.Equal(HttpStatusCode.OK, granted.StatusCode);
    }

    [Fact]
    public async Task EditingAnInactivePersonKeepsTheirAssignedPermissions()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var clerkDefaults = await Defaults(owner, "Revenue clerk");
        using var created = await owner.PostAsJsonAsync("/setup/people", Person("jane.one@example.com", "0711000001", clerkDefaults.Append("reports.view")));
        var id = (await created.Content.ReadFromJsonAsync<IdResponse>())!.Id;
        (await owner.PostAsync($"/setup/people/{id}/deactivate", null)).EnsureSuccessStatusCode();

        var inactive = await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{id}");
        Assert.False(inactive!.Active);
        Assert.Contains("reports.view", inactive.Permissions);

        // A people manager may rename them: resubmitting their assigned permissions is not an access change.
        using var admin = await app.SignIn(OfficeAdmin);
        using var renamed = await admin.PutAsJsonAsync($"/setup/people/{id}", Person("jane.one@example.com", "0711000001", inactive.Permissions) with { FirstName = "Janet" });
        Assert.Equal(HttpStatusCode.OK, renamed.StatusCode);
        var after = await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{id}");
        Assert.Equal("Janet", after!.FirstName);
        Assert.Contains("reports.view", after.Permissions);
    }

    [Fact]
    public async Task ScopeOptionsOfferTheVehiclesAPersonCanBeLimitedTo()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (_, vehicleId) = await AddVehicle(owner);

        var options = await owner.GetFromJsonAsync<ScopeOptions>("/setup/access/scope-options");
        Assert.Contains(options!.Companies, x => x.Name == "Review Fleet");
        Assert.Contains(options.Vehicles, x => x.Id == vehicleId && x.Registration == "KQA 321M");

        var clerkDefaults = await Defaults(owner, "Revenue clerk");
        using var created = await owner.PostAsJsonAsync("/setup/people", Person("jane.one@example.com", "0711000001", clerkDefaults, scopeMode: "vehicles", vehicleIds: [vehicleId]));
        Assert.Equal(HttpStatusCode.OK, created.StatusCode);
        var person = await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{(await created.Content.ReadFromJsonAsync<IdResponse>())!.Id}");
        Assert.Equal("vehicles", person!.ScopeMode);
        Assert.Equal([vehicleId], person.VehicleIds);
    }

    [Fact]
    public async Task CommitmentsUsersSeeRecurringItemsWithoutVehicleManagement()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (_, vehicleId) = await AddVehicle(owner);
        var today = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);
        (await owner.PostAsJsonAsync("/setup/recurring", new SaveRecurring("Insurance", RecurringKind.Cost, CostCategory.FixedCommitments, 900m,
            RecurrenceFrequency.Monthly, 1, false, today, null, [new VehicleShare(vehicleId, 900m)], "Add insurance"))).EnsureSuccessStatusCode();

        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var clerk = await db.Users.SingleAsync(x => x.Email == RevenueClerk);
            var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
            db.PermissionOverrides.AddRange(
                new PersonPermissionOverride { OrganizationId = organizationId, UserId = clerk.Id, Permission = "commitments.view", Granted = true },
                new PersonPermissionOverride { OrganizationId = organizationId, UserId = clerk.Id, Permission = "commitments.manage", Granted = true });
            db.SetupDataScopes.Add(new SetupDataScope { OrganizationId = organizationId, UserId = clerk.Id, AllCompanies = true });
            await db.SaveChangesAsync();
        });
        using var commitments = await app.SignIn(RevenueClerk);

        var vehicleList = await owner.GetFromJsonAsync<Page<VehicleDto>>("/setup/vehicles");
        Assert.Equal(1, Assert.Single(vehicleList!.Items).RecurringItems);
        Assert.Equal(HttpStatusCode.Forbidden, (await commitments.GetAsync("/setup/vehicles")).StatusCode);
        var items = await commitments.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring");
        Assert.Equal("KQA 321M", Assert.Single(Assert.Single(items!.Items).Allocations).Registration);
        var vehicles = await commitments.GetFromJsonAsync<List<VehicleOption>>("/setup/recurring/vehicle-options");
        Assert.Equal("Review Fleet", Assert.Single(vehicles!).CompanyName);
    }

    [Fact]
    public async Task VehicleReportsResolveTheCurrentPeriodOnTheServer()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (_, vehicleId) = await AddVehicle(owner);
        var today = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);

        var month = await owner.GetFromJsonAsync<VehicleReport>($"/setup/vehicles/{vehicleId}/report?period=month");
        Assert.Equal(new DateOnly(today.Year, today.Month, 1), month!.From);
        Assert.Equal(today, month.Through);
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.GetAsync($"/setup/vehicles/{vehicleId}/report?period=year")).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.GetAsync($"/setup/vehicles/{vehicleId}/report")).StatusCode);
    }

    [Fact]
    public async Task EveryMemberCanReadPermissionLabelsButNotPeople()
    {
        await app.SeedDemo();
        using var clerk = await app.SignIn(RevenueClerk);
        var catalog = await clerk.GetFromJsonAsync<List<PermissionGroup>>("/setup/access/catalog");
        Assert.Contains(catalog!, group => group.Items.Any(item => item.Key == "revenue.capture"));
        Assert.Equal(HttpStatusCode.Forbidden, (await clerk.GetAsync("/setup/people")).StatusCode);
    }

    [Fact]
    public async Task OrganizationSettingsFailuresMapToClientErrors()
    {
        await app.SeedDemo();
        using var admin = await app.SignIn(OfficeAdmin);
        Assert.Equal(HttpStatusCode.Forbidden, (await admin.GetAsync("/setup/organization/settings")).StatusCode);

        using var owner = await app.SignIn(Owner);
        using var invalid = await owner.PutAsJsonAsync("/setup/organization/settings/securityPolicy", new { value = new { lockoutThreshold = 99 }, reason = "Tighten lockout" });
        Assert.Equal(HttpStatusCode.BadRequest, invalid.StatusCode);
        using var noReason = await owner.PutAsJsonAsync("/setup/organization/settings/securityPolicy", new { value = new { lockoutThreshold = 3 }, reason = " " });
        Assert.Equal(HttpStatusCode.BadRequest, noReason.StatusCode);
    }

    [Fact]
    public async Task OrganizationSettingsChangesKeepTheirReason()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        using var saved = await owner.PutAsJsonAsync("/setup/organization/settings/securityPolicy", new { value = new { lockoutThreshold = 3 }, reason = "  Tighten lockout after audit  " });
        Assert.Equal(HttpStatusCode.OK, saved.StatusCode);

        var history = await owner.GetFromJsonAsync<JsonElement>("/setup/history");
        var entry = history.GetProperty("items").EnumerateArray().Single(x => x.GetProperty("section").GetString() == "securityPolicy");
        Assert.Equal("Tighten lockout after audit", entry.GetProperty("reason").GetString());
        Assert.Equal("Antony Maina", entry.GetProperty("actorName").GetString());
        await app.WithDb(async db =>
        {
            var audit = await db.AuditEvents.IgnoreQueryFilters().SingleAsync(x => x.Action == "organization.settings.updated");
            Assert.Contains("Tighten lockout after audit", audit.After);
            Assert.Equal(3, (await db.SecurityPolicies.IgnoreQueryFilters().SingleAsync()).LockoutThreshold);
        });
    }

    private static async Task<(Guid Company, Guid Vehicle)> AddVehicle(HttpClient owner)
    {
        using var company = await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("Review Fleet", "Add review fleet"));
        var companyId = (await company.Content.ReadFromJsonAsync<IdResponse>())!.Id;
        using var vehicle = await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(companyId, "KQA 321M", new DateOnly(2026, 1, 1), 20000m, "Add review vehicle"));
        return (companyId, (await vehicle.Content.ReadFromJsonAsync<IdResponse>())!.Id);
    }

    public void Dispose() => app.Dispose();
}
