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
        // Web v2.8: the Office admin holds no capture permissions, so the only role they can give is their own.
        var adminDefaults = await Defaults(admin, "Office admin");
        Assert.DoesNotContain("revenue.capture", adminDefaults);

        using var withDefaults = await admin.PostAsJsonAsync("/setup/people", Person("jane.one@example.com", "0711000001", adminDefaults, role: "Office admin"));
        Assert.Equal(HttpStatusCode.OK, withDefaults.StatusCode);

        var fleetDefaults = await Defaults(admin, "Fleet manager");
        using var ungrantableRole = await admin.PostAsJsonAsync("/setup/people", new SavePerson(
            "Jane", "Njeri", "jane.fleet@example.com", "0711000005", "Fleet manager", "all", [], [],
            fleetDefaults.ToList(), null));
        Assert.Equal(HttpStatusCode.Forbidden, ungrantableRole.StatusCode);

        using var escalated = await admin.PostAsJsonAsync("/setup/people", Person("jane.two@example.com", "0711000002", adminDefaults.Append("organization.manage"), role: "Office admin"));
        Assert.Equal(HttpStatusCode.Forbidden, escalated.StatusCode);
        using var withLimit = await admin.PostAsJsonAsync("/setup/people", Person("jane.three@example.com", "0711000003", adminDefaults, role: "Office admin", approvalLimit: 5000m));
        Assert.Equal(HttpStatusCode.Forbidden, withLimit.StatusCode);

        using var owner = await app.SignIn(Owner);
        using var granted = await owner.PostAsJsonAsync("/setup/people", Person("jane.four@example.com", "0711000004", adminDefaults.Append("pettycash.approve_day"), role: "Office admin", approvalLimit: 5000m));
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
        (await owner.PostAsJsonAsync($"/setup/people/{id}/deactivate",
            new { version = 1L, reason = "Temporary leave" })).EnsureSuccessStatusCode();

        var inactive = await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{id}");
        Assert.False(inactive!.Active);
        Assert.Contains("reports.view", inactive.Permissions);

        // A people manager may rename them: resubmitting their assigned permissions is not an access change.
        using var admin = await app.SignIn(OfficeAdmin);
        using var renamed = await admin.PutAsJsonAsync($"/setup/people/{id}",
            Person("jane.one@example.com", "0711000001", inactive.Permissions) with { FirstName = "Janet", Version = inactive.Version });
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
    public async Task RetiringVehiclesStopsPostingAndAllowsCompanyArchiving()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (companyId, vehicleId) = await AddVehicle(owner);
        var today = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);

        using var recurring = await owner.PostAsJsonAsync("/setup/recurring",
            new SaveRecurring("Retirement test", RecurringKind.Cost, 900m,
                RecurrenceFrequency.Weekly, (int)today.DayOfWeek, false, today, null,
                [new VehicleShare(vehicleId, 900m)], "Add retirement test", await ExpenseItemTestData.Id(owner, "Parking")));
        Assert.Equal(HttpStatusCode.OK, recurring.StatusCode);

        using var retire = await owner.PostAsJsonAsync($"/setup/vehicles/{vehicleId}/retire",
            new { leftOn = today.ToString("yyyy-MM-dd"), reason = "Vehicle left the fleet" });
        Assert.Equal(HttpStatusCode.OK, retire.StatusCode);

        var vehicles = await owner.GetFromJsonAsync<Page<VehicleDto>>("/setup/vehicles");
        var vehicle = Assert.Single(vehicles!.Items, item => item.Id == vehicleId);
        Assert.False(vehicle.Active);
        Assert.Equal(today, vehicle.LeftOn);
        Assert.Equal(0m, vehicle.WeeklyTarget);
        Assert.Equal(0, vehicle.RecurringItems);

        var options = await owner.GetFromJsonAsync<List<VehicleOption>>("/setup/recurring/vehicle-options");
        Assert.DoesNotContain(options!, item => item.Id == vehicleId);

        using var archive = await owner.PostAsJsonAsync($"/setup/companies/{companyId}/archive",
            new { reason = "All vehicles left the fleet" });
        Assert.Equal(HttpStatusCode.OK, archive.StatusCode);
        var companies = await owner.GetFromJsonAsync<Page<CompanyDto>>("/setup/companies");
        Assert.False(Assert.Single(companies!.Items, item => item.Id == companyId).Active);

        using var restoreCompany = await owner.PostAsJsonAsync($"/setup/companies/{companyId}/restore",
            new { reason = "Company returned to service" });
        Assert.Equal(HttpStatusCode.OK, restoreCompany.StatusCode);
        using var restoreVehicle = await owner.PostAsJsonAsync($"/setup/vehicles/{vehicleId}/restore",
            new { reason = "Vehicle returned to service" });
        Assert.Equal(HttpStatusCode.OK, restoreVehicle.StatusCode);
    }

    [Fact]
    public async Task AnArchiveOnAnotherDateIsRefusedAndRestoreCancelsAScheduledArchive()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var company = (await (await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("Lifecycle Line", "Add Lifecycle Line")))
            .Content.ReadFromJsonAsync<IdResponse>())!.Id;
        (await owner.PostAsJsonAsync($"/setup/companies/{company}/archive", new { })).EnsureSuccessStatusCode();

        // The business date moves back, so the archive is now scheduled and the company still counts as active.
        app.Clock.Advance(TimeSpan.FromDays(-3));
        var row = (await owner.GetFromJsonAsync<Page<CompanyDto>>("/setup/companies"))!.Items.Single(x => x.Id == company);
        Assert.True(row.Active);
        Assert.NotNull(row.ArchivedOn);
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync($"/setup/companies/{company}/archive", new { })).StatusCode);
        (await owner.PostAsJsonAsync($"/setup/companies/{company}/restore", new { })).EnsureSuccessStatusCode();
        Assert.Null((await owner.GetFromJsonAsync<Page<CompanyDto>>("/setup/companies"))!.Items.Single(x => x.Id == company).ArchivedOn);

        // Archived earlier and the date moved on: archiving again says so instead of pretending it worked.
        (await owner.PostAsJsonAsync($"/setup/companies/{company}/archive", new { })).EnsureSuccessStatusCode();
        app.Clock.Advance(TimeSpan.FromDays(5));
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync($"/setup/companies/{company}/archive", new { })).StatusCode);
    }

    [Fact]
    public async Task RoleDefaultsComeOnlyFromTheCatalog()
    {
        await app.SeedDemo();
        // Older databases hold RolePermissions rows that can drift from the catalog: here an extra grant for the
        // Revenue clerk and a missing one for the Office admin. Neither may change a token or a request-time check.
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var roles = await db.Roles.IgnoreQueryFilters().ToListAsync();
            var clerkRole = roles.Single(x => x.Name == "Revenue clerk");
            var adminRole = roles.Single(x => x.Name == "Office admin");
            db.RolePermissions.RemoveRange(db.RolePermissions.IgnoreQueryFilters().Where(x => x.RoleId == adminRole.Id && x.Permission == "companies.manage"));
            db.RolePermissions.Add(new RolePermission { OrganizationId = clerkRole.OrganizationId, RoleId = clerkRole.Id, Permission = "organization.manage" });
            await db.SaveChangesAsync();
        });

        using var clerk = await app.SignIn(RevenueClerk);
        var session = await clerk.GetFromJsonAsync<AuthSessionResponse>("/auth/session");
        Assert.Equal(PermissionCatalog.DefaultsFor("Revenue clerk").Order(StringComparer.Ordinal), session!.Permissions.Order(StringComparer.Ordinal));
        Assert.Equal(HttpStatusCode.Forbidden, (await clerk.GetAsync("/setup/organization/settings")).StatusCode);

        using var admin = await app.SignIn(OfficeAdmin);
        Assert.Contains("companies.manage", (await admin.GetFromJsonAsync<AuthSessionResponse>("/auth/session"))!.Permissions);
        Assert.Equal(HttpStatusCode.OK, (await admin.GetAsync("/setup/companies")).StatusCode);

        // Roles are still created, but no role grant is written any more (only the row this test added exists).
        (await admin.GetAsync("/setup/access/roles")).EnsureSuccessStatusCode();
        await app.WithDb(async db =>
        {
            Assert.Equal(4, await db.Roles.IgnoreQueryFilters().CountAsync());
            Assert.Equal("organization.manage", Assert.Single(await db.RolePermissions.IgnoreQueryFilters().ToListAsync()).Permission);
        });
    }

    private static async Task<string?> Detail(HttpResponseMessage response) =>
        (await response.Content.ReadFromJsonAsync<JsonElement>()).TryGetProperty("detail", out var detail) ? detail.GetString() : null;

    // Gives the Office admin single permissions straight in the database (as an access manager would).
    private Task Override(string permission, bool granted) => app.WithDb(async db =>
    {
        db.Provisioning = true;
        var admin = await db.Users.SingleAsync(x => x.Email == OfficeAdmin);
        var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
        db.PermissionOverrides.Add(new PersonPermissionOverride { OrganizationId = organizationId, UserId = admin.Id, Permission = permission, Granted = granted });
        await db.SaveChangesAsync();
    });

    [Fact]
    public async Task OnlyAnOwnerGivesTheOwnerRole()
    {
        await app.SeedDemo();
        using var admin = await app.SignIn(OfficeAdmin);
        var ownerDefaults = await Defaults(admin, "Owner");
        var clerk = (await admin.GetFromJsonAsync<Page<PersonDto>>("/setup/people"))!.Items.Single(x => x.Email == RevenueClerk);

        using var created = await admin.PostAsJsonAsync("/setup/people", Person("jane.owner@example.com", "0711000011", ownerDefaults, role: "Owner"));
        Assert.Equal(HttpStatusCode.Forbidden, created.StatusCode);
        Assert.Equal("Only an Owner can give the Owner role.", await Detail(created));
        using var promoted = await admin.PutAsJsonAsync($"/setup/people/{clerk.Id}",
            new SavePerson(clerk.FirstName, clerk.LastName, clerk.Email, clerk.PhoneNumber, "Owner", "all", [], [], [.. ownerDefaults], null, clerk.Version));
        Assert.Equal(HttpStatusCode.Forbidden, promoted.StatusCode);
        Assert.Equal("Only an Owner can give the Owner role.", await Detail(promoted));

        using var owner = await app.SignIn(Owner);
        Assert.Equal(HttpStatusCode.OK, (await owner.PostAsJsonAsync("/setup/people", Person("jane.owner@example.com", "0711000011", ownerDefaults, role: "Owner"))).StatusCode);
    }

    [Fact]
    public async Task NonOwnersGiveOnlyRolesInsideTheirOwnPermissions()
    {
        await app.SeedDemo();
        using var admin = await app.SignIn(OfficeAdmin);
        var managerDefaults = await Defaults(admin, "Fleet manager");
        var clerk = (await admin.GetFromJsonAsync<Page<PersonDto>>("/setup/people"))!.Items.Single(x => x.Email == RevenueClerk);
        SavePerson ClerkAsManager(long version) => new(clerk.FirstName, clerk.LastName, clerk.Email, clerk.PhoneNumber, "Fleet manager", "all", [], [],
            [.. managerDefaults], null, version);

        // The Office admin lacks "See my petty cash float" and "Record spending from my float", both Fleet manager
        // defaults, so they can give that role neither on create nor on a role change.
        using var created = await admin.PostAsJsonAsync("/setup/people", Person("jane.manager@example.com", "0711000012", managerDefaults, role: "Fleet manager"));
        Assert.Equal(HttpStatusCode.Forbidden, created.StatusCode);
        Assert.Equal("You can only grant roles whose permissions you hold.", await Detail(created));
        using var changed = await admin.PutAsJsonAsync($"/setup/people/{clerk.Id}", ClerkAsManager(clerk.Version));
        Assert.Equal(HttpStatusCode.Forbidden, changed.StatusCode);
        Assert.Equal("You can only grant roles whose permissions you hold.", await Detail(changed));

        // Once their effective permissions cover the role (here through single permissions), they can give it.
        await Override("dash.float", true);
        await Override("pettycash.spend", true);
        await Override("revenue.capture", true);
        await Override("revenue.no_earnings", true);
        Assert.Equal(HttpStatusCode.OK, (await admin.PostAsJsonAsync("/setup/people", Person("jane.manager@example.com", "0711000012", managerDefaults, role: "Fleet manager"))).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await admin.PutAsJsonAsync($"/setup/people/{clerk.Id}", ClerkAsManager(clerk.Version))).StatusCode);

        // A default they still lack counts too: without "See today's capture for my vehicles" they cannot give Revenue clerk.
        using var clerkRole = await admin.PostAsJsonAsync("/setup/people", Person("jane.clerk@example.com", "0711000013", await Defaults(admin, "Revenue clerk")));
        Assert.Equal(HttpStatusCode.Forbidden, clerkRole.StatusCode);
    }

    [Fact]
    public async Task ScopedEditorsCannotEraseAssignmentsOutsideTheirScope()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var north = (await (await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North Star", "Add North Star")))
            .Content.ReadFromJsonAsync<IdResponse>())!;
        var south = (await (await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("South Line", "Add South Line")))
            .Content.ReadFromJsonAsync<IdResponse>())!;
        var defaults = await Defaults(owner, "Revenue clerk");
        using var created = await owner.PostAsJsonAsync("/setup/people",
            new SavePerson("Jane", "Njeri", "jane.scope@example.com", "0711000007", "Revenue clerk", "companies",
                [north.Id, south.Id], [], defaults.ToList(), null));
        var id = (await created.Content.ReadFromJsonAsync<IdResponse>())!.Id;

        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var admin = await db.Users.SingleAsync(x => x.Email == OfficeAdmin);
            var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
            db.SetupDataScopes.RemoveRange(db.SetupDataScopes.IgnoreQueryFilters().Where(x => x.UserId == admin.Id));
            db.SetupCompanyScopes.RemoveRange(db.SetupCompanyScopes.IgnoreQueryFilters().Where(x => x.UserId == admin.Id));
            db.SetupCompanyScopes.Add(new SetupCompanyScope
            {
                OrganizationId = organizationId,
                UserId = admin.Id,
                CompanyId = north.Id
            });
            await db.SaveChangesAsync();
            db.Provisioning = false;
        });

        using var scopedAdmin = await app.SignIn(OfficeAdmin);
        var visible = await scopedAdmin.GetFromJsonAsync<PersonDto>($"/setup/people/{id}");
        using var response = await scopedAdmin.PutAsJsonAsync($"/setup/people/{id}",
            new SavePerson(visible!.FirstName, visible.LastName, visible.Email, visible.PhoneNumber, visible.Role,
                "companies", [north.Id], [], visible.Permissions.ToList(), visible.ApprovalLimit, visible.Version)
            with { FirstName = "Janet" });
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var after = await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{id}");
        Assert.Contains(north.Id, after!.CompanyIds);
        Assert.Contains(south.Id, after.CompanyIds);

        // Refusing a wider change is right, and the refusal says why (addendum 1, section 3).
        using var widened = await scopedAdmin.PutAsJsonAsync($"/setup/people/{id}",
            new SavePerson(after.FirstName, after.LastName, after.Email, after.PhoneNumber, after.Role, "vehicles", [], [Guid.NewGuid()],
                after.Permissions.ToList(), after.ApprovalLimit, after.Version));
        Assert.Equal(HttpStatusCode.Forbidden, widened.StatusCode);
        Assert.Contains("outside your own", await Detail(widened));
        Assert.Equal(new[] { north.Id, south.Id }.Order(), (await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{id}"))!.CompanyIds.Order());
    }

    [Fact]
    public async Task AnOlderOutOfRangePolicyDoesNotBreakEveryonesScreens()
    {
        await app.SeedDemo();
        // Saved by an earlier version whose bounds were wider (one try, a day-long pause), past the database's checks.
        await app.WithDb(db => db.Database.ExecuteSqlRawAsync(
            "PRAGMA ignore_check_constraints = 1; UPDATE \"SecurityPolicies\" SET \"LockoutThreshold\" = 1, \"LockoutMinutes\" = 1440; PRAGMA ignore_check_constraints = 0;"));

        using var clerk = await app.SignIn(RevenueClerk);
        Assert.Equal(HttpStatusCode.OK, (await clerk.GetAsync("/setup/appearance")).StatusCode);
        using var owner = await app.SignIn(Owner);
        Assert.Equal(HttpStatusCode.OK, (await owner.GetAsync("/setup/organization/settings")).StatusCode);
    }

    [Fact]
    public async Task APlainRefusalGivesNoDetail()
    {
        await app.SeedDemo();
        using var clerk = await app.SignIn(RevenueClerk);
        using var refused = await clerk.GetAsync("/setup/people");
        Assert.Equal(HttpStatusCode.Forbidden, refused.StatusCode);
        var problem = await refused.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Not permitted in this organization or data scope.", problem.GetProperty("title").GetString());
        Assert.False(problem.TryGetProperty("detail", out _));
    }

    [Fact]
    public async Task CommitmentsUsersSeeRecurringItemsWithoutVehicleManagement()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (_, vehicleId) = await AddVehicle(owner);
        var today = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);
        (await owner.PostAsJsonAsync("/setup/recurring", new SaveRecurring("Insurance", RecurringKind.Cost, 900m,
            RecurrenceFrequency.Monthly, 1, false, today, null, [new VehicleShare(vehicleId, 900m)], "Add insurance",
            await ExpenseItemTestData.Id(owner, "Insurance")))).EnsureSuccessStatusCode();

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
        // Contract C7: a blank reason is replaced by the automatic one.
        using var noReason = await owner.PutAsJsonAsync("/setup/organization/settings/securityPolicy", new { value = new { lockoutThreshold = 3 }, reason = " " });
        Assert.Equal(HttpStatusCode.OK, noReason.StatusCode);
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
        Assert.Equal("Changed the wrong PIN tries before a pause to 3. Reason: Tighten lockout after audit.", entry.GetProperty("reason").GetString());
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

    [Fact]
    public void RoleDefaultsFollowWebV28()
    {
        Assert.Equal(PermissionCatalog.All.Where(x => x != "dash.capture").Order(StringComparer.Ordinal), PermissionCatalog.RolePermissions["Owner"].Order(StringComparer.Ordinal));
        var admin = PermissionCatalog.DefaultsFor("Office admin");
        Assert.All(new[] { "dash.capture", "dash.investment", "revenue.capture", "revenue.no_earnings", "bills.approve" }, x => Assert.DoesNotContain(x, admin));
        Assert.Contains("bills.capture", admin);
        Assert.Contains("dash.float", PermissionCatalog.DefaultsFor("Fleet manager"));
        Assert.Equal(["dash.capture", "dash.gaps", "revenue.view", "revenue.capture", "revenue.no_earnings"], PermissionCatalog.RolePermissions["Revenue clerk"]);
    }

    private async Task<(Guid North, Guid South, Guid NorthVehicle, Guid SouthVehicle)> TwoCompanies(HttpClient owner)
    {
        async Task<Guid> Id(HttpResponseMessage response) => (await response.Content.ReadFromJsonAsync<IdResponse>())!.Id;
        var north = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North Star", "Add North Star")));
        var south = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("South Line", "Add South Line")));
        var northVehicle = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(north, "KAA 111A", new DateOnly(2026, 1, 1), 20000m, "Add vehicle")));
        var southVehicle = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(south, "KBB 222B", new DateOnly(2026, 1, 1), 20000m, "Add vehicle")));
        return (north, south, northVehicle, southVehicle);
    }

    // Limits the Office admin to one company.
    private Task ScopeAdminTo(Guid company) => app.WithDb(async db =>
    {
        db.Provisioning = true;
        var admin = await db.Users.SingleAsync(x => x.Email == OfficeAdmin);
        var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
        db.SetupDataScopes.RemoveRange(db.SetupDataScopes.IgnoreQueryFilters().Where(x => x.UserId == admin.Id));
        db.SetupCompanyScopes.Add(new SetupCompanyScope { OrganizationId = organizationId, UserId = admin.Id, CompanyId = company });
        await db.SaveChangesAsync();
    });

    [Fact]
    public async Task PeopleShowOnlyTheCompaniesAndVehiclesTheViewerCanReach()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (north, south, northVehicle, southVehicle) = await TwoCompanies(owner);
        var defaults = await Defaults(owner, "Revenue clerk");
        var byCompany = (await (await owner.PostAsJsonAsync("/setup/people", new SavePerson("Jane", "Njeri", "jane.c@example.com", "0711000021", "Revenue clerk", "companies",
            [north, south], [], defaults.ToList(), null))).Content.ReadFromJsonAsync<IdResponse>())!.Id;
        var byVehicle = (await (await owner.PostAsJsonAsync("/setup/people", new SavePerson("John", "Njeri", "john.v@example.com", "0711000022", "Revenue clerk", "vehicles",
            [], [northVehicle, southVehicle], defaults.ToList(), null))).Content.ReadFromJsonAsync<IdResponse>())!.Id;

        var full = await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{byCompany}");
        Assert.Equal((2, 0, 0), (full!.CompanyIds.Count, full.OtherCompanies, full.OtherVehicles));

        await ScopeAdminTo(north);
        using var scoped = await app.SignIn(OfficeAdmin);
        var companies = await scoped.GetFromJsonAsync<PersonDto>($"/setup/people/{byCompany}");
        Assert.Equal([north], companies!.CompanyIds);
        Assert.Equal((1, 0), (companies.OtherCompanies, companies.OtherVehicles));
        var vehicles = await scoped.GetFromJsonAsync<PersonDto>($"/setup/people/{byVehicle}");
        Assert.Equal([northVehicle], vehicles!.VehicleIds);
        Assert.Equal((0, 1), (vehicles.OtherCompanies, vehicles.OtherVehicles));
        var listed = (await scoped.GetFromJsonAsync<Page<PersonDto>>("/setup/people"))!.Items.Single(x => x.Id == byVehicle);
        Assert.Equal([northVehicle], listed.VehicleIds);

        // Saving what the viewer can see leaves the hidden company and vehicle assigned.
        using var saved = await scoped.PutAsJsonAsync($"/setup/people/{byVehicle}", new SavePerson(vehicles.FirstName, vehicles.LastName, vehicles.Email, vehicles.PhoneNumber,
            vehicles.Role, "vehicles", [], [.. vehicles.VehicleIds], [.. vehicles.Permissions], vehicles.ApprovalLimit, vehicles.Version));
        Assert.Equal(HttpStatusCode.OK, saved.StatusCode);
        var after = await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{byVehicle}");
        Assert.Equal(new[] { northVehicle, southVehicle }.Order(), after!.VehicleIds.Order());
        Assert.Equal(0, after.OtherVehicles);
    }

    [Fact]
    public async Task MeListsTheCompaniesAndVehiclesTheCallerWouldSee()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (north, south, northVehicle, southVehicle) = await TwoCompanies(owner);

        var all = await owner.GetFromJsonAsync<MyScope>("/setup/access/me");
        Assert.True(all!.AllCompanies);
        Assert.Contains(all.Companies, x => x.Id == south);
        Assert.Contains(all.Vehicles, x => x.Id == southVehicle && x.Registration == "KBB 222B" && x.CompanyId == south);

        await ScopeAdminTo(north);
        using var scoped = await app.SignIn(OfficeAdmin);
        var mine = await scoped.GetFromJsonAsync<MyScope>("/setup/access/me");
        Assert.False(mine!.AllCompanies);
        Assert.Equal([north], mine.Companies.Select(x => x.Id));
        Assert.Equal([northVehicle], mine.Vehicles.Select(x => x.Id));
        // The same rows the lists show.
        Assert.Equal(mine.Vehicles.Select(x => x.Id), (await scoped.GetFromJsonAsync<Page<VehicleDto>>("/setup/vehicles"))!.Items.Select(x => x.Id));

        // No permission is needed: a clerk holds none of the setup ones.
        using var clerk = await app.SignIn(RevenueClerk);
        Assert.Equal(HttpStatusCode.OK, (await clerk.GetAsync("/setup/access/me")).StatusCode);
        using var signedOut = app.CreateClient();
        Assert.Equal(HttpStatusCode.Unauthorized, (await signedOut.GetAsync("/setup/access/me")).StatusCode);
    }

    public void Dispose() => app.Dispose();
}
