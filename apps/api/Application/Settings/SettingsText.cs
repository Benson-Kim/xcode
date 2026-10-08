using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Auth.Application.Setup;
using Auth.Domain;

namespace Auth.Application.Settings;

public static class SettingsText
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public static DateOnly CalendarDate(string timeZone, DateTimeOffset utcNow)
    {
        try
        {
            return DateOnly.FromDateTime(TimeZoneInfo.ConvertTime(utcNow, TimeZoneInfo.FindSystemTimeZoneById(timeZone)).DateTime);
        }
        catch (TimeZoneNotFoundException)
        {
            throw new ArgumentException("The organization time zone is not available.");
        }
        catch (InvalidTimeZoneException)
        {
            throw new ArgumentException("The organization time zone is invalid.");
        }
    }

    // What a changed setting is called in an automatic reason; anything else reads as its words ("timeZone" is "the time zone").
    private static readonly Dictionary<string, string> SettingNames = new()
    {
        ["name"] = "the organization name",
        ["hour12"] = "the 12-hour clock",
        ["datePattern"] = "the date format",
        ["firstDayOfWeek"] = "the first day of the week",
        ["weekNumbering"] = "week numbering",
        ["useGrouping"] = "digit grouping",
        ["numberDecimals"] = "the decimal places",
        ["allowLocaleOverride"] = "personal locales",
        ["allowTimeZoneOverride"] = "personal time zones",
        ["allowHour12Override"] = "personal clock formats",
        ["allowThemeOverride"] = "personal themes",
        ["logoAlt"] = "the logo text",
        ["logoLight"] = "the light logo",
        ["logoDark"] = "the dark logo",
        ["primary"] = "the primary colour",
        ["secondary"] = "the secondary colour",
        ["accent"] = "the accent colour",
        ["passwordComplexity"] = "password complexity",
        ["pinLength"] = "the PIN length",
        ["lockoutThreshold"] = "the wrong PIN tries before a pause",
        ["lockoutMinutes"] = "the pause in minutes",
        ["allowPinSignIn"] = "PIN sign-in",
    };

    // The change log says what changed, such as "Changed the time zone to UTC", and a typed reason follows it.
    public static string AutomaticReason(string section, string before, string after)
    {
        var old = JsonNode.Parse(before) as JsonObject;
        var changes = (JsonNode.Parse(after) as JsonObject ?? [])
            .Where(field => field.Key != "organizationId" && !JsonNode.DeepEquals(old?[field.Key], field.Value))
            .Select(field => $"{SettingNames.GetValueOrDefault(field.Key) ?? "the " + Regex.Replace(field.Key, "(?<=[a-z])([A-Z])", " $1").ToLowerInvariant()} to {SettingValue(field.Key, field.Value)}")
            .ToList();
        return changes.Count == 0 ? $"Changed the {section} settings" : "Changed " + SetupPagination.Listed(changes);
    }

    private static string SettingValue(string name, JsonNode? value) => value?.GetValueKind() switch
    {
        null or JsonValueKind.Null => "none",
        JsonValueKind.True => "on",
        JsonValueKind.False => "off",
        JsonValueKind.Number when name == "firstDayOfWeek" => ((DayOfWeek)value.GetValue<int>()).ToString(),
        JsonValueKind.String => value.GetValue<string>(),
        _ => value.ToJsonString()
    };

    // The history keeps the logo's shape, not the image itself.
    public static string DescribeLogo(OrganizationLogo? logo) =>
        logo is null ? "null" : JsonSerializer.Serialize(new { logo.ContentType, bytes = logo.Data.Length, logo.UpdatedAt }, Json);
}
