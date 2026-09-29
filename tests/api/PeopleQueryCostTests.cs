using System.Net;
using System.Net.Http.Json;
using Auth.Application;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xunit;
using Xunit.Abstractions;

namespace Auth.Tests;

// What the people screens and setup calls ask of the database (counted by DatabaseProbe), and proof that scoped
// people lists still show exactly the people the visibility rules allow.
public sealed class PeopleQueryCostTests(ITestOutputHelper output) : IDisposable
{
    private readonly AuthFactory app = new();
    private const string Owner = "antony.maina@shamayah.co.ke";
    private const string OfficeAdmin = "peter.otieno@zurigenesis.co.ke";

    private sealed record IdResponse(Guid Id);

    private static async Task<Guid> Id(HttpResponseMessage response)
    {
        response.EnsureSuccessStatusCode();
        return (await response.Content.ReadFromJsonAsync<IdResponse>())!.Id;
    }

    // Adds people straight to the database: each has a role, an all-companies scope and one single permission.
    private Task AddPeople(int count) => app.WithDb(async db =>
    {
        db.Provisioning = true;
        var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
        var clerk = await db.Roles.IgnoreQueryFilters().SingleAsync(x => x.Name == "Revenue clerk");
        for (var i = 0; i < count; i++)
        {
            var user = new User { Email = $"person{i:D3}@example.com", PhoneNumber = $"+2547{i:D8}" };
            db.Users.Add(user);
            db.Memberships.Add(new OrganizationMembership { OrganizationId = organizationId, UserId = user.Id, FirstName = "Person", LastName = $"P{i:D3}" });
            db.PersonRoles.Add(new PersonRole { OrganizationId = organizationId, UserId = user.Id, RoleId = clerk.Id });
            db.SetupDataScopes.Add(new SetupDataScope { OrganizationId = organizationId, UserId = user.Id, AllCompanies = true });
            db.PermissionOverrides.Add(new PersonPermissionOverride { OrganizationId = organizationId, UserId = user.Id, Permission = "reports.view", Granted = true });
        }
        await db.SaveChangesAsync();
    });

    [Fact]
    public async Task APageOfPeopleLoadsOnlyThatPage()
    {
        await app.SeedDemo();
        await AddPeople(200);
        using var owner = await app.SignIn(Owner);

        app.Database.Reset();
        var page = await owner.GetFromJsonAsync<Page<PersonDto>>("/setup/people?page=2&pageSize=25");
        output.WriteLine($"GET /setup/people page 2 (25 of {page!.Total}): {app.Database.Commands} commands, {app.Database.Rows} rows read");

        Assert.Equal(204, page.Total);
        Assert.Equal([.. Enumerable.Range(21, 25).Select(i => $"person{i:D3}@example.com")], page.Items.Select(x => x.Email));
        Assert.All(page.Items, x => Assert.Contains("reports.view", x.Permissions));
        // Loading everyone's access state reads more than a thousand rows here; a page and its own related rows stay
        // near 25 per table.
        Assert.True(app.Database.Rows < 250, $"{app.Database.Rows} rows read");

        app.Database.Reset();
        var one = await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{page.Items[0].Id}");
        output.WriteLine($"GET /setup/people/{{id}}: {app.Database.Commands} commands, {app.Database.Rows} rows read");
        Assert.Equal("person021@example.com", one!.Email);
        Assert.True(app.Database.Rows < 40, $"{app.Database.Rows} rows read");
    }

