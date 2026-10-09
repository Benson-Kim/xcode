using System.Net;
using System.Net.Http.Json;
using Auth.Application;
using Auth.Application.Setup;
using Auth.Domain.Setup;
using Xunit;
using static Auth.Tests.RevenueTestData;

namespace Auth.Tests;

// The setup lists filter in the database, so a filtered list counts and pages its own matches.
public sealed class ListFilterTests : IDisposable
{
    private readonly AuthFactory app = new();

    [Fact]
    public async Task VehiclesFilterByCompanyAndPageTheMatchesOnly()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var joined = CalendarDate(app).AddDays(-30);
        var company = await NewCompany(owner, "Filter Fleet");
        foreach (var registration in new[] { "KFA 103F", "KFA 101F", "KFA 102F" })
            await NewVehicle(owner, company, registration, joined);
        await NewVehicle(owner, await NewCompany(owner, "Other Filter Fleet"), "KFA 100F", joined);

        var first = (await owner.GetFromJsonAsync<Page<VehicleDto>>($"/setup/vehicles?companyId={company}&pageSize=2"))!;
        Assert.Equal(3, first.Total);
        Assert.Equal(["KFA 101F", "KFA 102F"], first.Items.Select(v => v.Registration));
        var second = (await owner.GetFromJsonAsync<Page<VehicleDto>>($"/setup/vehicles?companyId={company}&pageSize=2&page=2"))!;
        Assert.Equal(["KFA 103F"], second.Items.Select(v => v.Registration));
        Assert.Equal(4, (await owner.GetFromJsonAsync<Page<VehicleDto>>("/setup/vehicles"))!.Total);
    }

    [Fact]
    public async Task PeopleFilterByRoleAndWhereTheyAreWithSigningIn()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        // A new person has no PIN yet; a second is then switched off.
        var waiting = await NewPerson(owner, "wanjiku.filter@example.com", "0711000101");
        var off = await NewPerson(owner, "otieno.filter@example.com", "0711000102");
        var version = (await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{off}"))!.Version;
        (await owner.PostAsJsonAsync($"/setup/people/{off}/deactivate", new { version, reason = "Left the company" })).EnsureSuccessStatusCode();

        async Task<Page<PersonDto>> People(string query) =>
            (await owner.GetFromJsonAsync<Page<PersonDto>>("/setup/people?pageSize=100" + query))!;
        var all = await People("");
        var active = await People("&status=active");
        var waitingOnes = await People("&status=waiting");
        var none = await People("&status=none");
        Assert.All(active.Items, p => Assert.True(p.Active && p.HasPin));
        Assert.All(waitingOnes.Items, p => Assert.True(p.Active && !p.HasPin));
        Assert.All(none.Items, p => Assert.False(p.Active));
        Assert.Contains(waiting, waitingOnes.Items.Select(p => p.Id));
        Assert.Contains(off, none.Items.Select(p => p.Id));
        Assert.True(active.Total > 0);
        Assert.Equal(all.Total, active.Total + waitingOnes.Total + none.Total);

        var clerks = await People("&role=Revenue%20clerk");
        Assert.All(clerks.Items, p => Assert.Equal("Revenue clerk", p.Role));
        Assert.Equal(all.Items.Count(p => p.Role == "Revenue clerk"), clerks.Total);
        var onePage = (await owner.GetFromJsonAsync<Page<PersonDto>>("/setup/people?pageSize=1&role=Revenue%20clerk&status=waiting"))!;
        Assert.Equal(waitingOnes.Items.Count(p => p.Role == "Revenue clerk"), onePage.Total);
        Assert.Single(onePage.Items);
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.GetAsync("/setup/people?status=asleep")).StatusCode);
    }

    [Fact]
    public async Task ScheduledItemsFilterByKindCompanyAndStatusWithRunningOnesFirst()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var joined = CalendarDate(app).AddDays(-30);
        var north = await NewCompany(owner, "North Filter");
        var south = await NewCompany(owner, "South Filter");
        var a = await NewVehicle(owner, north, "KFB 201F", joined);
        var b = await NewVehicle(owner, south, "KFB 202F", joined);
        var parking = await ExpenseItemTestData.Id(owner, "Parking");
        var start = CalendarDate(app);
        var parked = await NewItem(owner, "Filter parking", RecurringKind.Cost, a, start, parking);
        var saving = await NewItem(owner, "Filter savings", RecurringKind.Savings, b, start, null);
        var cleaning = await NewItem(owner, "Filter cleaning", RecurringKind.Cost, b, start, parking);
        (await owner.PostAsJsonAsync($"/setup/recurring/{cleaning}/stop", new StopRecurring(true, "No longer needed"))).EnsureSuccessStatusCode();

        async Task<Page<RecurringDto>> Items(string query) =>
            (await owner.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring" + query))!;
        async Task<Guid[]> Ids(string query) => [.. (await Items(query)).Items.Select(i => i.Id)];

        Assert.Equal([parked], await Ids($"?companyId={north}"));
        // Running items come first: the stopped cost, named Parking after its item, follows the savings.
        Assert.Equal([saving, cleaning], await Ids($"?companyId={south}"));
        Assert.Equal([saving], await Ids($"?companyId={south}&status=running"));
        Assert.Equal([cleaning], await Ids($"?companyId={south}&status=stopped"));
        Assert.Equal([cleaning], await Ids($"?companyId={south}&kind=cost"));
        Assert.Equal([saving], await Ids($"?companyId={south}&kind=savings"));

        var secondPage = await Items($"?companyId={south}&pageSize=1&page=2");
        Assert.Equal((2, cleaning), (secondPage.Total, Assert.Single(secondPage.Items).Id));
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.GetAsync("/setup/recurring?kind=fuel")).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.GetAsync("/setup/recurring?status=paused")).StatusCode);
    }

    private static async Task<Guid> Id(HttpResponseMessage response)
    {
        Assert.True(response.IsSuccessStatusCode, await response.Content.ReadAsStringAsync());
        return (await response.Content.ReadFromJsonAsync<IdResponse>())!.Id;
    }

    private static async Task<Guid> NewCompany(HttpClient client, string name) =>
        await Id(await client.PostAsJsonAsync("/setup/companies", new SaveCompany(name)));

    private static async Task<Guid> NewVehicle(HttpClient client, Guid company, string registration, DateOnly joined) =>
        await Id(await client.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(company, registration, joined, 7000m)));

    private static async Task<Guid> NewItem(HttpClient client, string name, RecurringKind kind, Guid vehicle, DateOnly start, Guid? item) =>
        await Id(await client.PostAsJsonAsync("/setup/recurring", new SaveRecurring(name, kind, 500m, RecurrenceFrequency.Weekly, 1, false,
            start, null, [new VehicleShare(vehicle, 500m)], ExpenseItemId: item)));

    private static async Task<Guid> NewPerson(HttpClient owner, string email, string phoneNumber)
    {
        var defaults = (await owner.GetFromJsonAsync<List<AccessRole>>("/setup/access/roles"))!.Single(x => x.Name == "Revenue clerk").Permissions;
        return await Id(await owner.PostAsJsonAsync("/setup/people",
            new SavePerson("Jane", "Filter", email, phoneNumber, "Revenue clerk", "all", [], [], defaults.ToList(), null)));
    }

    private sealed record IdResponse(Guid Id);

    public void Dispose() => app.Dispose();
}
