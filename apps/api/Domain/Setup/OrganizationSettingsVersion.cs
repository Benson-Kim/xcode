namespace Auth.Domain.Setup;
/// <summary>Append-only settings/setup history. JSON snapshots are audit data, never the live settings store.</summary>

public sealed class OrganizationSettingsVersion : IOrganizationEntity
{
     Guid IOrganizationEntity.OrganizationId
     {
          get => OrganizationId;
          set => throw new InvalidOperationException("Tenant cannot change.");
     }
     private OrganizationSettingsVersion() { }
     public Guid Id { get; private set; } = Guid.NewGuid();
     public Guid OrganizationId { get; private set; }
     public Guid ActorId { get; private set; }
     public long Version { get; private set; }
     public string Section { get; private set; } = "";
     public Guid EntityId { get; private set; }
     public DateTimeOffset OccurredAt { get; private set; }
     public DateTimeOffset? EffectiveFrom { get; private set; }
     public string Before { get; private set; } = "";
     public string After { get; private set; } = "";
     public string Reason { get; private set; } = "";
     public string CorrelationId { get; private set; } = "";
     public OrganizationSettingsVersion(Guid organizationId, Guid actorId, long version, string section, Guid entityId,
    DateTimeOffset occurredAt, string before, string after, string reason, string correlationId, DateTimeOffset? effectiveFrom = null)
     {
          if (organizationId == Guid.Empty || actorId == Guid.Empty || entityId == Guid.Empty || version < 1)
               throw new ArgumentException("Organization, actor, entity and a positive version are required.");
          if (string.IsNullOrWhiteSpace(reason) || reason.Trim().Length > 500)
               throw new ArgumentException("A reason of 1–500 characters is required.");
          if (occurredAt.Offset != TimeSpan.Zero || (effectiveFrom is not null && effectiveFrom.Value.Offset != TimeSpan.Zero))
               throw new ArgumentException("History instants must be UTC.");

          (OrganizationId, ActorId, Version, Section, EntityId) = (organizationId, actorId, version, SetupValue.Name(section), entityId);
          (OccurredAt, EffectiveFrom, Before, After, Reason, CorrelationId) = (occurredAt, effectiveFrom, before, after, reason.Trim(), correlationId);
     }

}
