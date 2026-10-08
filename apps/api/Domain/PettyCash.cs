namespace Auth.Domain;

public enum PettyCashKind
{
    Cash = 1,
    Expense = 2,
    Credit = 3
}

public enum PettyCashStatus
{
    Waiting = 1,
    Approved = 2,
    SentBack = 3
}

// What a person types for one entry. Every amount is signed and never zero: a negative expense is a refund, negative
// cash is cash taken back, a negative credit note is money the payee paid back.
public sealed record PettyCashLine(PettyCashKind Kind, DateOnly Date, Guid? VehicleId, Guid? ExpenseItemId, decimal Units,
    decimal UnitAmount, string? Payee, string? Note, bool Reimbursable)
{
    public const int NoteLength = 80;
    public const int PayeeLength = 80;
    public const int CommentLength = 200;
    public const decimal MaxUnits = 999999999.999m;
    public const decimal MaxAmount = 999999999999.99m;

    // Units can be part of one, such as 11.875 litres; the total is rounded to the cent, halves away from zero.
    public decimal Total => decimal.Round(Units * UnitAmount, 2, MidpointRounding.AwayFromZero);

    // Cash raises the float; expenses and credit notes lower it.
    public decimal Effect => Kind == PettyCashKind.Cash ? Total : -Total;

    public string? CleanNote => string.IsNullOrWhiteSpace(Note) ? null : Note.Trim();
    public string? CleanPayee => string.IsNullOrWhiteSpace(Payee) ? null : Payee.Trim();

    public void Validate()
    {
        if (!Enum.IsDefined(Kind))
            throw new ArgumentException("Choose an expense, a credit note or cash.");
        if (Date == default)
            throw new ArgumentException("Enter the date.");
        if (UnitAmount == 0)
            throw new ArgumentException("Enter an amount other than zero.");
        if (decimal.Round(UnitAmount, 2) != UnitAmount || Math.Abs(UnitAmount) > MaxAmount)
            throw new ArgumentException("Enter the amount with at most two decimals.");
        if (Units <= 0 || Units > MaxUnits || decimal.Round(Units, 3) != Units)
            throw new ArgumentException("Units must be above zero, with at most three decimals.");
        if (Kind != PettyCashKind.Expense && Units != 1)
            throw new ArgumentException("Only an expense has units.");
        if (Total == 0)
            throw new ArgumentException("The total rounds to zero. Check the units and the amount.");
        if (Math.Abs(Total) > MaxAmount)
            throw new ArgumentException("The total is too large.");
        if (CleanNote?.Length > NoteLength)
            throw new ArgumentException($"The note must be at most {NoteLength} characters.");

        switch (Kind)
        {
            case PettyCashKind.Expense:
                if (VehicleId is null || VehicleId == Guid.Empty)
                    throw new ArgumentException("Choose the vehicle.");
                if (ExpenseItemId is null || ExpenseItemId == Guid.Empty)
                    throw new ArgumentException("Choose what it was for.");
                if (CleanPayee is not null || Reimbursable)
                    throw new ArgumentException("Only a credit note has a payee.");
                break;
            case PettyCashKind.Credit:
                if (VehicleId is not null || ExpenseItemId is not null)
                    throw new ArgumentException("A credit note is not recorded against a vehicle.");
                if (CleanPayee is null)
                    throw new ArgumentException("Say who was paid.");
                if (CleanPayee.Length > PayeeLength)
                    throw new ArgumentException($"The payee must be at most {PayeeLength} characters.");
                if (CleanNote is null)
                    throw new ArgumentException("Say why the money was paid.");
                break;
            default:
                if (VehicleId is not null || ExpenseItemId is not null || CleanPayee is not null || Reimbursable)
                    throw new ArgumentException("Cash given has only an amount, a date and a note.");
                break;
        }
    }
}

// One movement on a holder's float. Nothing is deleted: a removed entry keeps its row, its reason and who removed it,
// and leaves every list and total.
public sealed class PettyCashEntry : IOrganizationEntity
{
    Guid IOrganizationEntity.OrganizationId
    {
        get => OrganizationId;
        set => throw new InvalidOperationException("Tenant cannot change.");
    }

    private PettyCashEntry() { }

    public Guid Id { get; private set; }
    public Guid OrganizationId { get; private set; }
    public Guid HolderId { get; private set; }
    public PettyCashKind Kind { get; private set; }
    public DateOnly Date { get; private set; }
    public Guid? VehicleId { get; private set; }
    public Guid? ExpenseItemId { get; private set; }
    public decimal Units { get; private set; }
    public decimal UnitAmount { get; private set; }
    public decimal Total { get; private set; }
    public string? Payee { get; private set; }
    public string? Note { get; private set; }
    public bool Reimbursable { get; private set; }
    public PettyCashStatus? Status { get; private set; }
    public string? SentBackNote { get; private set; }
    public Guid? ReviewedBy { get; private set; }
    public DateTimeOffset? ReviewedAt { get; private set; }
    public Guid RecordedBy { get; private set; }
    public DateTimeOffset RecordedAt { get; private set; }
    public Guid UpdatedBy { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }
    public Guid? RemovedBy { get; private set; }
    public DateTimeOffset? RemovedAt { get; private set; }
    public string? RemovalReason { get; private set; }
    public long Version { get; private set; } = 1;

