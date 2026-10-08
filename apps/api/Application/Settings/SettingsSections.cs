using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Application.Settings;

// One organization settings section: how a sent value changes what is saved, and how that change reads in the log.
public interface ISettingsSection
{
    string Key { get; }
    // Applies the value to tracked state and returns the section as it was and as it now is, or a refusal.
    Task<SectionChange> Apply(SettingsScope scope, JsonElement value, CancellationToken ct);
    string Describe(SectionChange change) => SettingsText.AutomaticReason(Key, change.Before, change.After);
}

public sealed record SectionChange(string Before, string After, SectionRefusal? Refusal = null)
{
    public static SectionChange Refused(SectionRefusal refusal) => new("", "", refusal);
}

public sealed record SettingsScope(AuthDb Db, Organization Organization, IClock Clock)
{
    public DateOnly CalendarDate(string timeZone) => SettingsText.CalendarDate(timeZone, Clock.UtcNow);
}

public static class SettingsSections
{
    public static IEnumerable<ISettingsSection> All() =>
    [
        new OrganizationDetailsSection(),
        // A new zone moves the calendar date, which a held business date may not pass.
        new MergedSection<OrganizationLocalization>("localization", db => db.Localizations,
            (scope, localization) => scope.Organization.ChangeTimeZone(localization, new TimeZoneId(localization.TimeZone), scope.CalendarDate(localization.TimeZone)),
            // Apps released before the spelling was fixed still send the old name.
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase) { ["useGroupping"] = "useGrouping" }),
        new MergedSection<OrganizationBranding>("branding", db => db.Brandings),
        new MergedSection<OrganizationSecurityPolicy>("securityPolicy", db => db.SecurityPolicies),
        new BusinessDateSection(),
    ];
}

// The sent fields are merged onto the saved section, so a partial payload changes only what it names and never resets
// the rest to defaults. afterMerge runs only when the merge changed something, before the saved state is described.
// A field sent under a legacy name counts as its current name, unless the current name is sent too.
public sealed class MergedSection<TEntity>(string key, Func<AuthDb, DbSet<TEntity>> set, Action<SettingsScope, TEntity>? afterMerge = null,
    IReadOnlyDictionary<string, string>? legacyNames = null) : ISettingsSection
    where TEntity : class, IOrganizationEntity, IValidatable, new()
{
    public string Key => key;

    public async Task<SectionChange> Apply(SettingsScope scope, JsonElement input, CancellationToken ct)
    {
        if (input.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("Send the section's settings as an object.");
        var entities = set(scope.Db);
        var current = await entities.FindAsync([scope.Organization.Id], ct);
        var merged = JsonObject.Create(JsonSerializer.SerializeToElement(current ?? new TEntity(), SettingsText.Json), new JsonNodeOptions { PropertyNameCaseInsensitive = true })!;
        var sent = JsonObject.Create(input)!;
        foreach (var (name, field) in sent)
        {
            var renamed = legacyNames?.GetValueOrDefault(name);
            if (renamed is not null && sent.Any(x => string.Equals(x.Key, renamed, StringComparison.OrdinalIgnoreCase))) continue;
            merged[renamed ?? name] = field?.DeepClone();
        }
        TEntity value;
        try
        {
            value = merged.Deserialize<TEntity>(SettingsText.Json) ?? throw new ArgumentException("Invalid settings.");
        }
        catch (JsonException)
        {
            throw new ArgumentException("A setting has the wrong type of value.");
        }
        value.OrganizationId = scope.Organization.Id;
        value.Validate();
        var before = JsonSerializer.Serialize(current, SettingsText.Json);
        if (current is null) entities.Add(value);
        else scope.Db.Entry(current).CurrentValues.SetValues(value);
        var saved = current ?? value;
        var after = JsonSerializer.Serialize(saved, SettingsText.Json);
        if (afterMerge is null || before == after)
            return new(before, after);
        afterMerge(scope, saved);
        return new(before, JsonSerializer.Serialize(saved, SettingsText.Json));
    }
}

public sealed class OrganizationDetailsSection : ISettingsSection
{
    public string Key => "organization";

    public async Task<SectionChange> Apply(SettingsScope scope, JsonElement value, CancellationToken ct)
    {
        var organization = scope.Organization;
        var before = JsonSerializer.Serialize(new OrganizationDetails(organization.Name, organization.Slug), SettingsText.Json);
        var details = value.Deserialize<OrganizationDetails>(SettingsText.Json) ?? throw new ArgumentException("Invalid organization details.");
        var name = details.Name?.Trim() ?? "";
        var slug = details.Slug?.Trim().ToLowerInvariant() ?? "";
        if (name.Length is 0 or > 200 || slug.Length is 0 or > 100 || !Regex.IsMatch(slug, "^[a-z0-9]+(?:-[a-z0-9]+)*$"))
            return SectionChange.Refused(new("Enter an organization name and a lowercase slug using letters, numbers, and hyphens."));
        if (await scope.Db.Organizations.IgnoreQueryFilters().AnyAsync(x => x.Id != organization.Id && x.Slug == slug, ct))
            return SectionChange.Refused(new("This organization slug is already in use.", Conflict: true));
        organization.Name = name;
        organization.Slug = slug;
        return new(before, JsonSerializer.Serialize(new OrganizationDetails(name, slug), SettingsText.Json));
    }
}

public sealed class BusinessDateSection : ISettingsSection
{
    public string Key => "businessDate";

    public async Task<SectionChange> Apply(SettingsScope scope, JsonElement value, CancellationToken ct)
    {
        var organization = scope.Organization;
        var before = JsonSerializer.Serialize(organization.BusinessDate, SettingsText.Json);
        var requested = Parse(value);
        // The same zone, and the same fallback, as the calendar date shown in the settings and used for setup.
        var zone = (await scope.Db.Localizations.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationLocalization()).TimeZone;
        return organization.ChangeBusinessDate(requested, scope.CalendarDate(zone))
            ? new(before, JsonSerializer.Serialize(organization.BusinessDate, SettingsText.Json))
            : new(before, before);
    }

    public string Describe(SectionChange change) =>
        change.After == "null" ? "Returned the business date to the calendar" : $"Set the business date to {JsonNode.Parse(change.After)!.GetValue<string>()}";

    private static DateOnly? Parse(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Null) return null;
        if (value.ValueKind != JsonValueKind.String || !DateOnly.TryParse(value.GetString(), out var parsed) || parsed == default)
            throw new ArgumentException("Business date must be a valid calendar date or null.");
        return parsed;
    }
}
