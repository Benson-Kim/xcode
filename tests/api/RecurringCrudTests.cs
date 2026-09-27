using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
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

        var create = new SaveRecurring(
            "Fuel reserve",
            RecurringKind.Cost,
            CostCategory.RunningCosts,
            1200m,
            RecurrenceFrequency.Weekly,
            6,
            false,
            today.AddDays(1),
            null,
            [new VehicleShare(vehicle.Id, 1200m)],
            "Create recurring CRUD test item");
        using var createItem = await client.PostAsJsonAsync("/setup/recurring", create);
        Assert.Equal(HttpStatusCode.OK, createItem.StatusCode);
        var created = await createItem.Content.ReadFromJsonAsync<IdResponse>();
        Assert.NotNull(created);

        var afterCreate = await client.GetFromJsonAsync<Page<RecurringDto>>("/setup/recurring");
        var createdItem = Assert.Single(afterCreate!.Items);
        Assert.Equal(created.Id, createdItem.Id);
        Assert.Equal("Fuel reserve", createdItem.Name);
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