    public bool Removed => RemovedAt is not null;
    public bool Reviewed => Kind != PettyCashKind.Cash;
    public decimal Effect => Kind == PettyCashKind.Cash ? Total : -Total;

    public PettyCashEntry(Guid id, Guid organizationId, Guid holderId, PettyCashLine line, DateTimeOffset recordedAt, Guid actorId)
    {
        if (id == Guid.Empty || organizationId == Guid.Empty || holderId == Guid.Empty || actorId == Guid.Empty)
            throw new ArgumentException("Entry, organization, holder and actor are required.");
        Utc(recordedAt);
        line.Validate();
        (Id, OrganizationId, HolderId, Kind) = (id, organizationId, holderId, line.Kind);
        Apply(line);
        Status = Reviewed ? PettyCashStatus.Waiting : null;
        (RecordedBy, RecordedAt, UpdatedBy, UpdatedAt) = (actorId, recordedAt, actorId, recordedAt);
    }

    public bool Matches(PettyCashLine line) =>
        Kind == line.Kind && Date == line.Date && VehicleId == line.VehicleId && ExpenseItemId == line.ExpenseItemId &&
        Units == line.Units && UnitAmount == line.UnitAmount && Reimbursable == line.Reimbursable &&
        string.Equals(Payee, line.CleanPayee, StringComparison.Ordinal) && string.Equals(Note, line.CleanNote, StringComparison.Ordinal);

    // Any change goes back for approval: what was approved is no longer what is recorded.
    public void Change(PettyCashLine line, DateTimeOffset at, Guid actorId)
    {
        Live();
        if (line.Kind != Kind)
            throw new ArgumentException("An entry cannot change between expense, credit note and cash. Remove it and record it again.");
        Utc(at);
        line.Validate();
        Apply(line);
        if (Reviewed)
            (Status, SentBackNote, ReviewedBy, ReviewedAt) = (PettyCashStatus.Waiting, null, null, null);
        Touch(at, actorId);
    }

    public void Approve(DateTimeOffset at, Guid actorId)
    {
        Waiting();
        Utc(at);
        (Status, SentBackNote, ReviewedBy, ReviewedAt) = (PettyCashStatus.Approved, null, actorId, at);
        Touch(at, actorId);
    }

    public void SendBack(string comment, DateTimeOffset at, Guid actorId)
    {
        Waiting();
        Utc(at);
        var text = comment?.Trim();
        if (string.IsNullOrEmpty(text))
            throw new ArgumentException("Say what should be fixed.");
        if (text.Length > PettyCashLine.CommentLength)
            throw new ArgumentException($"The comment must be at most {PettyCashLine.CommentLength} characters.");
        (Status, SentBackNote, ReviewedBy, ReviewedAt) = (PettyCashStatus.SentBack, text, actorId, at);
        Touch(at, actorId);
    }

    public void Remove(string reason, DateTimeOffset at, Guid actorId)
    {
        Live();
        Utc(at);
        (RemovedBy, RemovedAt, RemovalReason) = (actorId, at, reason);
        Touch(at, actorId);
    }

    private void Apply(PettyCashLine line)
    {
        (Date, VehicleId, ExpenseItemId, Units, UnitAmount, Total) =
            (line.Date, line.VehicleId, line.ExpenseItemId, line.Units, line.UnitAmount, line.Total);
        (Payee, Note, Reimbursable) = (line.CleanPayee, line.CleanNote, line.Reimbursable);
    }

    private void Touch(DateTimeOffset at, Guid actorId)
    {
        if (actorId == Guid.Empty) throw new ArgumentException("An actor is required.");
        (UpdatedAt, UpdatedBy) = (at, actorId);
        Version++;
    }

    private void Live()
    {
        if (Removed) throw new InvalidOperationException("This entry was removed.");
    }

    private void Waiting()
    {
        Live();
        if (!Reviewed)
            throw new ArgumentException("Cash given is not approved.");
        if (Status != PettyCashStatus.Waiting)
            throw new ArgumentException("Only an entry waiting for approval can be approved or sent back.");
    }

    private static void Utc(DateTimeOffset at)
    {
        if (at.Offset != TimeSpan.Zero) throw new ArgumentException("Petty cash instants must be UTC.");
    }
}
