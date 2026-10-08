using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Reflection;
using System.Security.Claims;
using System.Text.Json;
using Auth.Application;
using Auth.Application.Settings;
using Auth.Domain;
using Auth.Domain.Setup;
using Auth.Infrastructure;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
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
                useGrouping = false,
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
        Assert.False(root.GetProperty("localization").GetProperty("useGrouping").GetBoolean());
        Assert.False(root.GetProperty("localization").TryGetProperty("useGroupping", out _));
    }

    [Fact]
    public async Task GroupingSentUnderItsOldNameIsSavedAndBothNamesAreServed()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(DemoSeed.Logins[0].Email);
        async Task<JsonElement> Save(object value)
        {
            using var response = await owner.PutAsJsonAsync("/setup/organization/settings/localization", new { value });
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            var settings = await owner.GetFromJsonAsync<JsonElement>("/setup/organization/settings");
            return settings.GetProperty("localization");
        }

        Assert.False((await Save(new { useGroupping = false })).GetProperty("useGrouping").GetBoolean());
        var formats = (await owner.GetFromJsonAsync<JsonElement>("/setup/appearance")).GetProperty("formats");
        Assert.False(formats.GetProperty("useGrouping").GetBoolean());
        Assert.False(formats.GetProperty("useGroupping").GetBoolean());

        // Both names sent: the current one wins.
        Assert.True((await Save(new { useGrouping = true, useGroupping = false })).GetProperty("useGrouping").GetBoolean());

        var history = await owner.GetFromJsonAsync<JsonElement>("/setup/history?pageSize=100");
        var reasons = history.GetProperty("items").EnumerateArray().Reverse().Select(x => x.GetProperty("reason").GetString()).ToList();
        Assert.Equal(["Changed digit grouping to off", "Changed digit grouping to on"], reasons);
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
                    item.GetProperty("reason").GetString() == $"Set the business date to {businessDate:yyyy-MM-dd}. Reason: Reconcile the prior business day.");
    }

    // A frozen business date can move forward up to the organization's own calendar date, so the settings say what it is.
    [Fact]
    public async Task SettingsShowTheCalendarDateAFrozenBusinessDateCanAdvanceTo()
    {
        using var client = await CreateOwnerClient();
        var calendarDate = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);
        (await client.PutAsJsonAsync("/setup/organization/settings/businessDate", new { value = calendarDate.AddDays(-3).ToString("yyyy-MM-dd") })).EnsureSuccessStatusCode();

        var settings = await client.GetFromJsonAsync<JsonElement>("/setup/organization/settings");
        Assert.Equal(calendarDate.AddDays(-3).ToString("yyyy-MM-dd"), settings.GetProperty("effectiveBusinessDate").GetString());
        Assert.Equal(calendarDate.ToString("yyyy-MM-dd"), settings.GetProperty("calendarDate").GetString());

        (await client.PutAsJsonAsync("/setup/organization/settings/businessDate", new { value = settings.GetProperty("calendarDate").GetString() })).EnsureSuccessStatusCode();
        var advanced = await client.GetFromJsonAsync<JsonElement>("/setup/organization/settings");
        Assert.Equal(calendarDate.ToString("yyyy-MM-dd"), advanced.GetProperty("effectiveBusinessDate").GetString());
    }

    // A time zone decides the organization's calendar date, so a held business date must still be on or before it in the
    // zone being saved. Only UTC resolves under the tests' invariant globalization, so the zone "still on the previous
    // date" is simulated by putting the clock back a day: the calendar date in the saved zone is then before the held one.
    [Fact]
    public async Task ALocalizationSaveCannotLeaveAHeldBusinessDateInTheFuture()
    {
        using var client = await CreateOwnerClient();
        var today = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);
        (await client.PutAsJsonAsync("/setup/organization/settings/businessDate", new { value = today.ToString("yyyy-MM-dd") })).EnsureSuccessStatusCode();
        app.Clock.Advance(TimeSpan.FromDays(-1));

        using var refused = await client.PutAsJsonAsync("/setup/organization/settings/localization", new { value = new { timeZone = "UTC", currency = "USD" } });
        Assert.Equal(HttpStatusCode.BadRequest, refused.StatusCode);
        Assert.Equal("The held business date would be in the future in that time zone. Change the business date first.",
            (await refused.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString());
        var unchanged = await client.GetFromJsonAsync<JsonElement>("/setup/organization/settings");
        Assert.Equal("KES", unchanged.GetProperty("localization").GetProperty("currency").GetString());

        (await client.PutAsJsonAsync("/setup/organization/settings/businessDate", new { value = today.AddDays(-1).ToString("yyyy-MM-dd") })).EnsureSuccessStatusCode();
        (await client.PutAsJsonAsync("/setup/organization/settings/localization", new { value = new { timeZone = "UTC", currency = "USD" } })).EnsureSuccessStatusCode();
    }

    [Fact]
    public void ChangingTheTimeZoneChecksTheHeldBusinessDate()
    {
        var organization = new Organization();
        var localization = new OrganizationLocalization
        {
            OrganizationId = organization.Id,
            TimeZone = "UTC"
        };
        var today = new DateOnly(2026, 9, 30);
        var targetZone = new TimeZoneId("UTC");

        organization.ChangeBusinessDate(today, today);

        var pastDateInZone = today.AddDays(-1);
        Assert.Throws<ArgumentException>(() =>
            organization.ChangeTimeZone(localization, targetZone, pastDateInZone)
        );

        organization.ChangeTimeZone(localization, targetZone, today);
        Assert.Equal("UTC", localization.TimeZone);
        // The save's change-log entry moves the version; the time zone change itself does not.
        Assert.Equal(1, organization.SettingsVersion);
        // The held-date check runs only as part of a time zone change.
        Assert.True(typeof(Organization).GetMethod("EnsureBusinessDateWithin", BindingFlags.Instance | BindingFlags.NonPublic)?.IsPrivate);
    }

    [Fact]
    public async Task ALocalizationSaveMovesTheVersionOnce()
    {
        using var client = await CreateOwnerClient();
        async Task<long> Version() => (await client.GetFromJsonAsync<JsonElement>("/setup/appearance")).GetProperty("settingsVersion").GetInt64();
        var before = await Version();

        (await client.PutAsJsonAsync("/setup/organization/settings/localization", new { value = new { timeZone = "UTC", currency = "USD" }, reason = "Report in dollars" }))
            .EnsureSuccessStatusCode();

        Assert.Equal(before + 1, await Version());
        await app.WithDb(async db => Assert.Equal(before + 1,
            (await db.Set<OrganizationSettingsVersion>().IgnoreQueryFilters().SingleAsync(x => x.Section == "localization")).Version));
    }

    // The organization section's own refusals are a plain { detail }, not a problem, and save nothing.
    [Fact]
    public async Task ASlugAnotherOrganizationUsesIsRefused()
    {
        using var client = await CreateOwnerClient();
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            db.Organizations.Add(new Organization { Slug = "taken", Name = "Other Fleet" });
            await db.SaveChangesAsync();
        });

        using var refused = await client.PutAsJsonAsync("/setup/organization/settings/organization",
            new { value = new { name = "Demo Fleet", slug = "Taken" }, reason = "Use the short name" });
        Assert.Equal(HttpStatusCode.Conflict, refused.StatusCode);
        Assert.Equal("application/json", refused.Content.Headers.ContentType?.MediaType);
        var body = await refused.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("This organization slug is already in use.", body.GetProperty("detail").GetString());
        Assert.False(body.TryGetProperty("title", out _));

        var settings = await client.GetFromJsonAsync<JsonElement>("/setup/organization/settings");
        Assert.Equal("demo-fleet", settings.GetProperty("organization").GetProperty("slug").GetString());
        var history = await client.GetFromJsonAsync<JsonElement>("/setup/history?pageSize=100");
        Assert.DoesNotContain(history.GetProperty("items").EnumerateArray(), item => item.GetProperty("section").GetString() == "organization");
    }

    // The use cases are the application layer: they run, authorize and log a save with no HTTP request at all.
    [Fact]
    public async Task SettingsUseCasesSaveASectionWithoutHttp()
    {
        await app.SeedDemo();
        Guid organizationId = default, ownerId = default;
        long version = 0;
        await app.WithDb(async db =>
        {
            var organization = await db.Organizations.IgnoreQueryFilters().SingleAsync();
            (organizationId, version) = (organization.Id, organization.SettingsVersion);
            ownerId = (await db.Users.SingleAsync(x => x.Email == DemoSeed.Logins[0].Email)).Id;
        });
        var accessor = app.Services.GetRequiredService<IHttpContextAccessor>();
        accessor.HttpContext = new DefaultHttpContext
        {
            User = new ClaimsPrincipal(new ClaimsIdentity([new Claim("org", organizationId.ToString()), new Claim("sub", ownerId.ToString())], "test"))
        };
        try
        {
            using var scope = app.Services.CreateScope();
            var settings = scope.ServiceProvider.GetRequiredService<OrganizationSettingsUseCases>();
            app.Database.Reset();
            var saved = await settings.Save("branding", new SaveOrganizationSettings(JsonSerializer.SerializeToElement(new { displayName = "North Star" }), "Rebrand"),
                CancellationToken.None);

            Assert.Equal(new SettingsSaveResult("branding"), saved);
            Assert.Equal(1, app.Database.Transactions);
        }
        finally
        {
            accessor.HttpContext = null;
        }

        await app.WithDb(async db =>
        {
            Assert.Equal("North Star", (await db.Brandings.IgnoreQueryFilters().SingleAsync()).DisplayName);
            Assert.Equal(version + 1, (await db.Organizations.IgnoreQueryFilters().SingleAsync()).SettingsVersion);
            var entry = await db.Set<OrganizationSettingsVersion>().IgnoreQueryFilters().SingleAsync(x => x.Section == "branding");
            Assert.Equal((version + 1, ownerId, "Changed the display name to North Star. Reason: Rebrand."), (entry.Version, entry.ActorId, entry.Reason));
        });
    }

    // Organization settings keep the automatic reason; a typed one is optional but still checked.
    [Fact]
    public async Task SettingsSavedWithoutAReasonGetAnAutomaticOne()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(DemoSeed.Logins[0].Email);
        var yesterday = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime).AddDays(-1).ToString("yyyy-MM-dd");
        async Task Save(string section, object value) =>
            Assert.Equal(HttpStatusCode.OK, (await owner.PutAsJsonAsync($"/setup/organization/settings/{section}", new { value })).StatusCode);

        await Save("organization", new { name = "North Star Fleet", slug = "demo-fleet" });
        await Save("localization", new { currency = "USD", firstDayOfWeek = 0 });
        await Save("securityPolicy", new { lockoutThreshold = 3, allowPinSignIn = true });
        await Save("branding", new { displayName = "North Star" });
        await Save("businessDate", yesterday);
        await Save("businessDate", null!);
        (await owner.PutAsJsonAsync("/setup/organization/logo", new { dataUrl = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=" })).EnsureSuccessStatusCode();
        (await owner.DeleteAsync("/setup/organization/logo")).EnsureSuccessStatusCode();
        using var tooLong = await owner.PutAsJsonAsync("/setup/organization/settings/localization", new { value = new { currency = "EUR" }, reason = new string('r', 501) });
        Assert.Equal(HttpStatusCode.BadRequest, tooLong.StatusCode);

        var history = await owner.GetFromJsonAsync<JsonElement>("/setup/history?pageSize=100");
        var reasons = history.GetProperty("items").EnumerateArray().Reverse().Select(x => x.GetProperty("reason").GetString()).ToList();
        Assert.Equal([
            "Changed the organization name to North Star Fleet",
            "Changed the first day of the week to Sunday and the currency to USD",
            "Changed the wrong PIN tries before a pause to 3",
            "Changed the display name to North Star",
            $"Set the business date to {yesterday}",
            "Returned the business date to the calendar",
            "Uploaded a new logo",
            "Removed the logo"], reasons);
    }

    [Fact]
    public async Task APartialSectionKeepsTheFieldsItOmits()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(DemoSeed.Logins[0].Email);
        (await owner.PutAsJsonAsync("/setup/organization/settings/securityPolicy",
            new { value = new { lockoutMinutes = 30 }, reason = "Longer pause" })).EnsureSuccessStatusCode();
        (await owner.PutAsJsonAsync("/setup/organization/settings/securityPolicy",
            new { value = new { lockoutThreshold = 3 }, reason = "Fewer tries" })).EnsureSuccessStatusCode();
        // Localization omitted from this payload includes the organization's UTC time zone.
        using var localization = await owner.PutAsJsonAsync("/setup/organization/settings/localization",
            new { value = new { currency = "USD" }, reason = "Report in dollars" });
        Assert.Equal(HttpStatusCode.OK, localization.StatusCode);

        var settings = await owner.GetFromJsonAsync<JsonElement>("/setup/organization/settings");
        var policy = settings.GetProperty("securityPolicy");
        Assert.Equal(3, policy.GetProperty("lockoutThreshold").GetInt32());
        Assert.Equal(30, policy.GetProperty("lockoutMinutes").GetInt32());
        Assert.Equal("USD", settings.GetProperty("localization").GetProperty("currency").GetString());
        Assert.Equal("UTC", settings.GetProperty("localization").GetProperty("timeZone").GetString());

        using var notAnObject = await owner.PutAsJsonAsync("/setup/organization/settings/securityPolicy",
            new { value = 3, reason = "Wrong shape" });
        Assert.Equal(HttpStatusCode.BadRequest, notAnObject.StatusCode);
        using var wrongType = await owner.PutAsJsonAsync("/setup/organization/settings/securityPolicy",
            new { value = new { lockoutThreshold = "three" }, reason = "Wrong type" });
        Assert.Equal(HttpStatusCode.BadRequest, wrongType.StatusCode);
    }

    [Fact]
    public async Task SecurityPolicyCannotDisablePinSignIn()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(DemoSeed.Logins[0].Email);

        using var refused = await owner.PutAsJsonAsync("/setup/organization/settings/securityPolicy",
            new { value = new { allowPinSignIn = false }, reason = "Disable PIN sign-in" });
        Assert.Equal(HttpStatusCode.BadRequest, refused.StatusCode);
        Assert.Equal("PIN sign-in cannot be disabled.",
            (await refused.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString());

        var settings = await owner.GetFromJsonAsync<JsonElement>("/setup/organization/settings");
        Assert.True(settings.GetProperty("securityPolicy").GetProperty("allowPinSignIn").GetBoolean());
        var history = await owner.GetFromJsonAsync<JsonElement>("/setup/history?pageSize=100");
        Assert.DoesNotContain(history.GetProperty("items").EnumerateArray(),
            item => item.GetProperty("reason").GetString() == "Disable PIN sign-in");
    }

    [Fact]
    public async Task PreferenceWritesRefuseOverridesTheOrganizationDoesNotAllow()
    {
        await app.SeedDemo();
        using var clerk = await app.SignIn("wanjiru.kamau@zurigenesis.co.ke");
        object Preferences(string? locale = null, string? timeZone = null, bool? hour12 = null, string? themeMode = null) =>
            new { locale, timeZone, hour12, themeMode, reducedMotion = true, fontScale = 1.25 };

        // The organization allows no personal time zone by default.
        using var zone = await clerk.PutAsJsonAsync("/setup/preferences", Preferences(timeZone: "UTC"));
        Assert.Equal(HttpStatusCode.BadRequest, zone.StatusCode);
        Assert.Contains("time zone", (await zone.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString());
        (await clerk.PutAsJsonAsync("/setup/preferences", Preferences(locale: "fr-FR", hour12: true, themeMode: "dark"))).EnsureSuccessStatusCode();

        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var localization = await db.Localizations.IgnoreQueryFilters().SingleAsync();
            (localization.AllowLocaleOverride, localization.AllowHour12Override, localization.AllowThemeOverride) = (false, false, false);
            await db.SaveChangesAsync();
        });
        foreach (var forbidden in new[] { Preferences(locale: "fr-FR"), Preferences(hour12: true), Preferences(themeMode: "dark") })
            Assert.Equal(HttpStatusCode.BadRequest, (await clerk.PutAsJsonAsync("/setup/preferences", forbidden)).StatusCode);

        // Values saved while allowed are not offered back, so resaving the form clears them instead of failing.
        var loaded = await clerk.GetFromJsonAsync<JsonElement>("/setup/preferences");
        Assert.Equal(JsonValueKind.Null, loaded.GetProperty("locale").ValueKind);
        Assert.Equal(JsonValueKind.Null, loaded.GetProperty("themeMode").ValueKind);
        (await clerk.PutAsJsonAsync("/setup/preferences", Preferences())).EnsureSuccessStatusCode();
        await app.WithDb(async db =>
        {
            var stored = await db.UserPreferences.IgnoreQueryFilters().SingleAsync();
            Assert.Null(stored.Locale);
            Assert.Null(stored.ThemeMode);
            Assert.Equal(1.25, stored.FontScale);
        });
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