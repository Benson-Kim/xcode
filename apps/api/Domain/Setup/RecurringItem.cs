

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
          if (StoppedFrom is not null && StoppedFrom <= today)
               throw new ArgumentException("Stopped items cannot be edited.");
          // "Running" follows the current version's start, not the earliest start ever recorded, so a postponed item
          // is still editable until its new start date.
          var current = Versions.MaxBy(v => v.Revision)!;
          var running = current.Start < today;
          if (running && definition.Start != current.Start)
               throw new ArgumentException("An already running item's start date cannot change.");
          // A pending item's new version takes over from the edit date (or its earlier, backdated start), so
          // postponing never leaves the superseded version posting in between.
          var effectiveFrom = running || definition.Start >= today ? today : definition.Start;
          Versions.Add(new(OrganizationId, Id, current.Revision + 1, effectiveFrom, definition));
     }
     public bool Stop(DateOnly today)
     {
          if (StoppedFrom is not null)
          {
               // A stop already in effect is final. One dated later is pending: it is cancelled, never re-dated, so
               // stopping again on an earlier business date cannot quietly move the date (D16).
               if (StoppedFrom != today)
                    throw new ArgumentException(StoppedFrom > today
                        ? "This item is already due to stop on a later date. Cancel that stop first."
                        : "The item is already stopped.");
               return false;
          }
          StoppedFrom = today;
          return true;
     }
     // A stop dated after the business date has not taken effect yet, so it can be cancelled and the item keeps
     // posting. One already in effect stays final, because its missed postings were never written (D16).
     public bool CancelStop(DateOnly today)
     {
          if (StoppedFrom is null) return false;
          if (StoppedFrom <= today)
               throw new ArgumentException("This item has already stopped. Add a new scheduled item instead.");
          StoppedFrom = null;
          return true;
     }
     public RecurringVersion? DueOn(DateOnly date)
     {
          if (StoppedFrom is not null && date >= StoppedFrom) return null;
          var version = Versions.Where(v => v.EffectiveFrom <= date)
              .OrderByDescending(v => v.Revision).FirstOrDefault();
          return version is not null && date >= version.Start && (version.End is null || date <= version.End)
              && version.Schedule().IsDue(date) ? version : null;
     }
     // Every day from `from` through `through` on which DueOn gives a version, with that version, without asking about
     // each day. A version is in charge from its EffectiveFrom until a higher revision takes effect, so each version's
     // due dates are stepped within [max(from, EffectiveFrom, Start), min(through, End, next EffectiveFrom − 1, StoppedFrom − 1)].
     // O(R log R + due dates), against O(D·R log R) for calling DueOn on each of D days. Dates come out per version.
     public IEnumerable<(DateOnly Date, RecurringVersion Version)> DueBetween(DateOnly from, DateOnly through)
     {
          var end = StoppedFrom is { } stopped && stopped <= through ? stopped.DayNumber - 1 : through.DayNumber;
          var supersededFrom = int.MaxValue;
          foreach (var version in Versions.OrderByDescending(v => v.Revision))
          {
               var first = Math.Max(from.DayNumber, Math.Max(version.EffectiveFrom.DayNumber, version.Start.DayNumber));
               var last = Math.Min(Math.Min(end, supersededFrom - 1), version.End?.DayNumber ?? int.MaxValue);
               supersededFrom = Math.Min(supersededFrom, version.EffectiveFrom.DayNumber);
               if (first > last) continue;
               foreach (var date in version.Schedule().Occurrences(DateOnly.FromDayNumber(first), DateOnly.FromDayNumber(last)))
                    yield return (date, version);
          }
     }
}

public sealed record VehicleShare(Guid VehicleId, decimal Amount);


