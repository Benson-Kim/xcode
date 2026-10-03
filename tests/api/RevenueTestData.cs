using Auth.Domain;
using Auth.Domain.Setup;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Tests;

/// <summary>Direct database seeding for revenue tests, so each test sets up weeks of history in one step.</summary>
internal static class RevenueTestData
{
    public const string Owner = "antony.maina@shamayah.co.ke";
    public const string Admin = "peter.otieno@zurigenesis.co.ke";
    public const string Clerk = "wanjiru.kamau@zurigenesis.co.ke";

    // A Thursday at least a week back keeps week boundaries and "today" independent of the day the tests run.
    public static DateOnly PinnedThursday(AuthFactory app)
    {
        var date = CalendarDate(app).AddDays(-7);
        while (date.DayOfWeek != DayOfWeek.Thursday) date = date.AddDays(-1);
        return date;
    }

    public static DateOnly CalendarDate(AuthFactory app) => DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);

    public static Task SetBusinessDate(AuthFactory app, DateOnly date) => Provision(app, async db =>
    {
        var organization = await db.Organizations.IgnoreQueryFilters().SingleAsync();
        organization.ChangeBusinessDate(date, CalendarDate(app));
    });

    public static Task SetFirstDayOfWeek(AuthFactory app, DayOfWeek day) => Provision(app, async db =>
        (await db.Localizations.IgnoreQueryFilters().SingleAsync()).FirstDayOfWeek = (int)day);

    public static async Task<Guid> Company(AuthFactory app, string name)
    {
        var id = Guid.Empty;
        await Provision(app, async db =>
        {
            var company = new PsvCompany(await OrganizationId(db), name);
            db.Set<PsvCompany>().Add(company);
            id = company.Id;
        });
        return id;
    }

    public static async Task<Guid> Vehicle(AuthFactory app, Guid companyId, string registration, DateOnly joinedOn,
        decimal weeklyTarget = 7000m, DateOnly? leftOn = null, (decimal Target, DateOnly From)? revision = null)
    {
        var id = Guid.Empty;
        await Provision(app, async db =>
        {
            var vehicle = new FleetVehicle(await OrganizationId(db), companyId, new VehicleRegistration(registration), joinedOn, weeklyTarget);
            if (revision is { } change) vehicle.Update(companyId, joinedOn, change.Target, change.From);
            if (leftOn is not null) vehicle.Retire(leftOn.Value, leftOn.Value);
            db.Set<FleetVehicle>().Add(vehicle);
            id = vehicle.Id;
        });
        return id;
    }

    public static Task Records(AuthFactory app, Guid vehicleId, DateOnly from, DateOnly through, decimal amount = 1000m, params DateOnly[] skip) =>
        Provision(app, async db =>
        {
            var organizationId = await OrganizationId(db);
            var actor = (await db.Users.SingleAsync(x => x.Email == Owner)).Id;
            for (var date = from; date <= through; date = date.AddDays(1))
                if (!skip.Contains(date))
                    db.Set<RevenueRecord>().Add(new(organizationId, vehicleId, date, new(amount, null, null), app.Clock.UtcNow.ToUniversalTime(), actor));
        });

    public static Task ScopeToCompany(AuthFactory app, string email, Guid companyId) => Provision(app, async db =>
    {
        var organizationId = await OrganizationId(db);
        var user = (await db.Users.SingleAsync(x => x.Email == email)).Id;
        db.SetupCompanyScopes.Add(new() { OrganizationId = organizationId, UserId = user, CompanyId = companyId });
    });

    // A denied permission also removes the permissions that depend on it.
    public static Task Deny(AuthFactory app, string email, string permission) => Provision(app, async db =>
    {
        var organizationId = await OrganizationId(db);
        var user = (await db.Users.SingleAsync(x => x.Email == email)).Id;
        db.PermissionOverrides.Add(new() { OrganizationId = organizationId, UserId = user, Permission = permission, Granted = false });
    });

    // An override, so a test states the permission it needs rather than relying on a role's defaults (D10 changed them).
    public static Task Grant(AuthFactory app, string email, string permission) => Provision(app, async db =>
    {
        var organizationId = await OrganizationId(db);
        var user = (await db.Users.SingleAsync(x => x.Email == email)).Id;
        db.PermissionOverrides.Add(new() { OrganizationId = organizationId, UserId = user, Permission = permission, Granted = true });
    });

    private static async Task<Guid> OrganizationId(AuthDb db) => (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;

    private static Task Provision(AuthFactory app, Func<AuthDb, Task> change) => app.WithDb(async db =>
    {
        db.Provisioning = true;
        await change(db);
        await db.SaveChangesAsync();
        db.Provisioning = false;
    });
}
