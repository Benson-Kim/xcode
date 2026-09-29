using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace Auth.Tests;

// Contract C5: what went into each vehicle, visible and editable only within a person's data scope.
public sealed class InvestmentTests : IDisposable
{
    private readonly AuthFactory app = new();
    private const string Owner = "antony.maina@shamayah.co.ke";
    private const string RevenueClerk = "wanjiru.kamau@zurigenesis.co.ke";

    [Fact]
    public async Task EntriesAreRecordedChangedAndRemovedWithTheirHistory()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (_, vehicle, _) = await Fleet(owner);
        var today = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);

        var refit = await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/investment", new { date = "2025-03-10", description = "Body, seats and refit", amount = 380000m }));
        var deposit = await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/investment", new { date = "2025-03-01", description = " Deposit on the unit ", amount = 1200000m }));
        var branding = await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/investment", new { date = "2025-03-18", description = "Registration", amount = 95000m }));
        foreach (var invalid in new object[]
        {
            new { date = today.AddDays(1).ToString("yyyy-MM-dd"), description = "Later", amount = 1m },
            new { date = "2025-03-01", description = " ", amount = 1m },
            new { date = "2025-03-01", description = "Nothing", amount = 0m },
            new { date = "2025-03-01", description = "Fractions", amount = 1.005m },
        })
            Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/investment", invalid)).StatusCode);

        Assert.Equal(branding, await Id(await owner.PutAsJsonAsync($"/setup/investment/{branding}", new { date = "2025-03-18", description = "Registration and branding", amount = 95000m })));
        Assert.Equal(refit, await Id(await owner.DeleteAsync($"/setup/investment/{refit}")));
        Assert.Equal(HttpStatusCode.NotFound, (await owner.DeleteAsync($"/setup/investment/{refit}")).StatusCode);

        var investment = await owner.GetFromJsonAsync<InvestmentDto>($"/setup/vehicles/{vehicle}/investment");
        Assert.Equal(1295000m, investment!.TotalInvested);
        // Nothing has come back yet: no revenue and no costs since the vehicle joined.
        Assert.Equal((0m, 0m), (investment.Returned!.Value, investment.PercentPaidOff!.Value));
        Assert.Equal([deposit, branding], investment.Entries.Select(x => x.Id));
        Assert.Equal(("Deposit on the unit", "Antony Maina"), (investment.Entries[0].Description, investment.Entries[0].RecordedBy));
        Assert.Equal("Registration and branding", investment.Entries[1].Description);

        var history = (await owner.GetFromJsonAsync<Page<HistoryEntry>>("/setup/history?pageSize=100"))!.Items.Where(x => x.Section == "investment").ToList();
        Assert.All(history, x => Assert.Equal(vehicle, x.EntityId));
        Assert.Contains(history, x => x.Reason == "Recorded investment Deposit on the unit on KDA 482M");
        Assert.Contains(history, x => x.Reason == "Changed investment Registration and branding on KDA 482M");
        Assert.Contains(history, x => x.Reason == "Removed investment Body, seats and refit on KDA 482M" && x.After == "null");

        // Money invested is never money out.
        var report = await owner.GetFromJsonAsync<VehicleReport>($"/setup/vehicles/{vehicle}/report?period=month");
        Assert.Equal(0m, report!.Costs);
    }

    [Fact]
    public async Task ViewingNeedsInvestViewAndChangingNeedsInvestManage()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (_, vehicle, _) = await Fleet(owner);
        var entry = await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/investment", new { date = "2025-03-01", description = "Deposit", amount = 1000m }));

        using var viewer = await app.SignIn(RevenueClerk);
        Assert.Equal(HttpStatusCode.Forbidden, (await viewer.GetAsync($"/setup/vehicles/{vehicle}/investment")).StatusCode);

        // Permissions and scope are checked on every request, so the grant applies without signing in again.
        await Scope(RevenueClerk, allCompanies: true, "invest.view");
        Assert.Single((await viewer.GetFromJsonAsync<InvestmentDto>($"/setup/vehicles/{vehicle}/investment"))!.Entries);
        Assert.Equal(HttpStatusCode.Forbidden, (await viewer.PostAsJsonAsync($"/setup/vehicles/{vehicle}/investment", new { date = "2025-03-01", description = "More", amount = 1m })).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await viewer.PutAsJsonAsync($"/setup/investment/{entry}", new { date = "2025-03-01", description = "More", amount = 1m })).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await viewer.DeleteAsync($"/setup/investment/{entry}")).StatusCode);
    }

    [Fact]
    public async Task AnInvestmentViewerFindsTheirVehiclesButCannotChangeThem()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (north, mine, theirs) = await Fleet(owner);
        await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{mine}/investment", new { date = "2025-03-01", description = "Deposit", amount = 1000m }));

        await Scope(RevenueClerk, allCompanies: false, "invest.view", north);
        using var viewer = await app.SignIn(RevenueClerk);
        var listed = await viewer.GetFromJsonAsync<Page<VehicleDto>>("/setup/vehicles");
        Assert.Equal([mine], listed!.Items.Select(x => x.Id));
        Assert.Equal(1000m, (await viewer.GetFromJsonAsync<InvestmentDto>($"/setup/vehicles/{mine}/investment"))!.TotalInvested);

        var vehicle = new { companyId = north, registration = "KDA 482M", joinedOn = "2026-01-01", weeklyTarget = 9000m };
        Assert.Equal(HttpStatusCode.Forbidden, (await viewer.PostAsJsonAsync("/setup/vehicles", vehicle with { registration = "KDC 222C" })).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await viewer.PutAsJsonAsync($"/setup/vehicles/{mine}", vehicle)).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await viewer.PostAsJsonAsync($"/setup/vehicles/{mine}/retire", new { leftOn = "2026-02-01" })).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await viewer.PostAsJsonAsync($"/setup/vehicles/{mine}/restore", new { })).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await viewer.GetAsync("/setup/vehicles/company-options")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await viewer.PostAsJsonAsync($"/setup/vehicles/{mine}/investment", new { date = "2025-03-01", description = "More", amount = 1m })).StatusCode);
    }

    [Fact]
    public async Task AScopedPersonSeesAndChangesOnlyTheirVehiclesInvestment()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (north, mine, theirs) = await Fleet(owner);
        var ours = await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{mine}/investment", new { date = "2025-03-01", description = "Deposit", amount = 1000m }));
        var other = await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{theirs}/investment", new { date = "2025-03-01", description = "Deposit", amount = 2000m }));

        await Scope(RevenueClerk, allCompanies: false, "invest.manage", "audit.view", north);
        using var clerk = await app.SignIn(RevenueClerk);
        Assert.Equal(1000m, (await clerk.GetFromJsonAsync<InvestmentDto>($"/setup/vehicles/{mine}/investment"))!.TotalInvested);
        Assert.Equal(HttpStatusCode.NotFound, (await clerk.GetAsync($"/setup/vehicles/{theirs}/investment")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await clerk.PostAsJsonAsync($"/setup/vehicles/{theirs}/investment", new { date = "2025-03-01", description = "More", amount = 1m })).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await clerk.PutAsJsonAsync($"/setup/investment/{other}", new { date = "2025-03-01", description = "Less", amount = 1m })).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await clerk.DeleteAsync($"/setup/investment/{other}")).StatusCode);
        (await clerk.PutAsJsonAsync($"/setup/investment/{ours}", new { date = "2025-03-02", description = "Deposit", amount = 1500m })).EnsureSuccessStatusCode();

        var history = (await clerk.GetFromJsonAsync<Page<HistoryEntry>>("/setup/history?pageSize=100"))!.Items.Where(x => x.Section == "investment");
        Assert.All(history, x => Assert.Equal(mine, x.EntityId));
        Assert.Equal(2000m, (await owner.GetFromJsonAsync<InvestmentDto>($"/setup/vehicles/{theirs}/investment"))!.TotalInvested);
    }

    // Two companies with one vehicle each.
    private static async Task<(Guid North, Guid Mine, Guid Theirs)> Fleet(HttpClient owner)
    {
        var north = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North Star", "Add North Star")));
        var south = await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("South Line", "Add South Line")));
        var mine = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(north, "KDA 482M", new DateOnly(2026, 1, 1), 15000m, "Add")));
        var theirs = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(south, "KDB 111A", new DateOnly(2026, 1, 1), 15000m, "Add")));
        return (north, mine, theirs);
    }

    private async Task Scope(string email, bool allCompanies, params object[] grants) => await app.WithDb(async db =>
    {
        db.Provisioning = true;
        var user = await db.Users.SingleAsync(x => x.Email == email);
        var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
        foreach (var grant in grants)
            if (grant is string permission)
                db.PermissionOverrides.Add(new PersonPermissionOverride { OrganizationId = organizationId, UserId = user.Id, Permission = permission, Granted = true });
            else
                db.SetupCompanyScopes.Add(new SetupCompanyScope { OrganizationId = organizationId, UserId = user.Id, CompanyId = (Guid)grant });
        if (allCompanies)
            db.SetupDataScopes.Add(new SetupDataScope { OrganizationId = organizationId, UserId = user.Id, AllCompanies = true });
        await db.SaveChangesAsync();
    });

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
