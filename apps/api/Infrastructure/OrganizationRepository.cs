
using System.Data;
using System.Text.Json;
using Auth.Application;
using Auth.Domain;
using Microsoft.Data.SqlClient;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

public sealed class OrganizationRepository(AuthDb db, EffectiveSettingsResolver settings, EffectivePermissionResolver permissions) : IOrganizationRepository
{
     public Task<Organization?> Get(CancellationToken ct)
          => db.Organizations.SingleOrDefaultAsync(ct);
     public Task<OrganizationMembership?> Membership(Guid userId, CancellationToken ct)
          => db.Memberships.SingleOrDefaultAsync(x => x.UserId == userId, ct);
     // This repository is scoped to one request, so each person's permissions are resolved once per request however
     // many checks ask (the use-case pipeline, then access rules such as role granting).
     private readonly Dictionary<Guid, IReadOnlySet<string>> resolvedPermissions = [];

     // A role's standard permissions come only from PermissionCatalog; the RolePermissions table is no longer read.
     public async Task<IReadOnlySet<string>> Permissions(Guid userId, CancellationToken ct)
     {
          if (resolvedPermissions.TryGetValue(userId, out var resolved))
               return resolved;
          var member = await Membership(userId, ct);
          var roleNames = await db.PersonRoles.Where(x => x.UserId == userId)
               .Join(db.Roles, link => link.RoleId, role => role.Id, (_, role) => role.Name)
               .ToListAsync(ct);
          return resolvedPermissions[userId] = permissions.Resolve(roleNames.SelectMany(PermissionCatalog.DefaultsFor),
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
     private const int ChangeLogRetries = 3;

     // Every write that adds a change-log entry bumps Organization.SettingsVersion, so two writes to different records
     // at the same moment collide on that one row: a concurrency conflict on it alone, or on SQL Server a deadlock
     // (1205) while both hold shared locks on it. Neither means the caller's data was stale, so the whole unit of work
     // runs again from scratch (fresh reads, authorization and validation, in a new transaction), up to three times.
     // Any other conflict, such as a stale person record, still surfaces on the first attempt.
     public async Task<T> Execute<T>(Func<Task<T>> action, CancellationToken ct)
     {
          for (var attempt = 0; ; attempt++)
          {
               try
               {
                    await using var transaction = await db.Database.BeginTransactionAsync(IsolationLevel.Serializable, ct);
                    var result = await action();
                    await db.SaveChangesAsync(ct);
                    await transaction.CommitAsync(ct);
                    return result;
               }
               catch (Exception error) when (attempt < ChangeLogRetries && OnlyTheChangeLogCollided(error))
               {
                    db.ChangeTracker.Clear();
                    // A little jitter, so writers that collided do not simply collide again.
                    await Task.Delay(Random.Shared.Next(5, 25) * (attempt + 1), ct);
               }
          }
     }

     private static bool OnlyTheChangeLogCollided(Exception error)
     {
          if (error is DbUpdateConcurrencyException { Entries.Count: > 0 } conflict)
               return conflict.Entries.All(x => x.Entity is Organization);
          for (var inner = error; inner is not null; inner = inner.InnerException)
               if (inner is SqlException { Number: 1205 })
                    return true;
          return false;
     }

     // Reads run without an explicit transaction and save nothing. A read that changed tracked state would silently
     // lose that change, so it fails instead: such work belongs on the write path.
     public async Task<T> Read<T>(Func<Task<T>> action, CancellationToken ct)
     {
          var result = await action();
          if (db.ChangeTracker.HasChanges())
               throw new InvalidOperationException("A read changed state. Run it as a write.");
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