using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Auth.Application;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Api;

public static class OrganizationEndpoints
{
     private static readonly JsonSerializerOptions SettingsJson = new(JsonSerializerDefaults.Web);

     public static void MapOrganization(this WebApplication app)
     {
          var group = app.MapGroup("/setup").RequireAuthorization().WithTags("Organization").WithSetupErrors();
          group.MapGet("/organization/settings", async (IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, IClock clock, CancellationToken ct) =>
          {
               await EnsurePermission(organizations, context.ActorId, "organization.manage", ct);
               var organization = await db.Organizations.AsNoTracking().SingleAsync(ct);
               var localization = await db.Localizations.AsNoTracking().SingleOrDefaultAsync(ct)
                    ?? new OrganizationLocalization { OrganizationId = context.OrganizationId };
               var calendarDate = OrganizationCalendarDate(localization.TimeZone, clock.UtcNow);
               return Results.Ok(new
               {
                    organization,
                    localization,
                    branding = await db.Brandings.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationBranding { OrganizationId = context.OrganizationId },
                    securityPolicy = await db.SecurityPolicies.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationSecurityPolicy { OrganizationId = context.OrganizationId },
                    effectiveBusinessDate = organization.BusinessDate ?? calendarDate,
                    // Today in the organization's time zone, whatever the business date is set to: the latest date it may take.
                    calendarDate,
                    effective = await organizations.Settings(context.ActorId, ct)
               });
          }).WithName("GetOrganizationSettings");

          group.MapPut("/organization/settings/{section}", async (string section, SaveOrganizationSettings input, IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, IClock clock, CancellationToken ct) =>
          {
               await EnsurePermission(organizations, context.ActorId, "organization.manage", ct);
               var reason = SetupPagination.OptionalReason(input.Reason);
               var organization = await db.Organizations.SingleAsync(ct);
               string before, after;
               switch (section)
               {
                    case "organization":
                         before = JsonSerializer.Serialize(new OrganizationDetails(organization.Name, organization.Slug), SettingsJson);
                         var details = input.Value.Deserialize<OrganizationDetails>(SettingsJson) ?? throw new ArgumentException("Invalid organization details.");
                         var name = details.Name?.Trim() ?? "";
                         var slug = details.Slug?.Trim().ToLowerInvariant() ?? "";
                         if (name.Length is 0 or > 200 || slug.Length is 0 or > 100 || !Regex.IsMatch(slug, "^[a-z0-9]+(?:-[a-z0-9]+)*$"))
                              return Results.BadRequest(new { detail = "Enter an organization name and a lowercase slug using letters, numbers, and hyphens." });
                         if (await db.Organizations.IgnoreQueryFilters().AnyAsync(x => x.Id != organization.Id && x.Slug == slug, ct))
                              return Results.Conflict(new { detail = "This organization slug is already in use." });
                         organization.Name = name;
                         organization.Slug = slug;
                         after = JsonSerializer.Serialize(new OrganizationDetails(name, slug), SettingsJson);
                         break;
                    case "localization":
                         (before, after) = await Save(db.Localizations, input.Value, context.OrganizationId, ct);
                         // The zone being saved sets the calendar date, which a held business date may not pass.
                         if (before != after)
                              organization.EnsureBusinessDateWithin(OrganizationCalendarDate(
                                   (await db.Localizations.FindAsync([context.OrganizationId], ct))!.TimeZone, clock.UtcNow));
                         break;
                    case "branding": (before, after) = await Save(db.Brandings, input.Value, context.OrganizationId, ct); break;
                    case "securityPolicy": (before, after) = await Save(db.SecurityPolicies, input.Value, context.OrganizationId, ct); break;
                    case "businessDate":
                         before = JsonSerializer.Serialize(organization.BusinessDate, SettingsJson);
                         var requestedBusinessDate = ParseBusinessDate(input.Value);
                         // The same zone, and the same fallback, as the calendar date shown in the settings and used for setup.
                         organization.ChangeBusinessDate(requestedBusinessDate, OrganizationCalendarDate(
                              (await db.Localizations.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationLocalization()).TimeZone, clock.UtcNow));
                         after = JsonSerializer.Serialize(organization.BusinessDate, SettingsJson);
                         break;
                    default: throw new KeyNotFoundException();
               }
               // Saving what is already stored changes nothing, so it adds no version or change-log entry.
               if (before == after)
                    return Results.Ok(new { section });
               RecordChange(db, context, organization, clock, section, before, after, reason ?? SetupPagination.Automatic(AutomaticReason(section, before, after)));
               await db.SaveChangesAsync(ct);
               return Results.Ok(new { section });
          }).WithName("UpdateOrganizationSettings");

          group.MapPut("/organization/logo", async (SaveLogo input, IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, IClock clock, CancellationToken ct) =>
          {
               await EnsurePermission(organizations, context.ActorId, "organization.manage", ct);
               var reason = SetupPagination.OptionalReason(input.Reason) ?? "Uploaded a new logo";
               var organization = await db.Organizations.SingleAsync(ct);
               var uploaded = OrganizationLogo.FromDataUrl(context.OrganizationId, input.DataUrl, clock.UtcNow);
               var existing = await db.Logos.SingleOrDefaultAsync(ct);
               var before = DescribeLogo(existing);
               if (existing is null)
                    db.Logos.Add(uploaded);
               else
                    (existing.ContentType, existing.Data, existing.UpdatedAt) = (uploaded.ContentType, uploaded.Data, uploaded.UpdatedAt);
               RecordChange(db, context, organization, clock, "logo", before, DescribeLogo(uploaded), reason);
               await db.SaveChangesAsync(ct);
               return Results.Ok(new { logo = uploaded.ToDataUrl() });
          }).WithName("UpdateOrganizationLogo");

          group.MapDelete("/organization/logo", async (string? reason, IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, IClock clock, CancellationToken ct) =>
          {
               await EnsurePermission(organizations, context.ActorId, "organization.manage", ct);
               var changeReason = SetupPagination.OptionalReason(reason) ?? "Removed the logo";
               var existing = await db.Logos.SingleOrDefaultAsync(ct);
               if (existing is null)
                    return Results.Ok(new { logo = (string?)null });
               var organization = await db.Organizations.SingleAsync(ct);
               db.Logos.Remove(existing);
               RecordChange(db, context, organization, clock, "logo", DescribeLogo(existing), "null", changeReason);
               await db.SaveChangesAsync(ct);
               return Results.Ok(new { logo = (string?)null });
          }).WithName("DeleteOrganizationLogo");

          // What every member's screens need to look and format as the organization and the person chose.
          group.MapGet("/appearance", async (IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, IClock clock, CancellationToken ct) =>
          {
               await EnsureMember(organizations, context.ActorId, ct);
               var organization = await db.Organizations.AsNoTracking().SingleAsync(ct);
               var localization = await db.Localizations.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationLocalization();
               var effective = await organizations.Settings(context.ActorId, ct);
               var logo = await db.Logos.AsNoTracking().SingleOrDefaultAsync(ct);
               var branding = effective.Branding;
               return Results.Ok(new
               {
                    organizationName = organization.Name,
                    settingsVersion = organization.SettingsVersion,
                    businessDate = organization.BusinessDate ?? OrganizationCalendarDate(localization.TimeZone, clock.UtcNow),
                    branding = new { branding.DisplayName, branding.LogoAlt, branding.Primary, branding.Secondary, branding.Accent, logo = logo?.ToDataUrl() },
                    formats = effective.Formats,
                    effective.ThemeMode,
                    effective.ReducedMotion,
                    effective.FontScale,
                    // Appended for the phone, which enforces the wrong-PIN policy offline; older clients ignore them.
                    effective.SecurityPolicy.LockoutThreshold,
                    effective.SecurityPolicy.LockoutMinutes,
               });
          }).WithName("GetAppearance");

          group.MapGet("/preferences", async (IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, CancellationToken ct) =>
          {
               await EnsureMember(organizations, context.ActorId, ct);
               var preference = await db.UserPreferences.AsNoTracking().SingleOrDefaultAsync(x => x.UserId == context.ActorId, ct) ?? new UserPreference { OrganizationId = context.OrganizationId, UserId = context.ActorId };
               // Which overrides the organization allows, and its own values, so the form only offers what will take effect.
               var localization = await db.Localizations.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationLocalization();
               // A value kept from before an override was withdrawn is not offered back, so saving the form clears it.
               return Results.Ok(new
               {
                    preference.OrganizationId,
                    preference.UserId,
                    Locale = localization.AllowLocaleOverride ? preference.Locale : null,
                    TimeZone = localization.AllowTimeZoneOverride ? preference.TimeZone : null,
                    Hour12 = localization.AllowHour12Override ? preference.Hour12 : null,
                    ThemeMode = localization.AllowThemeOverride ? preference.ThemeMode : null,
                    preference.ReducedMotion,
                    preference.FontScale,
                    localization.AllowLocaleOverride,
                    localization.AllowTimeZoneOverride,
                    localization.AllowHour12Override,
                    localization.AllowThemeOverride,
                    organization = new { localization.Locale, localization.TimeZone, localization.Hour12 },
               });
          }).WithName("GetUserPreferences");

          group.MapPut("/preferences", async (SaveUserPreferences input, IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, CancellationToken ct) =>
          {
               await EnsureMember(organizations, context.ActorId, ct);
               var preference = await db.UserPreferences.SingleOrDefaultAsync(x => x.UserId == context.ActorId, ct);
               if (preference is null)
               {
                    preference = new UserPreference { OrganizationId = context.OrganizationId, UserId = context.ActorId };
                    db.UserPreferences.Add(preference);
               }
               preference.Locale = input.Locale; preference.TimeZone = input.TimeZone; preference.Hour12 = input.Hour12;
               preference.ThemeMode = input.ThemeMode; preference.ReducedMotion = input.ReducedMotion; preference.FontScale = input.FontScale;
               preference.Validate();
               (await db.Localizations.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationLocalization()).EnsureAllowed(preference);
               await db.SaveChangesAsync(ct);
               return Results.Ok(preference);
          }).WithName("UpdateUserPreferences");
     }

