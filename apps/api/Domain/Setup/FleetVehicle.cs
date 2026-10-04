using System.Text.RegularExpressions;
namespace Auth.Domain.Setup;

public sealed record VehicleRegistration
{
     public string Value { get; }
     public VehicleRegistration(string value)
     {
          var compact = (value ?? "").Trim().ToUpperInvariant().Replace(" ", "");
          if (!Regex.IsMatch(compact, "^K[A-Z]{2}[0-9]{3}[A-Z]$", RegexOptions.CultureInvariant))
               throw new ArgumentException("Use the registration format KDA 482M.");
          Value = compact[..3] + " " + compact[3..];
     }
}

public sealed class FleetVehicle : IOrganizationEntity
{
     Guid IOrganizationEntity.OrganizationId
     {
          get => OrganizationId;
          set => throw new InvalidOperationException("Tenant cannot change.");
     }
     private FleetVehicle() { }
     public Guid Id { get; private set; } = Guid.NewGuid();
     public Guid OrganizationId { get; private set; }
     public Guid CompanyId { get; private set; }
     public string Registration { get; private set; } = "";
     public DateOnly JoinedOn { get; private set; }
     public DateOnly? LeftOn { get; private set; }
     public List<VehicleTarget> Targets { get; private set; } = [];
     public List<VehicleAwayPeriod> AwayPeriods { get; private set; } = [];

     public FleetVehicle(Guid organizationId, Guid companyId, VehicleRegistration registration, DateOnly joinedOn, decimal weeklyTarget)
     {
          if (organizationId == Guid.Empty || companyId == Guid.Empty)
               throw new ArgumentException("Organization and company are required.");
          if (joinedOn == default) throw new ArgumentException("Join date is required.");
          OrganizationId = organizationId;
          CompanyId = companyId;
          Registration = registration.Value;
          JoinedOn = joinedOn;
          Targets.Add(new(organizationId, Id, joinedOn, SetupValue.Money(weeklyTarget), 1));
     }

     // Away days are not in the fleet either, so nothing expects or misses revenue for them (D4). Callers that
     // ask about a past date must load AwayPeriods; one asking about the business date need not, because a period
     // is only ever written when the vehicle is already back.
     public bool ActiveOn(DateOnly date) => ActiveOn(JoinedOn, LeftOn, date) && !AwayOn(date);

     public bool AwayOn(DateOnly date) => AwayPeriods.Any(p => p.Covers(date));

     // The join and leave half of "active": joined by the date and not yet left. Queries spell it out as
     // JoinedOn <= date && (LeftOn == null || LeftOn > date). Away periods are a per-date lookup, so a query that
     // needs them filters the rows it loaded rather than asking the database.
     public static bool ActiveOn(DateOnly joinedOn, DateOnly? leftOn, DateOnly date) => date >= joinedOn && (leftOn is null || date < leftOn);

     public bool Update(Guid companyId, DateOnly joinedOn, decimal weeklyTarget, DateOnly today)
     {
          if (companyId == Guid.Empty)
               throw new ArgumentException("Company is required.");
          if (joinedOn == default || joinedOn > today)
               throw new ArgumentException("A vehicle cannot join after the business date.");
          if (LeftOn is not null)
               throw new ArgumentException("Retired vehicles must be restored before they can be edited.");
          SetupValue.Money(weeklyTarget);
          var changed = CompanyId != companyId || JoinedOn != joinedOn;
          var previousJoin = JoinedOn;
          var targetAtPreviousJoin = TargetOn(previousJoin);
          CompanyId = companyId;
          JoinedOn = joinedOn;
          // An earlier join date must not leave days with no target before the first recorded one.
          if (joinedOn < previousJoin && Targets.All(t => t.EffectiveFrom > joinedOn))
               Targets.Add(new(OrganizationId, Id, joinedOn, targetAtPreviousJoin, Targets.Max(t => t.Revision) + 1));
          // Append even for repeated edits today: history is never overwritten.
          var effectiveToday = today < joinedOn ? joinedOn : today;
          if (TargetOn(effectiveToday) != weeklyTarget)
          {
               Targets.Add(new(OrganizationId, Id, effectiveToday, weeklyTarget, Targets.Max(t => t.Revision) + 1));
               changed = true;
          }
          return changed;
     }