// Category is the Phase 1 cost category, kept only so legacy versions stay readable. New costs name an expense
// item instead, and carry the bucket of that item's category at the time of saving.
public sealed record RecurringDefinition(string Name, RecurringKind Kind, CostCategory? Category, decimal Amount,
    RecurringSchedule Schedule, DateOnly Start, DateOnly? End, IReadOnlyList<VehicleShare> Allocations,
    Guid? ExpenseItemId = null, ExpenseBucket? Bucket = null, string? Note = null)
{
     public const int NoteLength = 200;

     public void Validate()
     {
          SetupValue.Name(Name);
          SetupValue.Money(Amount);
          var costTypeValid = Category is null ? Bucket is not null && Enum.IsDefined(Bucket.Value) : Enum.IsDefined(Category.Value) && Bucket is null;
          if (!Enum.IsDefined(Kind) || (Kind == RecurringKind.Cost ? !costTypeValid : Category is not null || Bucket is not null || ExpenseItemId is not null))
               throw new ArgumentException("Costs need an expense item; savings must not have one.");
          if (Note?.Length > NoteLength)
               throw new ArgumentException($"A note can have at most {NoteLength} characters.");
          if (End < Start)
               throw new ArgumentException("End date must be on or after start date.");
          if (Allocations is null || Allocations.Count is < 1 or > 500 || Allocations.Any(a => a.VehicleId == Guid.Empty)
              || Allocations.Select(a => a.VehicleId).Distinct().Count() != Allocations.Count)
               throw new ArgumentException("Choose 1-500 distinct vehicles.");
          foreach (var allocation in Allocations) SetupValue.Money(allocation.Amount);
          if (Allocations.Sum(a => a.Amount) != Amount)
               throw new ArgumentException("Vehicle shares must equal the total exactly.");
     }

     // What may be saved from now on (addendum 1). Versions saved before it (daily schedules, the four old cost
     // categories, older starts) are history: they stay readable and keep posting, and are never checked against this.
     public void ValidateNew(DateOnly today, DateOnly? currentStart)
     {
          Validate();
          if (Schedule.Frequency == RecurrenceFrequency.Daily)
               throw new ArgumentException("Daily schedules are no longer offered. Choose weekly, monthly or yearly.");
          if (Kind == RecurringKind.Savings && Schedule.Frequency is not (RecurrenceFrequency.Weekly or RecurrenceFrequency.Monthly))
               throw new ArgumentException("Savings are set aside weekly or monthly.");
          if (Kind == RecurringKind.Cost && (ExpenseItemId is null || Category is not null))
               throw new ArgumentException("Choose the expense item this cost is for.");
          if (Start == default)
               throw new ArgumentException("Start date is required.");
          // Anything older than the current month is a one-off expense, not a schedule.
          if (Start != currentStart && Start < new DateOnly(today.Year, today.Month, 1))
               throw new ArgumentException("A schedule can start no earlier than the first of the current month.");
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
     public Guid? ExpenseItemId { get; private set; }
     // Every cost version carries its bucket; legacy versions were backfilled from their category (assumption A2).
     public ExpenseBucket? Bucket { get; private set; }
     public string? Note { get; private set; }
     public int? Month { get; private set; }
     public List<RecurringAllocation> Allocations { get; private set; } = [];
     public RecurringSchedule Schedule() => new(Frequency, Day, LastDay, Month);
     // The bucket a cost reports under. A Phase 1 version stored without one follows its category (assumption A2), and
     // any other cost counts as a recurring charge, so every cost lands in exactly one bucket. Savings have none.
     // Every cost reports under a bucket; one stored with neither a bucket nor a legacy category counts as a recurring charge.
     public ExpenseBucket? ReportedBucket() =>
          ExpenseBuckets.Of(Kind, Category, Bucket) ?? (Kind == RecurringKind.Cost ? ExpenseBucket.RecurringCharges : null);
     internal RecurringVersion(Guid org, Guid item, int revision, DateOnly effectiveFrom, RecurringDefinition definition)
     {
          definition.Validate();
          (OrganizationId, ItemId, Revision, EffectiveFrom) = (org, item, revision, effectiveFrom);
          (Name, Kind, Category, Amount) = (SetupValue.Name(definition.Name), definition.Kind, definition.Category, definition.Amount);
          (Frequency, Day, LastDay, Month, Start, End) = (definition.Schedule.Frequency, definition.Schedule.Day, definition.Schedule.LastDay,
               definition.Schedule.Month, definition.Start, definition.End);
          (ExpenseItemId, Note) = (definition.ExpenseItemId, definition.Note);
          Bucket = definition.Bucket ?? (definition.Category is { } category ? ExpenseBuckets.FromLegacy(category) : null);
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