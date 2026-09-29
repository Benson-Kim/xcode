using System.Text.Json;
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
               return Results.Ok(new
               {
                    organization,
                    localization,
                    branding = await db.Brandings.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationBranding { OrganizationId = context.OrganizationId },
                    securityPolicy = await db.SecurityPolicies.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationSecurityPolicy { OrganizationId = context.OrganizationId },
                    effectiveBusinessDate = organization.BusinessDate ?? OrganizationCalendarDate(localization.TimeZone, clock.UtcNow),
                    effective = await organizations.Settings(context.ActorId, ct)
               });
          }).WithName("GetOrganizationSettings");

          group.MapPut("/organization/settings/{section}", async (string section, SaveOrganizationSettings input, IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, IClock clock, CancellationToken ct) =>
          {
               await EnsurePermission(organizations, context.ActorId, "organization.manage", ct);
               var reason = SetupPagination.Reason(input.Reason);
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
                    case "localization": (before, after) = await Save(db.Localizations, input.Value.Deserialize<OrganizationLocalization>(SettingsJson) ?? throw new ArgumentException("Invalid localization settings."), context.OrganizationId, ct); break;
                    case "branding": (before, after) = await Save(db.Brandings, input.Value.Deserialize<OrganizationBranding>(SettingsJson) ?? throw new ArgumentException("Invalid branding settings."), context.OrganizationId, ct); break;
                    case "securityPolicy": (before, after) = await Save(db.SecurityPolicies, input.Value.Deserialize<OrganizationSecurityPolicy>(SettingsJson) ?? throw new ArgumentException("Invalid security policy."), context.OrganizationId, ct); break;
                    case "businessDate":
                         before = JsonSerializer.Serialize(organization.BusinessDate, SettingsJson);
                         var requestedBusinessDate = ParseBusinessDate(input.Value);
                         organization.ChangeBusinessDate(requestedBusinessDate, OrganizationCalendarDate(
                              (await db.Localizations.AsNoTracking().SingleOrDefaultAsync(ct))?.TimeZone ?? "UTC", clock.UtcNow));
                         after = JsonSerializer.Serialize(organization.BusinessDate, SettingsJson);
                         break;
                    default: throw new KeyNotFoundException();
               }
               // Saving what is already stored changes nothing, so it adds no version or change-log entry.
               if (before == after)
                    return Results.Ok(new { section });
               RecordChange(db, context, organization, clock, section, before, after, reason);
               await db.SaveChangesAsync(ct);
               return Results.Ok(new { section });
          }).WithName("UpdateOrganizationSettings");

          group.MapPut("/organization/logo", async (SaveLogo input, IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, IClock clock, CancellationToken ct) =>
          {
               await EnsurePermission(organizations, context.ActorId, "organization.manage", ct);
               var organization = await db.Organizations.SingleAsync(ct);
               var uploaded = OrganizationLogo.FromDataUrl(context.OrganizationId, input.DataUrl, clock.UtcNow);
               var existing = await db.Logos.SingleOrDefaultAsync(ct);
               var before = DescribeLogo(existing);
               if (existing is null)
                    db.Logos.Add(uploaded);
               else
                    (existing.ContentType, existing.Data, existing.UpdatedAt) = (uploaded.ContentType, uploaded.Data, uploaded.UpdatedAt);
               RecordChange(db, context, organization, clock, "logo", before, DescribeLogo(uploaded), "Updated logo");
               await db.SaveChangesAsync(ct);
               return Results.Ok(new { logo = uploaded.ToDataUrl() });
          }).WithName("UpdateOrganizationLogo");

          group.MapDelete("/organization/logo", async (IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, IClock clock, CancellationToken ct) =>
          {
               await EnsurePermission(organizations, context.ActorId, "organization.manage", ct);
               var existing = await db.Logos.SingleOrDefaultAsync(ct);
               if (existing is null)
                    return Results.Ok(new { logo = (string?)null });
               var organization = await db.Organizations.SingleAsync(ct);
               db.Logos.Remove(existing);
               RecordChange(db, context, organization, clock, "logo", DescribeLogo(existing), "null", "Removed logo");
               await db.SaveChangesAsync(ct);
               return Results.Ok(new { logo = (string?)null });
          }).WithName("DeleteOrganizationLogo");

          // What every member's screens need to look and format as the organization and the person chose.
          group.MapGet("/appearance", async (IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, IClock clock, CancellationToken ct) =>
          {
               await EnsureMember(organizations, context.ActorId, ct);
               var organization = await db.Organizations.AsNoTracking().SingleAsync(ct);
               var localization = await db.Localizations.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationLocalization { TimeZone = "UTC" };
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
               });
          }).WithName("GetAppearance");

          group.MapGet("/preferences", async (IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, CancellationToken ct) =>
          {
               await EnsureMember(organizations, context.ActorId, ct);
               var preference = await db.UserPreferences.AsNoTracking().SingleOrDefaultAsync(x => x.UserId == context.ActorId, ct) ?? new UserPreference { OrganizationId = context.OrganizationId, UserId = context.ActorId };
               // Which overrides the organization allows, and its own values, so the form only offers what will take effect.
               var localization = await db.Localizations.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationLocalization();
               return Results.Ok(new
               {
                    preference.OrganizationId,
                    preference.UserId,
                    preference.Locale,
                    preference.TimeZone,
                    preference.Hour12,
                    preference.ThemeMode,
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

     // Returns the section as it was and as it is now saved (defaults included for any omitted field), for the settings history.
     private static async Task<(string Before, string After)> Save<TEntity>(DbSet<TEntity> set, TEntity value, Guid organizationId, CancellationToken ct) where TEntity : class, IOrganizationEntity
     {
          value.OrganizationId = organizationId;
          if (value is OrganizationLocalization localization) localization.Validate();
          if (value is OrganizationBranding branding) branding.Validate();
          if (value is OrganizationSecurityPolicy policy) policy.Validate();
          var existing = await set.FindAsync([organizationId], ct);
          var before = JsonSerializer.Serialize(existing, SettingsJson);
          if (existing is null) set.Add(value);
          else
          {
               var entry = set.Entry(existing);
               entry.CurrentValues.SetValues(value);
          }
          return (before, JsonSerializer.Serialize(existing ?? value, SettingsJson));
     }

     public sealed record SaveOrganizationSettings(JsonElement Value, string Reason);
     public sealed record OrganizationDetails(string? Name, string? Slug);
     public sealed record SaveLogo(string? DataUrl);
     public sealed record SaveUserPreferences(string? Locale, string? TimeZone, bool? Hour12, string? ThemeMode, bool ReducedMotion, double FontScale);
}
