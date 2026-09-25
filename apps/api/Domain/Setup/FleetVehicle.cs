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
     public List<VehicleTarget> Targets { get; private set; } = [];
     public FleetVehicle(Guid organizationId, Guid companyId, VehicleRegistration registration, DateOnly joinedOn, decimal weeklyTarget)
     {
          if (organizationId == Guid.Empty || companyId == Guid.Empty)
               throw new ArgumentException("Organization and company are required.");
          OrganizationId = organizationId;
          CompanyId = companyId;
          Registration = registration.Value;
          JoinedOn = joinedOn;
          Targets.Add(new(organizationId, Id, joinedOn, SetupValue.Money(weeklyTarget), 1));
     }

     public bool Update(Guid companyId, DateOnly joinedOn, decimal weeklyTarget, DateOnly today)
     {
          if (companyId == Guid.Empty)
               throw new ArgumentException("Company is required.");
          SetupValue.Money(weeklyTarget);
          var changed = CompanyId != companyId || JoinedOn != joinedOn;
          CompanyId = companyId;
          JoinedOn = joinedOn;
          // Append even for repeated edits today: history is never overwritten.
          if (TargetOn(today < joinedOn ? joinedOn : today) != weeklyTarget)
          {
               Targets.Add(new(OrganizationId, Id, today < joinedOn ? joinedOn : today, weeklyTarget, Targets.Max(t => t.Revision) + 1));
               changed = true;
          }
          return changed;
     }
     public decimal TargetOn(DateOnly date) => date < JoinedOn ? 0 : Targets
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