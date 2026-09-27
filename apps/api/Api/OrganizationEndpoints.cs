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
          group.MapGet("/organization/settings", async (IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, CancellationToken ct) =>
          {
               await EnsurePermission(organizations, context.ActorId, "organization.manage", ct);
               var organization = await db.Organizations.AsNoTracking().SingleAsync(ct);
               return Results.Ok(new
               {
                    organization,
                    localization = await db.Localizations.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationLocalization { OrganizationId = context.OrganizationId },
                    branding = await db.Brandings.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationBranding { OrganizationId = context.OrganizationId },
                    securityPolicy = await db.SecurityPolicies.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationSecurityPolicy { OrganizationId = context.OrganizationId },
                    effective = await organizations.Settings(context.ActorId, ct)
               });
          }).WithName("GetOrganizationSettings");

          group.MapPut("/organization/settings/{section}", async (string section, SaveOrganizationSettings input, IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, IClock clock, CancellationToken ct) =>
          {
               await EnsurePermission(organizations, context.ActorId, "organization.manage", ct);
               var reason = SetupPagination.Reason(input.Reason);
               var organization = await db.Organizations.SingleAsync(ct);
               string before;
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
                         break;
                    case "localization": before = await Save(db.Localizations, input.Value.Deserialize<OrganizationLocalization>(SettingsJson) ?? throw new ArgumentException("Invalid localization settings."), context.OrganizationId, ct); break;
                    case "branding": before = await Save(db.Brandings, input.Value.Deserialize<OrganizationBranding>(SettingsJson) ?? throw new ArgumentException("Invalid branding settings."), context.OrganizationId, ct); break;
                    case "securityPolicy": before = await Save(db.SecurityPolicies, input.Value.Deserialize<OrganizationSecurityPolicy>(SettingsJson) ?? throw new ArgumentException("Invalid security policy."), context.OrganizationId, ct); break;
                    default: throw new KeyNotFoundException();
               }
               organization.SettingsChanged();
               // The versioned history keeps the stated reason and appears in the change log; the audit row carries it too.
               var after = input.Value.GetRawText();
               db.Set<OrganizationSettingsVersion>().Add(new(context.OrganizationId, context.ActorId, organization.SettingsVersion, section, organization.Id, clock.UtcNow, before, after, reason, context.CorrelationId));
               db.AuditEvents.Add(new AuditEvent { OrganizationId = context.OrganizationId, ActorId = context.ActorId, Action = "organization.settings.updated", Entity = section, Before = before, After = JsonSerializer.Serialize(new { value = input.Value, reason }, SettingsJson), CorrelationId = context.CorrelationId, OccuredAt = clock.UtcNow });
               await db.SaveChangesAsync(ct);
               return Results.Ok(new { section });
          }).WithName("UpdateOrganizationSettings");

          group.MapGet("/preferences", async (IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, CancellationToken ct) =>
          {
               await EnsureMember(organizations, context.ActorId, ct);
               return Results.Ok(await db.UserPreferences.AsNoTracking().SingleOrDefaultAsync(x => x.UserId == context.ActorId, ct) ?? new UserPreference { OrganizationId = context.OrganizationId, UserId = context.ActorId });
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

     private static async Task EnsureMember(IOrganizationRepository organizations, Guid userId, CancellationToken ct)
     {
          if ((await organizations.Membership(userId, ct)) is not { Active: true }) throw new UnauthorizedAccessException();
     }

     private static async Task EnsurePermission(IOrganizationRepository organizations, Guid userId, string permission, CancellationToken ct)
     {
          await EnsureMember(organizations, userId, ct);
          if (!(await organizations.Permissions(userId, ct)).Contains(permission)) throw new UnauthorizedAccessException();
     }

     // Returns the section as it was before the change, for the settings history.
     private static async Task<string> Save<TEntity>(DbSet<TEntity> set, TEntity value, Guid organizationId, CancellationToken ct) where TEntity : class, IOrganizationEntity
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
          return before;
     }

     public sealed record SaveOrganizationSettings(JsonElement Value, string Reason);
     public sealed record OrganizationDetails(string? Name, string? Slug);
     public sealed record SaveUserPreferences(string? Locale, string? TimeZone, bool? Hour12, string? ThemeMode, bool ReducedMotion, double FontScale);
}
