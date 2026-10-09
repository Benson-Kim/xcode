namespace Auth.Domain;

// One vehicle's row of a purchase, as typed. The rules are a petty cash expense's: units above zero with at most three
// decimals, a signed amount that is never zero, and a total rounded to the cent with halves away from zero.
public sealed record CentralExpenseLine(DateOnly Date, Guid VehicleId, Guid ExpenseItemId, decimal Units, decimal UnitAmount, string? Note)
{
    public decimal Total => decimal.Round(Units * UnitAmount, 2, MidpointRounding.AwayFromZero);

    public string? CleanNote => string.IsNullOrWhiteSpace(Note) ? null : Note.Trim();

    public void Validate() =>
        new PettyCashLine(PettyCashKind.Expense, Date, VehicleId, ExpenseItemId, Units, UnitAmount, null, Note, false).Validate();
}

public sealed record ExpenseAllocationLine(Guid VehicleId, decimal Amount);

// One purchase, shared by one to fifty vehicles whose amounts add up to the total exactly.
public sealed record CentralPurchase(DateOnly Date, Guid ExpenseItemId, decimal Units, decimal UnitAmount, string? Note,
    IReadOnlyList<ExpenseAllocationLine> Allocations)
{
    public const int MaxVehicles = 50;

    public decimal Total => decimal.Round(Units * UnitAmount, 2, MidpointRounding.AwayFromZero);

    public void Validate()
    {
        if (Allocations is null || Allocations.Count is < 1 or > MaxVehicles || Allocations.Any(a => a.VehicleId == Guid.Empty) ||
            Allocations.Select(a => a.VehicleId).Distinct().Count() != Allocations.Count)
            throw new ArgumentException($"Choose 1-{MaxVehicles} distinct vehicles.");
        new CentralExpenseLine(Date, Allocations[0].VehicleId, ExpenseItemId, Units, UnitAmount, Note).Validate();
        if (Allocations.Any(a => a.Amount == 0 || decimal.Round(a.Amount, 2) != a.Amount))
            throw new ArgumentException("Each vehicle's amount must be other than zero, with at most two decimals.");
        if (Allocations.Any(a => Math.Sign(a.Amount) != Math.Sign(Total)))
            throw new ArgumentException("Each vehicle's amount must have the same sign as the total.");
        if (Allocations.Sum(a => a.Amount) != Total)
            throw new ArgumentException("The vehicle amounts must add up to the total.");
    }

    // Several vehicles bought at the same unit cost keep it: an even split whose units and rounded cost still agree
    // is units / vehicles at the unit amount. Any other split stores one unit at the vehicle's own amount.
    public IReadOnlyList<CentralExpenseLine> Lines()
    {
        Validate();
        var count = Allocations.Count;
        var even = count > 1 && Allocations.All(a => a.Amount == Allocations[0].Amount);
        var share = Units / count;
        var keepsUnitCost = even && decimal.Round(share, 3) == share &&
            decimal.Round(share * UnitAmount, 2, MidpointRounding.AwayFromZero) == Allocations[0].Amount;
        return [.. Allocations.Select(a => count == 1
            ? new CentralExpenseLine(Date, a.VehicleId, ExpenseItemId, Units, UnitAmount, Note)
            : keepsUnitCost
                ? new CentralExpenseLine(Date, a.VehicleId, ExpenseItemId, share, UnitAmount, Note)
                : new CentralExpenseLine(Date, a.VehicleId, ExpenseItemId, 1, a.Amount, Note))];
    }
}

// Money out recorded straight onto one vehicle. A purchase shared by several vehicles is saved as one row each, and
// every row keeps the purchase (the group) so price reports use the true unit cost and quantity. Nothing is deleted:
// a removed row keeps its reason and who removed it, and leaves every list, total and report.
public sealed class CentralExpense : IOrganizationEntity
{
    public const int NoteLength = PettyCashLine.NoteLength;
    public const int ReasonLength = 500;

    Guid IOrganizationEntity.OrganizationId
    {
        get => OrganizationId;
        set => throw new InvalidOperationException("Tenant cannot change.");
    }

    private CentralExpense() { }

