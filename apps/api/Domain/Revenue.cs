using Auth.Domain.Setup;

namespace Auth.Domain;

public enum RevenueNoEarningsReason
{
    Garage = 1,
    Arrest = 2,
    NoCrew = 3,
    Other = 4
}

public sealed record RevenueEntry(decimal? Amount, RevenueNoEarningsReason? Reason, string? Note)
{
    public void Validate()
    {
        if (Amount is not null)
        {
            SetupValue.Money(Amount.Value);
            if (Reason is not null || !string.IsNullOrWhiteSpace(Note))
                throw new ArgumentException("Revenue amount cannot have a no-earnings reason.");
            return;
        }

        if (Reason is null || !Enum.IsDefined(Reason.Value))
            throw new ArgumentException("Enter revenue or choose a no-earnings reason.");

        var note = Note?.Trim();
        if (Reason == RevenueNoEarningsReason.Other && string.IsNullOrWhiteSpace(note))
            throw new ArgumentException("Explain what happened when choosing Other.");
        if (note is not null && note.Length > 80)
            throw new ArgumentException("The no-earnings note must be at most 80 characters.");
        if (Reason != RevenueNoEarningsReason.Other && !string.IsNullOrWhiteSpace(note))
            throw new ArgumentException("Only Other may have a no-earnings note.");
    }

    public string DisplayReason => Reason switch
    {
        RevenueNoEarningsReason.Garage => "Garage",
        RevenueNoEarningsReason.Arrest => "Arrest",
        RevenueNoEarningsReason.NoCrew => "No Crew",
        RevenueNoEarningsReason.Other => "Other",
        _ => ""
    };
}

public sealed class RevenueRecord : IOrganizationEntity
{
    Guid IOrganizationEntity.OrganizationId
    {
        get => OrganizationId;
        set => throw new InvalidOperationException("Tenant cannot change.");
    }

    private RevenueRecord() { }

    public Guid Id { get; private set; } = Guid.NewGuid();
    public Guid OrganizationId { get; private set; }
    public Guid VehicleId { get; private set; }
    public DateOnly BusinessDate { get; private set; }
    public decimal? Amount { get; private set; }
    public RevenueNoEarningsReason? Reason { get; private set; }
    public string? Note { get; private set; }
    public DateTimeOffset CapturedAt { get; private set; }
    public Guid CapturedBy { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }
    public Guid UpdatedBy { get; private set; }
    public bool CorrectedAfterDate { get; private set; }
    public long Version { get; private set; } = 1;

    public RevenueRecord(Guid organizationId, Guid vehicleId, DateOnly businessDate, RevenueEntry entry, DateTimeOffset capturedAt, Guid actorId)
    {
        if (organizationId == Guid.Empty || vehicleId == Guid.Empty || businessDate == default || actorId == Guid.Empty)
            throw new ArgumentException("Organization, vehicle, date and actor are required.");
        if (capturedAt.Offset != TimeSpan.Zero)
            throw new ArgumentException("Revenue instants must be UTC.");

        entry.Validate();
        OrganizationId = organizationId;
        VehicleId = vehicleId;
        BusinessDate = businessDate;
        Amount = entry.Amount;
        Reason = entry.Reason;
        Note = entry.Note?.Trim();
        CapturedAt = capturedAt;
        CapturedBy = actorId;
        UpdatedAt = capturedAt;
        UpdatedBy = actorId;
    }

    public bool Matches(RevenueEntry entry) =>
        Amount == entry.Amount &&
        Reason == entry.Reason &&
        string.Equals(Note, entry.Note?.Trim(), StringComparison.Ordinal);

    public void Replace(RevenueEntry entry, DateOnly businessDate, DateTimeOffset updatedAt, Guid actorId)
    {
        if (businessDate != BusinessDate)
            throw new InvalidOperationException("A revenue record's business date cannot change.");
        if (updatedAt.Offset != TimeSpan.Zero || actorId == Guid.Empty)
            throw new ArgumentException("Revenue updates must have a UTC timestamp and actor.");

        entry.Validate();
        Amount = entry.Amount;
        Reason = entry.Reason;
        Note = entry.Note?.Trim();
        UpdatedAt = updatedAt;
        UpdatedBy = actorId;
        CorrectedAfterDate = true;
        Version++;
    }
}
