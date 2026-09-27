
using System.Data;
using System.Text.Json;
using Auth.Application;
using Auth.Domain;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

public sealed class OrganizationRepository(AuthDb db, EffectiveSettingsResolver settings, EffectivePermissionResolver permissions) : IOrganizationRepository
{
     public Task<Organization?> Get(CancellationToken ct)
          => db.Organizations.SingleOrDefaultAsync(ct);
     public Task<OrganizationMembership?> Membership(Guid userId, CancellationToken ct)
          => db.Memberships.SingleOrDefaultAsync(x => x.UserId == userId, ct);
     public async Task<IReadOnlySet<string>> Permissions(Guid userId, CancellationToken ct)
     {
          var member = await Membership(userId, ct);
          var roleIds = db.PersonRoles.Where(x => x.UserId == userId).Select(x => x.RoleId);
          return permissions.Resolve(await db.RolePermissions.Where(x
               => roleIds.Contains(x.RoleId)).Select(x => x.Permission).ToListAsync(ct),
               await db.PermissionOverrides.Where(x => x.UserId == userId).ToListAsync(ct), member is { Active: true });
     }

     public async Task<EffectiveSettings> Settings(Guid userId, CancellationToken ct) =>
          settings.Resolve(
               await db.Localizations.SingleOrDefaultAsync(ct),
               await db.Brandings.SingleOrDefaultAsync(ct),
               await db.SecurityPolicies.SingleOrDefaultAsync(ct),
               await db.UserPreferences.SingleOrDefaultAsync(x => x.UserId == userId, ct)
          );
}

public sealed class UnitOfWork(AuthDb db, IOrganizationContext context, IClock clock) : IUnitOfWork
{
     public async Task<T> Execute<T>(Func<Task<T>> action, CancellationToken ct)
     {
          await using var transaction = await db.Database.BeginTransactionAsync(IsolationLevel.Serializable, ct);
          var result = await action();
          await db.SaveChangesAsync(ct);
          await transaction.CommitAsync(ct);
          return result;
     }

     public void Audit(string action, string entity, object? before, object? after) => db.AuditEvents.Add(new()
     {
          OrganizationId = context.OrganizationId,
          ActorId = context.ActorId,
          Action = action,
          Entity = entity,
          Before = before is null ? null : JsonSerializer.Serialize(before),
          After = after is null ? null : JsonSerializer.Serialize(after),
          CorrelationId = context.CorrelationId,
          OccuredAt = clock.UtcNow
     });
}