     // Every settings change bumps the version, joins the change log with its reason, and is audited.
     private static void RecordChange(AuthDb db, IOrganizationContext context, Organization organization, IClock clock, string section, string before, string after, string reason)
     {
          organization.SettingsChanged();
          db.Set<OrganizationSettingsVersion>().Add(new(context.OrganizationId, context.ActorId, organization.SettingsVersion, section, organization.Id, clock.UtcNow, before, after, reason, context.CorrelationId));
          db.AuditEvents.Add(new AuditEvent
          {
               OrganizationId = context.OrganizationId,
               ActorId = context.ActorId,
               Action = "organization.settings.updated",
               Entity = section,
               Before = before,
               After = JsonSerializer.Serialize(new { value = JsonDocument.Parse(after).RootElement, reason }, SettingsJson),
               CorrelationId = context.CorrelationId,
               OccuredAt = clock.UtcNow,
          });
     }

     private static DateOnly OrganizationCalendarDate(string timeZone, DateTimeOffset utcNow)
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

     private static DateOnly? ParseBusinessDate(JsonElement value)
     {
          if (value.ValueKind == JsonValueKind.Null) return null;
          if (value.ValueKind != JsonValueKind.String || !DateOnly.TryParse(value.GetString(), out var parsed) || parsed == default)
               throw new ArgumentException("Business date must be a valid calendar date or null.");
          return parsed;
     }

