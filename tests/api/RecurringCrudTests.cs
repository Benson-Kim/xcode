using System.Net;
using System.Net.Http.Headers;
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

public sealed class RecurringCrudTests : IDisposable
{
    private readonly AuthFactory app = new();

    [Fact]
    public async Task OwnerCanCreateReadUpdateAndStopARecurringItem()
    {
        using var client = await CreateOwnerClient();
        var today = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);

        using var createCompany = await client.PostAsJsonAsync("/setup/companies", new SaveCompany("CRUD Test Fleet", "Create recurring CRUD test fleet"));
        Assert.Equal(HttpStatusCode.OK, createCompany.StatusCode);
        var company = await createCompany.Content.ReadFromJsonAsync<IdResponse>();
        Assert.NotNull(company);

        using var createVehicle = await client.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(
            company.Id,
            "KQA 321M",
            today,
            20000m,
            "Create recurring CRUD test vehicle"));
        Assert.Equal(HttpStatusCode.OK, createVehicle.StatusCode);
        var vehicle = await createVehicle.Content.ReadFromJsonAsync<IdResponse>();
        Assert.NotNull(vehicle);

        // A cost picks an expense item: the name typed and the old category are ignored.
        var parking = await ExpenseItemTestData.Id(client, "Parking");
        var create = new SaveRecurring(
            "Typed name",
            RecurringKind.Cost,
            CostCategory.RunningCosts,
            1200m,
            RecurrenceFrequency.Weekly,
            6,
            false,
            today.AddDays(1),
            null,
            [new VehicleShare(vehicle.Id, 1200m)],
            "Create recurring CRUD test item",
            parking,
            "  Stage fees  ");
        using var createItem = await client.PostAsJsonAsync("/setup/recurring", create);
        Assert.Equal(HttpStatusCode.OK, createItem.StatusCode);
        var created = await createItem.Content.ReadFromJsonAsync<IdResponse>();
        Assert.NotNull(created);

        var afterCreate = await client.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring");
        var createdItem = Assert.Single(afterCreate!.Items);
        Assert.Equal(created.Id, createdItem.Id);
        Assert.Equal("Parking", createdItem.Name);
        Assert.Null(createdItem.Category);
        Assert.Equal(parking, createdItem.ExpenseItemId);
        Assert.Equal("Parking", createdItem.ExpenseItemName);
        Assert.Equal(ExpenseBucket.RecurringCharges, createdItem.Bucket);
        Assert.Equal("Stage fees", createdItem.Note);
        Assert.Equal(1200m, createdItem.Amount);
        Assert.Equal(RecurrenceFrequency.Weekly, createdItem.Frequency);
        Assert.Equal(6, createdItem.Day);

        var update = new SaveRecurring(
            "Fuel reserve revised",
            RecurringKind.Savings,
            null,
            1450m,
            RecurrenceFrequency.Monthly,
            null,
            true,
            today.AddDays(1),
            null,
            [new VehicleShare(vehicle.Id, 1450m)],
            "Update recurring CRUD test item");
        using var updateItem = await client.PutAsJsonAsync($"/setup/recurring/{created.Id}", update);
        Assert.Equal(HttpStatusCode.OK, updateItem.StatusCode);

        var afterUpdate = await client.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring");
        var updatedItem = Assert.Single(afterUpdate!.Items);
        Assert.Equal(created.Id, updatedItem.Id);
        Assert.Equal("Fuel reserve revised", updatedItem.Name);
        Assert.Null(updatedItem.ExpenseItemId);
        Assert.Null(updatedItem.Bucket);
        Assert.Equal(1450m, updatedItem.Amount);
        Assert.Equal(RecurrenceFrequency.Monthly, updatedItem.Frequency);
        Assert.True(updatedItem.LastDay);
        Assert.Equal(2, updatedItem.Revision);

        using var stopItem = await client.PostAsJsonAsync($"/setup/recurring/{created.Id}/stop", new StopRecurring(true, "Stop recurring CRUD test item"));
        Assert.Equal(HttpStatusCode.OK, stopItem.StatusCode);

        var afterStop = await client.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring");
        var stoppedItem = Assert.Single(afterStop!.Items);
        Assert.Equal(created.Id, stoppedItem.Id);
        Assert.Equal(today, stoppedItem.StoppedFrom);

        var priorBusinessDate = today.AddDays(-1);
        using var rollBackBusinessDate = await client.PutAsJsonAsync("/setup/organization/settings/businessDate",
            new { value = priorBusinessDate.ToString("yyyy-MM-dd") });
        Assert.Equal(HttpStatusCode.OK, rollBackBusinessDate.StatusCode);

        using var reviseBeforeScheduledStop = await client.PutAsJsonAsync($"/setup/recurring/{created.Id}", update with
        {
            Name = "Fuel reserve before scheduled stop",
            Reason = "Revise before the scheduled stop"
        });
        Assert.Equal(HttpStatusCode.OK, reviseBeforeScheduledStop.StatusCode);

        var revisedBeforeStop = Assert.Single((await client.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring"))!.Items);
        Assert.Equal(3, revisedBeforeStop.Revision);
        Assert.Equal("Fuel reserve before scheduled stop", revisedBeforeStop.Name);
        Assert.Equal(today, revisedBeforeStop.StoppedFrom);

        // A pending stop is never quietly re-dated (D16): it is cancelled, then set again on the day wanted.
        using var stopEarlier = await client.PostAsJsonAsync($"/setup/recurring/{created.Id}/stop",
            new StopRecurring(true, "Stop before the scheduled date"));
        Assert.Equal(HttpStatusCode.BadRequest, stopEarlier.StatusCode);
        Assert.Equal(today, Assert.Single((await client.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring"))!.Items).StoppedFrom);

        using var cancelStop = await client.PostAsJsonAsync($"/setup/recurring/{created.Id}/restore", new { });
        Assert.Equal(HttpStatusCode.OK, cancelStop.StatusCode);
        Assert.Null(Assert.Single((await client.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring"))!.Items).StoppedFrom);

        using var stopAgain = await client.PostAsJsonAsync($"/setup/recurring/{created.Id}/stop",
            new StopRecurring(true, "Stop before the scheduled date"));
        Assert.Equal(HttpStatusCode.OK, stopAgain.StatusCode);
        Assert.Equal(priorBusinessDate, Assert.Single((await client.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring"))!.Items).StoppedFrom);

        // A stop that has taken effect stays final.
        using var cancelEffective = await client.PostAsJsonAsync($"/setup/recurring/{created.Id}/restore", new { });
        Assert.Equal(HttpStatusCode.BadRequest, cancelEffective.StatusCode);
    }

    // The saved total always equals the shares listed with it, so the editor opens balanced; what still posts is apart.
    [Fact]
    public async Task RetiredSharesStayInTheTotalAndActiveAmountSaysWhatStillPosts()
    {
        using var client = await CreateOwnerClient();
        var today = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);
        var company = (await (await client.PostAsJsonAsync("/setup/companies", new SaveCompany("Retire Fleet"))).Content.ReadFromJsonAsync<IdResponse>())!.Id;
        async Task<Guid> Vehicle(string registration) => (await (await client.PostAsJsonAsync("/setup/vehicles",
            new SaveVehicle(company, registration, today, 20000m))).Content.ReadFromJsonAsync<IdResponse>())!.Id;
        var (first, second) = (await Vehicle("KQA 321M"), await Vehicle("KQA 322M"));
        (await client.PostAsJsonAsync("/setup/recurring", new SaveRecurring(null, RecurringKind.Cost, null, 1000m, RecurrenceFrequency.Weekly, 1, false,
            today, null, [new VehicleShare(first, 700m), new VehicleShare(second, 300m)], ExpenseItemId: await ExpenseItemTestData.Id(client, "Parking"))))
            .EnsureSuccessStatusCode();
        async Task<RecurringDto> Item() => Assert.Single((await client.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring"))!.Items);
        Task Retire(Guid vehicle) => client.PostAsJsonAsync($"/setup/vehicles/{vehicle}/retire", new VehicleLifecycleRequest(today)).ContinueWith(t => t.Result.EnsureSuccessStatusCode());

        Assert.Equal((1000m, 1000m), ((await Item()).Amount, (await Item()).ActiveAmount));
        await Retire(second);
        var partlyRetired = await Item();
        Assert.Equal((1000m, 700m, 1000m), (partlyRetired.Amount, partlyRetired.ActiveAmount, partlyRetired.Allocations.Sum(a => a.Amount)));
        await Retire(first);
        var allRetired = await Item();
        Assert.Equal((1000m, 0m), (allRetired.Amount, allRetired.ActiveAmount));
    }

    // The vehicle picker offers only vehicles a new share may use, even when the business date is set before one joined.
    [Fact]
    public async Task ThePickerOffersOnlyVehiclesANewShareCanUse()
    {
        using var client = await CreateOwnerClient();
        var company = (await (await client.PostAsJsonAsync("/setup/companies", new SaveCompany("Picker Fleet"))).Content.ReadFromJsonAsync<IdResponse>())!.Id;
        var early = (await (await client.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(company, "KQA 331M", new DateOnly(2026, 1, 1), 20000m))).Content.ReadFromJsonAsync<IdResponse>())!.Id;
        var late = (await (await client.PostAsJsonAsync("/setup/vehicles", new SaveVehicle(company, "KQA 332M", new DateOnly(2026, 3, 10), 20000m))).Content.ReadFromJsonAsync<IdResponse>())!.Id;
        (await client.PutAsJsonAsync("/setup/organization/settings/businessDate", new { value = "2026-03-05" })).EnsureSuccessStatusCode();

        var options = await client.GetFromJsonAsync<List<VehicleOption>>("/setup/recurring/vehicle-options");
        Assert.Equal([early], options!.Select(x => x.Id));
        using var refused = await client.PostAsJsonAsync("/setup/recurring", new SaveRecurring(null, RecurringKind.Cost, null, 100m, RecurrenceFrequency.Weekly, 1, false,
            new DateOnly(2026, 3, 5), null, [new VehicleShare(late, 100m)], ExpenseItemId: await ExpenseItemTestData.Id(client, "Parking")));
        Assert.Equal(HttpStatusCode.BadRequest, refused.StatusCode);
    }

    // "Active" means FleetVehicle.ActiveOn everywhere: joined by the business date and not yet left.
    [Fact]
    public async Task AVehicleThatHasNotJoinedYetIsInactiveInEveryList()
    {
        using var client = await CreateOwnerClient();
        var today = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);
        var company = (await (await client.PostAsJsonAsync("/setup/companies", new SaveCompany("Join Fleet"))).Content.ReadFromJsonAsync<IdResponse>())!.Id;
        async Task<Guid> Vehicle(string registration, DateOnly joined) => (await (await client.PostAsJsonAsync("/setup/vehicles",
            new SaveVehicle(company, registration, joined, 20000m))).Content.ReadFromJsonAsync<IdResponse>())!.Id;
        var (early, late) = (await Vehicle("KQA 341M", new DateOnly(2026, 1, 1)), await Vehicle("KQA 342M", new DateOnly(2026, 3, 10)));
        (await client.PostAsJsonAsync("/setup/recurring", new SaveRecurring(null, RecurringKind.Cost, null, 1000m, RecurrenceFrequency.Weekly, 1, false,
            today, null, [new VehicleShare(early, 600m), new VehicleShare(late, 400m)], ExpenseItemId: await ExpenseItemTestData.Id(client, "Parking"))))
            .EnsureSuccessStatusCode();
        (await client.PutAsJsonAsync("/setup/organization/settings/businessDate", new { value = "2026-03-05" })).EnsureSuccessStatusCode();

        var vehicles = (await client.GetFromJsonAsync<Page<VehicleDto>>("/setup/vehicles"))!.Items;
        var notJoined = vehicles.Single(x => x.Id == late);
        Assert.Equal((false, 0m, 0), (notJoined.Active, notJoined.WeeklyTarget, notJoined.RecurringItems));
        var joined = vehicles.Single(x => x.Id == early);
        Assert.Equal((true, 20000m, 1), (joined.Active, joined.WeeklyTarget, joined.RecurringItems));
        Assert.Equal(1, (await client.GetFromJsonAsync<Page<CompanyDto>>("/setup/companies"))!.Items.Single(x => x.Id == company).VehicleCount);
        var scope = await client.GetFromJsonAsync<JsonElement>("/setup/access/scope-options");
        Assert.DoesNotContain(scope.GetProperty("vehicles").EnumerateArray(), x => x.GetProperty("id").GetGuid() == late);
        var item = Assert.Single((await client.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring"))!.Items);
        Assert.Equal((1000m, 600m, false), (item.Amount, item.ActiveAmount, item.Allocations.Single(a => a.VehicleId == late).Active));
    }

    private async Task<HttpClient> CreateOwnerClient()
    {
        await app.WithDb(async db =>
        {
            await db.Database.EnsureCreatedAsync();
            db.Provisioning = true;
            var organization = new Organization { Slug = "demo-fleet", Name = "Demo Fleet" };
            db.Organizations.Add(organization);
            db.Localizations.Add(new OrganizationLocalization { OrganizationId = organization.Id, TimeZone = "UTC" });
            db.Brandings.Add(new OrganizationBranding { OrganizationId = organization.Id });
            db.SecurityPolicies.Add(new OrganizationSecurityPolicy { OrganizationId = organization.Id });
            await db.SaveChangesAsync();
            db.Provisioning = false;
            await DemoSeed.Run(db);
        });

        var client = app.CreateClient();
        const string phoneNumber = "0733520614";
        const string deviceId = "recurring-crud-test";
        using var signIn = await client.PostAsJsonAsync("/auth/sign-in", new AuthRequest(
            PhoneNumber: phoneNumber,
            Pin: DemoSeed.Logins[0].Pin!,
            DeviceId: deviceId));
        Assert.Equal(HttpStatusCode.Accepted, signIn.StatusCode);

        var email = DemoSeed.Logins[0].Email;
        using var verify = await client.PostAsJsonAsync("/auth/verify-device", new AuthRequest(
            PhoneNumber: phoneNumber,
            DeviceId: deviceId,
            Code: app.Email.Codes[email]));
        Assert.Equal(HttpStatusCode.OK, verify.StatusCode);
        var tokens = await verify.Content.ReadFromJsonAsync<AuthResponse>();
        Assert.False(string.IsNullOrWhiteSpace(tokens?.AccessToken));
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", tokens!.AccessToken);
        return client;
    }

    private sealed record IdResponse(Guid Id);

    public void Dispose() => app.Dispose();
}