    public Guid Id { get; private set; }
    public Guid OrganizationId { get; private set; }
    public DateOnly Date { get; private set; }
    public Guid VehicleId { get; private set; }
    public Guid ExpenseItemId { get; private set; }
    public decimal Units { get; private set; }
    public decimal UnitAmount { get; private set; }
    public decimal Total { get; private set; }
    public string? Note { get; private set; }
    public Guid GroupId { get; private set; }
    public int GroupSize { get; private set; }
    public decimal GroupTotal { get; private set; }
    public decimal GroupUnits { get; private set; }
    public decimal GroupUnitAmount { get; private set; }
    public Guid RecordedBy { get; private set; }
    public DateTimeOffset RecordedAt { get; private set; }
    public Guid UpdatedBy { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }
    public Guid? RemovedBy { get; private set; }
    public DateTimeOffset? RemovedAt { get; private set; }
    public string? RemovalReason { get; private set; }
    public long Version { get; private set; } = 1;

    public bool Removed => RemovedAt is not null;

    private CentralExpense(Guid id, Guid organizationId, Guid groupId, CentralPurchase purchase, CentralExpenseLine line,
        DateTimeOffset recordedAt, Guid actorId)
    {
        if (id == Guid.Empty || organizationId == Guid.Empty || groupId == Guid.Empty || actorId == Guid.Empty)
            throw new ArgumentException("Expense, organization, group and actor are required.");
        Utc(recordedAt);
        line.Validate();
        (Id, OrganizationId, GroupId) = (id, organizationId, groupId);
        Apply(line);
        (GroupSize, GroupTotal, GroupUnits, GroupUnitAmount) = (purchase.Allocations.Count, purchase.Total, purchase.Units, purchase.UnitAmount);
        (RecordedBy, RecordedAt, UpdatedBy, UpdatedAt) = (actorId, recordedAt, actorId, recordedAt);
    }

    // One row for each vehicle of the purchase. With one vehicle the row takes the purchase's id, so a retried save
    // finds it; with several every row has an id of its own and the purchase's id is only the group's.
    public static IReadOnlyList<CentralExpense> Record(Guid? groupId, Guid organizationId, CentralPurchase purchase,
        DateTimeOffset recordedAt, Guid actorId)
    {
        var group = groupId is { } given && given != Guid.Empty ? given : Guid.NewGuid();
        return [.. purchase.Lines().Select(line => new CentralExpense(
            purchase.Allocations.Count == 1 ? group : Guid.NewGuid(), organizationId, group, purchase, line, recordedAt, actorId))];
    }

    public bool Matches(CentralExpenseLine line) =>
        Date == line.Date && VehicleId == line.VehicleId && ExpenseItemId == line.ExpenseItemId && Units == line.Units &&
        UnitAmount == line.UnitAmount && string.Equals(Note, line.CleanNote, StringComparison.Ordinal);

    // A different item, quantity or price is no longer the purchase the group describes, so the row leaves the group.
    // The group id stays: it is the key a retried save looks for. A new date, vehicle or note keeps the group.
    public void Change(CentralExpenseLine line, DateTimeOffset at, Guid actorId)
    {
        Live();
        Utc(at);
        line.Validate();
        var detaches = line.ExpenseItemId != ExpenseItemId || line.Units != Units || line.UnitAmount != UnitAmount;
        Apply(line);
        if (detaches)
            (GroupSize, GroupTotal, GroupUnits, GroupUnitAmount) = (1, Total, Units, UnitAmount);
        Touch(at, actorId);
    }

    public void Remove(string reason, DateTimeOffset at, Guid actorId)
    {
        Live();
        Utc(at);
        if (string.IsNullOrWhiteSpace(reason) || reason.Length > ReasonLength)
            throw new ArgumentException($"A reason of 1-{ReasonLength} characters is required.");
        (RemovedBy, RemovedAt, RemovalReason) = (actorId, at, reason);
        Touch(at, actorId);
    }

    private void Apply(CentralExpenseLine line) =>
        (Date, VehicleId, ExpenseItemId, Units, UnitAmount, Total, Note) =
            (line.Date, line.VehicleId, line.ExpenseItemId, line.Units, line.UnitAmount, line.Total, line.CleanNote);

    private void Touch(DateTimeOffset at, Guid actorId)
    {
        if (actorId == Guid.Empty) throw new ArgumentException("An actor is required.");
        (UpdatedAt, UpdatedBy) = (at, actorId);
        Version++;
    }

    private void Live()
    {
        if (Removed) throw new InvalidOperationException("This expense was removed.");
    }

    private static void Utc(DateTimeOffset at)
    {
        if (at.Offset != TimeSpan.Zero) throw new ArgumentException("Expense instants must be UTC.");
    }
}
