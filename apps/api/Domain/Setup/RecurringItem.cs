

namespace Auth.Domain.Setup;

public sealed class RecurringItem : IOrganizationEntity
{
     Guid IOrganizationEntity.OrganizationId
     {
          get => OrganizationId;
          set => throw new InvalidOperationException("Tenant cannot change.");
     }
     private RecurringItem() { }
     public Guid Id { get; private set; } = Guid.NewGuid();
     public Guid OrganizationId { get; private set; }
     public DateOnly? StoppedFrom { get; private set; }
     public List<RecurringVersion> Versions { get; private set; } = [];
     public RecurringItem(Guid organizationId, RecurringDefinition definition)
     {
          if (organizationId == Guid.Empty)
               throw new ArgumentException("Organization is required.");
          OrganizationId = organizationId;
          Versions.Add(new(OrganizationId, Id, 1, definition.Start, definition));
     }
     public void Revise(RecurringDefinition definition, DateOnly today)
     {
          if (StoppedFrom is not null)
               throw new ArgumentException("Stopped items cannot be edited.");
          var first = Versions.Min(v => v.Start);
          if (first < today && definition.Start != first)
               throw new ArgumentException("An already running item's start date cannot change.");
          Versions.Add(new(OrganizationId, Id, Versions.Max(v => v.Revision) + 1, first < today ? today : definition.Start, definition));
     }
     public bool Stop(DateOnly today)
     {
          if (StoppedFrom is not null) return false;
          StoppedFrom = today;
          return true;
     }
     public RecurringVersion? DueOn(DateOnly date)
     {
          if (StoppedFrom is not null && date >= StoppedFrom) return null;
          var version = Versions.Where(v => v.EffectiveFrom <= date)
              .OrderByDescending(v => v.Revision).FirstOrDefault();
          return version is not null && date >= version.Start && (version.End is null || date <= version.End)
              && new RecurringSchedule(version.Frequency, version.Day, version.LastDay).IsDue(date) ? version : null;
     }
}

public sealed record VehicleShare(Guid VehicleId, decimal Amount);


public sealed record RecurringDefinition(string Name, RecurringKind Kind, CostCategory? Category, decimal Amount,
    RecurringSchedule Schedule, DateOnly Start, DateOnly? End, IReadOnlyList<VehicleShare> Allocations)
{
     public void Validate()
     {
          SetupValue.Name(Name);
          SetupValue.Money(Amount);
          if (!Enum.IsDefined(Kind) || (Kind == RecurringKind.Cost ? Category is null || !Enum.IsDefined(Category.Value) : Category is not null))
               throw new ArgumentException("Costs require a valid category; savings must not have a cost category.");
          if (End < Start)
               throw new ArgumentException("End date must be on or after start date.");
          if (Allocations is null || Allocations.Count is < 1 or > 500 || Allocations.Any(a => a.VehicleId == Guid.Empty)
              || Allocations.Select(a => a.VehicleId).Distinct().Count() != Allocations.Count)
               throw new ArgumentException("Choose 1-500 distinct vehicles.");
          foreach (var allocation in Allocations) SetupValue.Money(allocation.Amount);
          if (Allocations.Sum(a => a.Amount) != Amount)
               throw new ArgumentException("Vehicle shares must equal the total exactly.");
     }
}

public sealed class RecurringVersion : IOrganizationEntity
{
     Guid IOrganizationEntity.OrganizationId
     {
          get => OrganizationId;
          set => throw new InvalidOperationException("Tenant cannot change.");
     }
     private RecurringVersion() { }
     public Guid Id { get; private set; } = Guid.NewGuid();
     public Guid OrganizationId { get; private set; }
     public Guid ItemId { get; private set; }
     public int Revision { get; private set; }
     public DateOnly EffectiveFrom { get; private set; }
     public string Name { get; private set; } = "";
     public RecurringKind Kind { get; private set; }
     public CostCategory? Category { get; private set; }
     public decimal Amount { get; private set; }
     public RecurrenceFrequency Frequency { get; private set; }
     public int? Day { get; private set; }
     public bool LastDay { get; private set; }
     public DateOnly Start { get; private set; }
     public DateOnly? End { get; private set; }
     public List<RecurringAllocation> Allocations { get; private set; } = [];
     internal RecurringVersion(Guid org, Guid item, int revision, DateOnly effectiveFrom, RecurringDefinition definition)
     {
          definition.Validate();
          (OrganizationId, ItemId, Revision, EffectiveFrom) = (org, item, revision, effectiveFrom);
          (Name, Kind, Category, Amount) = (SetupValue.Name(definition.Name), definition.Kind, definition.Category, definition.Amount);
          (Frequency, Day, LastDay, Start, End) = (definition.Schedule.Frequency, definition.Schedule.Day, definition.Schedule.LastDay, definition.Start, definition.End);
          Allocations = definition.Allocations.Select(a => new RecurringAllocation(org, Id, a.VehicleId, a.Amount)).ToList();
     }
}

public sealed class RecurringAllocation : IOrganizationEntity
{
     Guid IOrganizationEntity.OrganizationId
     {
          get => OrganizationId;
          set => throw new InvalidOperationException("Tenant cannot change.");
     }
     private RecurringAllocation() { }
     public Guid Id { get; private set; } = Guid.NewGuid();
     public Guid OrganizationId { get; private set; }
     public Guid VersionId { get; private set; }
     public Guid VehicleId { get; private set; }
     public decimal Amount { get; private set; }
     internal RecurringAllocation(Guid org, Guid version, Guid vehicle, decimal amount)
         => (OrganizationId, VersionId, VehicleId, Amount) = (org, version, vehicle, amount);
}