     // What a changed setting is called in an automatic reason; anything else reads as its words ("timeZone" is "the time zone").
     private static readonly Dictionary<string, string> SettingNames = new()
     {
          ["name"] = "the organization name", ["hour12"] = "the 12-hour clock", ["datePattern"] = "the date format",
          ["firstDayOfWeek"] = "the first day of the week",
          ["weekNumbering"] = "week numbering", ["useGroupping"] = "digit grouping", ["numberDecimals"] = "the decimal places",
          ["allowLocaleOverride"] = "personal locales", ["allowTimeZoneOverride"] = "personal time zones",
          ["allowHour12Override"] = "personal clock formats", ["allowThemeOverride"] = "personal themes",
          ["logoAlt"] = "the logo text", ["logoLight"] = "the light logo", ["logoDark"] = "the dark logo",
          ["primary"] = "the primary colour", ["secondary"] = "the secondary colour", ["accent"] = "the accent colour",
          ["passwordComplexity"] = "password complexity", ["pinLength"] = "the PIN length",
          ["lockoutThreshold"] = "the wrong PIN tries before a pause", ["lockoutMinutes"] = "the pause in minutes",
          ["allowPinSignIn"] = "PIN sign-in",
     };

     // Contract C7: without a typed reason, the change log says what changed, such as "Changed the time zone to UTC".
     private static string AutomaticReason(string section, string before, string after)
     {
          if (section == "businessDate")
               return after == "null" ? "Returned the business date to the calendar" : $"Set the business date to {JsonNode.Parse(after)!.GetValue<string>()}";
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
     private static string DescribeLogo(OrganizationLogo? logo) =>
          logo is null ? "null" : JsonSerializer.Serialize(new { logo.ContentType, bytes = logo.Data.Length, logo.UpdatedAt }, SettingsJson);

     private static async Task EnsureMember(IOrganizationRepository organizations, Guid userId, CancellationToken ct)
     {
          if ((await organizations.Membership(userId, ct)) is not { Active: true }) throw new UnauthorizedAccessException();
     }

     private static async Task EnsurePermission(IOrganizationRepository organizations, Guid userId, string permission, CancellationToken ct)
     {
          await EnsureMember(organizations, userId, ct);
          if (!(await organizations.Permissions(userId, ct)).Contains(permission)) throw new UnauthorizedAccessException();
     }

     // The sent fields are merged onto the saved section, so a partial payload changes only what it names and never
     // resets the rest to defaults. Returns the section as it was and as it is now saved, for the settings history.
     private static async Task<(string Before, string After)> Save<TEntity>(DbSet<TEntity> set, JsonElement input, Guid organizationId, CancellationToken ct) where TEntity : class, IOrganizationEntity, new()
     {
          if (input.ValueKind != JsonValueKind.Object)
               throw new ArgumentException("Send the section's settings as an object.");
          var current = await set.FindAsync([organizationId], ct);
          var merged = JsonObject.Create(JsonSerializer.SerializeToElement(current ?? new TEntity(), SettingsJson), new JsonNodeOptions { PropertyNameCaseInsensitive = true })!;
          foreach (var (name, field) in JsonObject.Create(input)!)
               merged[name] = field?.DeepClone();
          TEntity value;
          try
          {
               value = merged.Deserialize<TEntity>(SettingsJson) ?? throw new ArgumentException("Invalid settings.");
          }
          catch (JsonException)
          {
               throw new ArgumentException("A setting has the wrong type of value.");
          }
          value.OrganizationId = organizationId;
          if (value is OrganizationLocalization localization) localization.Validate();
          if (value is OrganizationBranding branding) branding.Validate();
          if (value is OrganizationSecurityPolicy policy) policy.Validate();
          var before = JsonSerializer.Serialize(current, SettingsJson);
          if (current is null) set.Add(value);
          else
          {
               var entry = set.Entry(current);
               entry.CurrentValues.SetValues(value);
          }
          return (before, JsonSerializer.Serialize(current ?? value, SettingsJson));
     }

     public sealed record SaveOrganizationSettings(JsonElement Value, string? Reason = null);
     public sealed record OrganizationDetails(string? Name, string? Slug);
     public sealed record SaveLogo(string? DataUrl, string? Reason);
     public sealed record SaveUserPreferences(string? Locale, string? TimeZone, bool? Hour12, string? ThemeMode, bool ReducedMotion, double FontScale);
}