     public bool Retire(DateOnly leftOn, DateOnly today)
     {
          if (leftOn == default || leftOn > today || leftOn < JoinedOn)
               throw new ArgumentException("A vehicle's leave date must be from its join date through the business date.");
          // Away stretches never overlap, so each one reads as a single absence from the fleet.
          if (AwayPeriods.Count > 0 && leftOn < AwayPeriods.Max(p => p.ReturnedOn))
               throw new ArgumentException("A vehicle's leave date must be on or after the day it last returned to the fleet.");
          if (LeftOn is not null)
          {
               if (LeftOn != leftOn) throw new ArgumentException("The vehicle is already retired.");
               return false;
          }
          LeftOn = leftOn;
          return true;
     }

     // Restoring a vehicle whose leave already took effect records the stretch it was away, so those days are
     // neither expected nor missing once it is back (D4). A leave undone on its own date took effect for no day,
     // so it leaves no stretch behind.
     public bool Restore(DateOnly returnedOn, DateOnly today)
     {
          if (LeftOn is not { } left) return false;
          if (returnedOn == default || returnedOn < left || returnedOn > today)
               throw new ArgumentException("A vehicle's return date must be from the day it left through the business date.");
          if (returnedOn > left) AwayPeriods.Add(new(OrganizationId, Id, left, returnedOn));
          LeftOn = null;
          return true;
     }

     public decimal TargetOn(DateOnly date) => !ActiveOn(date) ? 0 : Targets
         .Where(t => t.EffectiveFrom <= date)
         .OrderByDescending(t => t.EffectiveFrom)
         .ThenByDescending(t => t.Revision)
         .Select(t => t.WeeklyAmount)
         .FirstOrDefault();
}

public sealed class VehicleTarget : IOrganizationEntity
{
     Guid IOrganizationEntity.OrganizationId
     {
          get => OrganizationId;
          set => throw new InvalidOperationException("Tenant cannot change.");
     }
     private VehicleTarget() { }
     public Guid Id { get; private set; } = Guid.NewGuid();
     public Guid OrganizationId { get; private set; }
     public Guid VehicleId { get; private set; }
     public DateOnly EffectiveFrom { get; private set; }
     public decimal WeeklyAmount { get; private set; }
     public int Revision { get; private set; }
     internal VehicleTarget(Guid organizationId, Guid vehicleId, DateOnly from, decimal amount, int revision)
         => (OrganizationId, VehicleId, EffectiveFrom, WeeklyAmount, Revision) = (organizationId, vehicleId, from, amount, revision);
}

public sealed class VehicleAwayPeriod : IOrganizationEntity
{
     Guid IOrganizationEntity.OrganizationId
     {
          get => OrganizationId;
          set => throw new InvalidOperationException("Tenant cannot change.");
     }
     private VehicleAwayPeriod() { }
     public Guid Id { get; private set; } = Guid.NewGuid();
     public Guid OrganizationId { get; private set; }
     public Guid VehicleId { get; private set; }
     public DateOnly LeftOn { get; private set; }
     public DateOnly ReturnedOn { get; private set; }
     internal VehicleAwayPeriod(Guid organizationId, Guid vehicleId, DateOnly leftOn, DateOnly returnedOn)
         => (OrganizationId, VehicleId, LeftOn, ReturnedOn) = (organizationId, vehicleId, leftOn, returnedOn);

     // Read like the dates on the vehicle itself: away from the day it left, back in the fleet on the day it returned.
     public bool Covers(DateOnly date) => date >= LeftOn && date < ReturnedOn;
}
