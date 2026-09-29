namespace Auth.Domain.Setup;

// What the owner put into a vehicle before and around buying it. It is never counted as money out.
public sealed class VehicleInvestment : IOrganizationEntity
{
     public const int DescriptionLength = 160;
     Guid IOrganizationEntity.OrganizationId
     {
          get => OrganizationId;
          set => throw new InvalidOperationException("Tenant cannot change.");
     }
     private VehicleInvestment() { }
     public Guid Id { get; private set; } = Guid.NewGuid();
     public Guid OrganizationId { get; private set; }
     public Guid VehicleId { get; private set; }
     public DateOnly Date { get; private set; }
     public string Description { get; private set; } = "";
     public decimal Amount { get; private set; }
     public Guid RecordedBy { get; private set; }
     public DateTimeOffset RecordedAt { get; private set; }

     public VehicleInvestment(FleetVehicle vehicle, DateOnly date, string description, decimal amount, DateOnly today,
          Guid recordedBy, DateTimeOffset recordedAt)
     {
          if (recordedBy == Guid.Empty)
               throw new ArgumentException("The person recording it is required.");
          (OrganizationId, VehicleId, RecordedBy, RecordedAt) = (vehicle.OrganizationId, vehicle.Id, recordedBy, recordedAt);
          Change(date, description, amount, today);
     }

     public bool Change(DateOnly date, string description, decimal amount, DateOnly today)
     {
          if (date == default || date > today)
               throw new ArgumentException("An investment date is required and cannot be after the business date.");
          var value = description?.Trim();
          if (string.IsNullOrWhiteSpace(value) || value.Length > DescriptionLength)
               throw new ArgumentException($"Say what it was, in 1-{DescriptionLength} characters.");
          SetupValue.Money(amount);
          if (date == Date && value == Description && amount == Amount) return false;
          (Date, Description, Amount) = (date, value, amount);
          return true;
     }
}