    [Fact]
    public async Task ScopedPeopleListsShowExactlyThePeopleInScope()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var a = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("Alpha", "Add Alpha")));
        var b = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("Beta", "Add Beta")));
        var vA = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(a, "KDA 100A", new DateOnly(2026, 1, 1), 1000m, "Add")));
        var vB = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(b, "KDB 200B", new DateOnly(2026, 1, 1), 1000m, "Add")));
        var vB2 = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(b, "KDB 300B", new DateOnly(2026, 1, 1), 1000m, "Add")));
        var clerk = (await owner.GetFromJsonAsync<List<AccessRole>>("/setup/access/roles"))!.Single(x => x.Name == "Revenue clerk").Permissions.ToList();
        var phone = 0;
        async Task<Guid> Person(string name, string scope, List<Guid> companies, List<Guid> vehicles) =>
            await Id(await owner.PostAsJsonAsync("/setup/people", new SavePerson("Jane", name, $"{name}@example.com", $"071100{++phone:D4}",
                "Revenue clerk", scope, companies, vehicles, clerk, null)));
        var people = new Dictionary<string, Guid>
        {
            ["alpha"] = await Person("alpha", "companies", [a], []),
            ["beta"] = await Person("beta", "companies", [b], []),
            ["both"] = await Person("both", "companies", [a, b], []),
            ["vehicle-a"] = await Person("vehicle-a", "vehicles", [], [vA]),
            ["vehicle-b"] = await Person("vehicle-b", "vehicles", [], [vB]),
            ["vehicle-b2"] = await Person("vehicle-b2", "vehicles", [], [vB2]),
            ["everything"] = await Person("everything", "all", [], [])
        };

        async Task ScopeAdmin(Guid? company, Guid? vehicle) => await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var admin = await db.Users.SingleAsync(x => x.Email == OfficeAdmin);
            var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
            db.SetupDataScopes.RemoveRange(db.SetupDataScopes.IgnoreQueryFilters().Where(x => x.UserId == admin.Id));
            db.SetupCompanyScopes.RemoveRange(db.SetupCompanyScopes.IgnoreQueryFilters().Where(x => x.UserId == admin.Id));
            db.SetupVehicleScopes.RemoveRange(db.SetupVehicleScopes.IgnoreQueryFilters().Where(x => x.UserId == admin.Id));
            if (company is Guid c) db.SetupCompanyScopes.Add(new SetupCompanyScope { OrganizationId = organizationId, UserId = admin.Id, CompanyId = c });
            if (vehicle is Guid v) db.SetupVehicleScopes.Add(new SetupVehicleScope { OrganizationId = organizationId, UserId = admin.Id, VehicleId = v });
            await db.SaveChangesAsync();
        });
        using var admin = await app.SignIn(OfficeAdmin);
        async Task Sees(params string[] expected)
        {
            var page = (await admin.GetFromJsonAsync<Page<PersonDto>>("/setup/people?pageSize=100"))!;
            Assert.Equal([.. expected.Select(x => $"{x}@example.com").Append(OfficeAdmin).Order()], page.Items.Select(x => x.Email).Order());
            Assert.Equal(expected.Length + 1, page.Total);
            foreach (var (name, id) in people)
                Assert.Equal(expected.Contains(name) ? HttpStatusCode.OK : HttpStatusCode.NotFound, (await admin.GetAsync($"/setup/people/{id}")).StatusCode);
        }

        // A company scope sees people scoped to that company, or to one of its vehicles.
        await ScopeAdmin(a, null);
        await Sees("alpha", "both", "vehicle-a");

        // A vehicle scope sees people scoped to that vehicle, or to the company that vehicle belongs to, but not
        // people scoped to other vehicles of that company.
        await ScopeAdmin(null, vB);
        await Sees("beta", "both", "vehicle-b");
    }

    [Fact]
    public async Task PermissionsAreResolvedOncePerRequest()
    {
        await app.SeedDemo();
        using var scope = app.Services.CreateScope();
        var organizations = scope.ServiceProvider.GetRequiredService<IOrganizationRepository>();
        var userId = Guid.NewGuid();

        app.Database.Reset();
        await organizations.Permissions(userId, CancellationToken.None);
        var first = app.Database.Commands;
        await organizations.Permissions(userId, CancellationToken.None);
        output.WriteLine($"Permissions(userId): first call {first} commands, second call {app.Database.Commands - first}");

        Assert.True(first > 0);
        Assert.Equal(first, app.Database.Commands);
    }

    [Fact]
    public async Task SavingAPersonCountsItsQueries()
    {
        await app.SeedDemo();
        await AddPeople(200);
        using var owner = await app.SignIn(Owner);
        var clerk = (await owner.GetFromJsonAsync<Page<PersonDto>>("/setup/people?pageSize=100"))!.Items.Single(x => x.Email == "wanjiru.kamau@zurigenesis.co.ke");

        app.Database.Reset();
        (await owner.PutAsJsonAsync($"/setup/people/{clerk.Id}", new SavePerson(clerk.FirstName, "Renamed", clerk.Email, clerk.PhoneNumber,
            clerk.Role, "all", [], [], [.. clerk.Permissions], clerk.ApprovalLimit, clerk.Version))).EnsureSuccessStatusCode();
        output.WriteLine($"PUT /setup/people/{{id}}: {app.Database.Commands} commands, {app.Database.Rows} rows read");
        Assert.Equal(1, app.Database.Transactions);
    }

    [Fact]
    public async Task SetupReadsOpenNoTransaction()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);

        foreach (var path in new[] { "/setup/people", "/setup/access/catalog", "/setup/access/scope-options", "/setup/companies", "/setup/vehicles", "/setup/recurring", "/setup/history" })
        {
            app.Database.Reset();
            (await owner.GetAsync(path)).EnsureSuccessStatusCode();
            Assert.True(app.Database.Transactions == 0, $"{path} opened {app.Database.Transactions} transaction(s)");
        }

        // Listing roles may create missing ones, so it stays a write.
        app.Database.Reset();
        (await owner.GetAsync("/setup/access/roles")).EnsureSuccessStatusCode();
        Assert.Equal(1, app.Database.Transactions);
    }

    [Fact]
    public async Task AReadThatChangesStateFailsInsteadOfDroppingTheChange()
    {
        await app.SeedDemo();
        using var scope = app.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AuthDb>();
        var unitOfWork = scope.ServiceProvider.GetRequiredService<IUnitOfWork>();

        await Assert.ThrowsAsync<InvalidOperationException>(() => unitOfWork.Read(() =>
        {
            db.Users.Add(new User { Email = "read.write@example.com" });
            return Task.FromResult(0);
        }, CancellationToken.None));
        Assert.False(await db.Users.AnyAsync(x => x.Email == "read.write@example.com"));
    }

    public void Dispose() => app.Dispose();
}
