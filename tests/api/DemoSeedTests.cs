using System.Net;
using System.Net.Http.Json;
using Auth.Application;
using Auth.Application.Setup;
using Auth.Domain.Setup;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace Auth.Tests;

public sealed class DemoSeedTests : IDisposable
{
    private readonly AuthFactory app = new();

    [Fact]
    public async Task DesignLoginsSignInWithTheirPins_AndReseedingKeepsChangedPins()
    {
        await app.WithDb(async db => { await db.Database.EnsureCreatedAsync(); await AuthFactory.AddOrganization(db); await DemoSeed.Run(db); });
        using var client = app.CreateClient();
        foreach (var (phoneNumber, email, pin) in DemoSeed.Logins.Where(l => l.Pin is not null))
        {
            // A correct PIN on an untrusted phone asks for an email code; a wrong one is a 401.
            var response = await client.PostAsJsonAsync("/auth/sign-in", new AuthRequest(PhoneNumber: phoneNumber, Pin: pin!, DeviceId: "new-phone"));
            Assert.Equal(HttpStatusCode.Accepted, response.StatusCode);
        }
        await app.WithDb(async db =>
        {
            Assert.Null((await db.Users.SingleAsync(u => u.Email == "brian.mwangi@metrotrans.co.ke")).PinHash);
            var owner = await db.Users.SingleAsync(u => u.Email == "antony.maina@shamayah.co.ke");
            owner.SetPin(PinHasher.Hash("9731"));
            await db.SaveChangesAsync();
            await DemoSeed.Run(db);
            Assert.Equal(DemoSeed.Logins.Length, await db.Users.CountAsync());
            Assert.True(PinHasher.Verify("9731", (await db.Users.AsNoTracking().SingleAsync(u => u.Id == owner.Id)).PinHash!));
        });
    }

    [Fact]
    public async Task TheDesignsExpenseCatalogIsSeededOnceAndLocalChangesSurviveReseeding()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn("antony.maina@shamayah.co.ke");
        var options = await owner.GetFromJsonAsync<List<ExpenseItemOption>>("/setup/expense-items/options");
        Assert.Equal(13, options!.Count);
        Assert.Contains(options, x => x is { Name: "Tyres", CategoryName: "Garage and repairs", Bucket: ExpenseBucket.RepairsAndMaintenance });
        Assert.Contains(options, x => x is { Name: "Insurance", CategoryName: "Charges", Bucket: ExpenseBucket.RecurringCharges });
        Assert.Contains(options, x => x is { Name: "Loan repayment", CategoryName: "Loans", Bucket: ExpenseBucket.LoanRepayments });

        var loans = options.Single(x => x.CategoryName == "Loans").CategoryId;
        (await owner.PutAsJsonAsync($"/setup/expense-categories/{loans}", new { name = "Bank loans", bucket = 3 })).EnsureSuccessStatusCode();
        await app.WithDb(db => DemoSeed.Run(db));

        var categories = await owner.GetFromJsonAsync<Page<ExpenseCategoryDto>>("/setup/expense-categories");
        Assert.Equal(["Bank loans", "Charges", "Garage and repairs"], categories!.Items.Select(x => x.Name));
        Assert.Equal(13, categories.Items.Sum(x => x.Items.Count));
    }

    // A "vehicles" scope with no vehicles chosen cannot be saved, so every change to the demo Fleet manager was refused.
    [Fact]
    public async Task TheFleetManagerHasAScopeThatCanBeSavedAndKeepsOneChosenLater()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn("antony.maina@shamayah.co.ke");
        async Task<PersonDto> Manager() => (await owner.GetFromJsonAsync<Page<PersonDto>>("/setup/people?pageSize=100"))!.Items.Single(x => x.Role == "Fleet manager");
        SavePerson Edited(PersonDto x, string scopeMode, List<Guid> companyIds) =>
            new(x.FirstName, x.LastName, x.Email, x.PhoneNumber, x.Role, scopeMode, companyIds, [.. x.VehicleIds], [.. x.Permissions], 5000m, x.Version);

        var manager = await Manager();
        Assert.Equal("all", manager.ScopeMode);
        (await owner.PutAsJsonAsync($"/setup/people/{manager.Id}", Edited(manager, manager.ScopeMode, [.. manager.CompanyIds]))).EnsureSuccessStatusCode();

        // A scope chosen during development survives reseeding.
        var company = (await (await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North Star"))).Content.ReadFromJsonAsync<IdResponse>())!.Id;
        (await owner.PutAsJsonAsync($"/setup/people/{manager.Id}", Edited(await Manager(), "companies", [company]))).EnsureSuccessStatusCode();
        await app.WithDb(db => DemoSeed.Run(db));
        manager = await Manager();
        Assert.Equal(("companies", company), (manager.ScopeMode, Assert.Single(manager.CompanyIds)));
    }

    private sealed record IdResponse(Guid Id);

    public void Dispose() => app.Dispose();
}
