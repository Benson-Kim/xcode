using System.Text.Json;
using Auth.Application;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Api;

public static class OrganizationEndpoints
{
     public static void MapOrganization(this WebApplication app)
     {
          var group = app.MapGroup("/setup").RequireAuthorization().WithTags("Organization");
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

          group.MapPut("/organization/settings/{section}", async (string section, SaveOrganizationSettings input, IOrganizationContext context, IOrganizationRepository organizations, AuthDb db, CancellationToken ct) =>
          {
               await EnsurePermission(organizations, context.ActorId, "organization.manage", ct);
               if (string.IsNullOrWhiteSpace(input.Reason) || input.Reason.Trim().Length > 500) throw new ArgumentException("A reason of 1-500 characters is required.");
               switch (section)
               {
                    case "localization": await Save(db.Localizations, input.Value.Deserialize<OrganizationLocalization>() ?? throw new ArgumentException("Invalid localization settings."), context.OrganizationId, ct); break;
                    case "branding": await Save(db.Brandings, input.Value.Deserialize<OrganizationBranding>() ?? throw new ArgumentException("Invalid branding settings."), context.OrganizationId, ct); break;
                    case "securityPolicy": await Save(db.SecurityPolicies, input.Value.Deserialize<OrganizationSecurityPolicy>() ?? throw new ArgumentException("Invalid security policy."), context.OrganizationId, ct); break;
                    default: throw new KeyNotFoundException();
               }
               db.AuditEvents.Add(new AuditEvent { OrganizationId = context.OrganizationId, ActorId = context.ActorId, Action = "organization.settings.updated", Entity = section, After = input.Value.GetRawText(), CorrelationId = context.CorrelationId, OccuredAt = DateTimeOffset.UtcNow });
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

     private static async Task Save<TEntity>(DbSet<TEntity> set, TEntity value, Guid organizationId, CancellationToken ct) where TEntity : class, IOrganizationEntity
     {
          value.OrganizationId = organizationId;
          if (value is OrganizationLocalization localization) localization.Validate();
          if (value is OrganizationBranding branding) branding.Validate();
          if (value is OrganizationSecurityPolicy policy) policy.Validate();
          var existing = await set.FindAsync([organizationId], ct);
          if (existing is null) set.Add(value);
          else
          {
               var entry = set.Entry(existing);
               entry.CurrentValues.SetValues(value);
          }
     }

     public sealed record SaveOrganizationSettings(JsonElement Value, string Reason);
     public sealed record SaveUserPreferences(string? Locale, string? TimeZone, bool? Hour12, string? ThemeMode, bool ReducedMotion, double FontScale);
}
