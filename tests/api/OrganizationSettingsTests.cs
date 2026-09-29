using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace Auth.Tests;

public sealed class OrganizationSettingsTests : IDisposable
{
    private readonly AuthFactory app = new();

    [Fact]
    public async Task OrganizationAndLocalizationSettingsPersistCamelCaseValues()
    {
        using var client = await CreateOwnerClient();

        using var invalid = await client.PutAsJsonAsync("/setup/organization/settings/organization", new
        {
            value = new { name = "North Star Fleet", slug = "../invalid" },
            reason = "Update organization details"
        });
        Assert.Equal(HttpStatusCode.BadRequest, invalid.StatusCode);

        using var updateOrganization = await client.PutAsJsonAsync("/setup/organization/settings/organization", new
        {
            value = new { name = "North Star Fleet", slug = "north-star-fleet" },
            reason = "Update organization details"
        });
        Assert.Equal(HttpStatusCode.OK, updateOrganization.StatusCode);

        using var updateLocalization = await client.PutAsJsonAsync("/setup/organization/settings/localization", new
        {
            value = new
            {
                locale = "fr-FR",
                timeZone = "UTC",
                currency = "USD",
                datePattern = "long",
                hour12 = true,
                firstDayOfWeek = 0,
                weekNumbering = "local",
                useGroupping = false,
                numberDecimals = 0,
                allowLocaleOverride = false,
                allowTimeZoneOverride = true,
                allowHour12Override = false,
                allowThemeOverride = false
            },
            reason = "Update organization localization"
        });
        Assert.Equal(HttpStatusCode.OK, updateLocalization.StatusCode);

        using var response = await client.GetAsync("/setup/organization/settings");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        var root = document.RootElement;
        Assert.Equal("North Star Fleet", root.GetProperty("organization").GetProperty("name").GetString());
        Assert.Equal("north-star-fleet", root.GetProperty("organization").GetProperty("slug").GetString());
        Assert.Equal("fr-FR", root.GetProperty("localization").GetProperty("locale").GetString());
        Assert.Equal("USD", root.GetProperty("localization").GetProperty("currency").GetString());
        Assert.Equal("long", root.GetProperty("localization").GetProperty("datePattern").GetString());
    }

    [Fact]
    public async Task BusinessDateUsesTheServerDateForSetupAndIsAudited()
    {
        using var client = await CreateOwnerClient();
        var calendarDate = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);
        var businessDate = calendarDate.AddDays(-1);

        using var update = await client.PutAsJsonAsync("/setup/organization/settings/businessDate", new
        {
            value = businessDate.ToString("yyyy-MM-dd"),
            reason = "Reconcile the prior business day"
        });
        Assert.Equal(HttpStatusCode.OK, update.StatusCode);

        using var settings = JsonDocument.Parse(await (await client.GetAsync("/setup/organization/settings")).Content.ReadAsStringAsync());
        Assert.Equal(businessDate.ToString("yyyy-MM-dd"), settings.RootElement.GetProperty("organization").GetProperty("businessDate").GetString());
        Assert.Equal(businessDate.ToString("yyyy-MM-dd"), settings.RootElement.GetProperty("effectiveBusinessDate").GetString());

        using var appearance = JsonDocument.Parse(await (await client.GetAsync("/setup/appearance")).Content.ReadAsStringAsync());
        Assert.Equal(businessDate.ToString("yyyy-MM-dd"), appearance.RootElement.GetProperty("businessDate").GetString());

        using var future = await client.PutAsJsonAsync("/setup/organization/settings/businessDate", new
        {
            value = calendarDate.AddDays(1).ToString("yyyy-MM-dd"),
            reason = "Invalid future date"
        });
        Assert.Equal(HttpStatusCode.BadRequest, future.StatusCode);

        using var history = JsonDocument.Parse(await (await client.GetAsync("/setup/history")).Content.ReadAsStringAsync());
        Assert.Contains(history.RootElement.GetProperty("items").EnumerateArray(),
            item => item.GetProperty("section").GetString() == "businessDate" &&
                    item.GetProperty("reason").GetString() == "Reconcile the prior business day");
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
        await app.WithDb(async db =>
        {
            var owner = await db.Users.SingleAsync(x => x.Email == DemoSeed.Logins[0].Email);
            Assert.Equal(UserStatus.Active, owner.Status);
            Assert.True(owner.PinHash is not null && PinHasher.Verify(DemoSeed.Logins[0].Pin!, owner.PinHash));
        });

        var client = app.CreateClient();
        using var signIn = await client.PostAsJsonAsync("/auth/sign-in", new AuthRequest(
            PhoneNumber: "0733520614",
            Pin: DemoSeed.Logins[0].Pin!,
            DeviceId: "organization-settings-test"));
        Assert.True(signIn.StatusCode == HttpStatusCode.Accepted, await signIn.Content.ReadAsStringAsync());

        var email = DemoSeed.Logins[0].Email;
        using var verify = await client.PostAsJsonAsync("/auth/verify-device", new AuthRequest(
            PhoneNumber: "0733520614",
            DeviceId: "organization-settings-test",
            Code: app.Email.Codes[email]));
        Assert.Equal(HttpStatusCode.OK, verify.StatusCode);
        var tokens = await verify.Content.ReadFromJsonAsync<AuthResponse>();
        Assert.False(string.IsNullOrWhiteSpace(tokens?.AccessToken));
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", tokens!.AccessToken);
        return client;
    }

    public void Dispose() => app.Dispose();
}