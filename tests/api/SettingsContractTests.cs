using System.Net.Http.Json;
using System.Reflection;
using System.Text.Json;
using Auth.Application.Settings;
using Auth.Domain;
using Microsoft.AspNetCore.Http.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Xunit;

namespace Auth.Tests;

// The settings responses carry DTOs instead of the entities they used to. Each one writes exactly the JSON its entity
// wrote: the same fields, in the same order, with the same values.
public sealed class SettingsContractTests : IDisposable
{
    private readonly AuthFactory app = new();
    private const string Owner = "antony.maina@shamayah.co.ke";

    private JsonSerializerOptions Http => app.Services.GetRequiredService<IOptions<JsonOptions>>().Value.SerializerOptions;

    // Every field is changed on its own as well, so a field the DTO drops, misplaces or fills from another field fails.
    [Fact]
    public void EachSettingsDtoWritesWhatItsEntityWrote()
    {
        Maps<Organization, OrganizationDto>(OrganizationDto.From);
        Maps<OrganizationLocalization, LocalizationDto>(LocalizationDto.From);
        Maps<OrganizationBranding, BrandingDto>(BrandingDto.From);
        Maps<OrganizationSecurityPolicy, SecurityPolicyDto>(SecurityPolicyDto.From);
        Maps<UserPreference, UserPreferenceDto>(UserPreferenceDto.From);
    }

    [Fact]
    public async Task TheSettingsAndPreferenceResponsesAreTheEntitiesJson()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var yesterday = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime).AddDays(-1).ToString("yyyy-MM-dd");
        (await owner.PutAsJsonAsync("/setup/organization/settings/businessDate", new { value = yesterday })).EnsureSuccessStatusCode();
        (await owner.PutAsJsonAsync("/setup/organization/settings/branding", new { value = new { supportEmail = "help@example.com" } })).EnsureSuccessStatusCode();

        using var settings = JsonDocument.Parse(await owner.GetStringAsync("/setup/organization/settings"));
        using var saved = await owner.PutAsJsonAsync("/setup/preferences",
            new { locale = "fr-FR", timeZone = (string?)null, hour12 = true, themeMode = "dark", reducedMotion = true, fontScale = 1.25 });
        saved.EnsureSuccessStatusCode();
        using var preference = JsonDocument.Parse(await saved.Content.ReadAsStringAsync());

        await app.WithDb(async db =>
        {
            var section = settings.RootElement;
            Assert.Equal(Json(await db.Organizations.IgnoreQueryFilters().SingleAsync()), section.GetProperty("organization").GetRawText());
            Assert.Equal(Json(await db.Localizations.IgnoreQueryFilters().SingleAsync()), section.GetProperty("localization").GetRawText());
            Assert.Equal(Json(await db.Brandings.IgnoreQueryFilters().SingleAsync()), section.GetProperty("branding").GetRawText());
            Assert.Equal(Json(await db.SecurityPolicies.IgnoreQueryFilters().SingleAsync()), section.GetProperty("securityPolicy").GetRawText());
            Assert.Equal(Json(await db.UserPreferences.IgnoreQueryFilters().SingleAsync()), preference.RootElement.GetRawText());
        });
    }

    private string Json<T>(T value) => JsonSerializer.Serialize(value, Http);

    private void Maps<TEntity, TDto>(Func<TEntity, TDto> map) where TEntity : new()
    {
        var defaults = new TEntity();
        Assert.Equal(Json(defaults), Json(map(defaults)));
        var properties = typeof(TEntity).GetProperties(BindingFlags.Instance | BindingFlags.Public);
        Assert.NotEmpty(properties);
        foreach (var property in properties)
        {
            var entity = new TEntity();
            property.SetValue(entity, Changed(property.PropertyType, property.GetValue(entity)));
            Assert.Equal(Json(entity), Json(map(entity)));
        }
    }

    private static object? Changed(Type type, object? value) => (Nullable.GetUnderlyingType(type) ?? type) switch
    {
        var t when t == typeof(Guid) => Guid.NewGuid(),
        var t when t == typeof(string) => value + "changed",
        var t when t == typeof(bool) => value is not true,
        var t when t == typeof(int) => (int)(value ?? 0) + 7,
        var t when t == typeof(long) => (long)(value ?? 0L) + 7,
        var t when t == typeof(double) => (double)(value ?? 0d) + 0.5,
        var t when t == typeof(DateOnly) => ((DateOnly?)value ?? new DateOnly(2026, 9, 30)).AddDays(1),
        var t => throw new InvalidOperationException($"No changed value for {t.Name}."),
    };

    public void Dispose() => app.Dispose();
}
