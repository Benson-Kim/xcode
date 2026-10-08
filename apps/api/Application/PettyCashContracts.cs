using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;

namespace Auth.Application.PettyCash;

// Kinds and statuses travel as these words, the ones the web and the phone read (packages/shared/src/pettyCash.ts).
public static class PettyCashWords
{
    public static string Kind(PettyCashKind kind) => kind switch
    {
        PettyCashKind.Cash => "cash",
        PettyCashKind.Expense => "expense",
        PettyCashKind.Credit => "credit",
        _ => throw new ArgumentOutOfRangeException(nameof(kind))
    };

    public static string? Status(PettyCashStatus? status) => status switch
    {
        null => null,
        PettyCashStatus.Waiting => "waiting",
        PettyCashStatus.Approved => "approved",
        PettyCashStatus.SentBack => "sentBack",
        _ => throw new ArgumentOutOfRangeException(nameof(status))
    };

    public static PettyCashKind? ParseKind(string? value) => value?.Trim() switch
    {
        null or "" => null,
        "cash" => PettyCashKind.Cash,
        "expense" => PettyCashKind.Expense,
        "credit" => PettyCashKind.Credit,
        _ => throw new ArgumentException("Choose an expense, a credit note or cash.")
    };

    // "expense,credit" asks for either; nothing asks for every kind.
    public static IReadOnlyList<PettyCashKind> ParseKinds(string? value) =>
        [.. (value ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(x => ParseKind(x)!.Value).Distinct()];

    public static PettyCashStatus? ParseStatus(string? value) => value?.Trim() switch
    {
        null or "" => null,
        "waiting" => PettyCashStatus.Waiting,
        "approved" => PettyCashStatus.Approved,
        "sentBack" => PettyCashStatus.SentBack,
        _ => throw new ArgumentException("Status must be waiting, approved or sentBack.")
    };
}

public sealed record PettyCashPermissionsDto(Guid? HolderId, bool CanSpend, bool CanViewAll, bool CanIssue, bool CanIssueNegative,
    bool CanApproveItem, bool CanApproveDay, decimal? ApprovalLimit);

// Active is false once the person no longer records spending; their float still shows while it has entries.
public sealed record PettyCashHolderDto(Guid Id, string Name, bool Active);

// The figures for a day or a week. MoneyOut is Expenses plus CreditNotes; ClosingBalance is OpeningBalance + CashReceived - MoneyOut.
public sealed record PettyCashFiguresDto(decimal OpeningBalance, decimal CashReceived, decimal Expenses, decimal CreditNotes,
    decimal MoneyOut, decimal ClosingBalance);

// The float to date. Waiting, Approved and SentBack split expenses and credit notes by status.
public sealed record PettyCashFloatDto(Guid HolderId, string Name, bool Active, decimal CashReceived, decimal CreditNotes, decimal Expenses,
    decimal Waiting, int WaitingCount, decimal Approved, decimal SentBack, decimal Balance, DateOnly? LastCashOn);

// Period is "day" or "week"; From and To are the first and last day it covers.
public sealed record PettyCashOverviewDto(DateOnly BusinessDate, DateOnly Date, string Period, DateOnly From, DateOnly To,
    PettyCashPermissionsDto Permissions, IReadOnlyList<PettyCashHolderDto> Holders, PettyCashFiguresDto Figures,
    IReadOnlyList<PettyCashFloatDto> Floats);

// The flags say what the signed-in person may do with this entry, so clients never work the rules out themselves.
public sealed record PettyCashEntryDto(Guid Id, string Kind, Guid HolderId, string HolderName, DateOnly Date, Guid? VehicleId,
    string? Registration, Guid? ExpenseItemId, string? ExpenseItemName, ExpenseBucket? Bucket, decimal Units, decimal UnitAmount,
    decimal Total, string? Payee, string? Note, bool Reimbursable, string? Status, string? SentBackNote, string? ReviewedByName,
    DateTimeOffset? ReviewedAt, string RecordedByName, DateTimeOffset RecordedAt, DateTimeOffset UpdatedAt, long Version,
    bool CanEdit, bool CanRemove, bool CanReview, bool AboveLimit);

public sealed record PettyCashOptionsDto(IReadOnlyList<VehicleOption> Vehicles, IReadOnlyList<ExpenseItemOption> Items,
    IReadOnlyList<PettyCashHolderDto> Holders);

// Id on a create is the client's own, so a retried create answers with the entry it already made. Version is
// required on a change. HolderId names the float for cash, and for a credit note an issuer records for someone else.
public sealed record SavePettyCashEntry(string Kind, DateOnly Date, decimal UnitAmount, Guid? Id = null, Guid? HolderId = null,
    Guid? VehicleId = null, Guid? ExpenseItemId = null, decimal? Units = null, string? Payee = null, string? Note = null,
    bool Reimbursable = false, long? Version = null)
{
    public PettyCashLine Line()
    {
        var kind = PettyCashWords.ParseKind(Kind) ?? throw new ArgumentException("Choose an expense, a credit note or cash.");
        var line = new PettyCashLine(kind, Date, VehicleId, ExpenseItemId, Units ?? 1, UnitAmount, Payee, Note, Reimbursable);
        line.Validate();
        return line;
    }
}

public sealed record PettyCashSaved(Guid Id, long Version, string? Status, decimal Balance);
public sealed record ReviewPettyCashEntry(long Version);
public sealed record SendBackPettyCashEntry(long Version, string? Comment);
public sealed record RemovePettyCashEntry(long Version, string? Reason);
public sealed record ApprovePettyCashDay(DateOnly Date, Guid? HolderId = null);
public sealed record PettyCashDayApproved(int Approved, decimal Total, int Skipped);

public sealed record PettyCashDashboardFloat(decimal Balance, int WaitingCount, decimal WaitingTotal, int SentBackCount, decimal ApprovedThisMonth);
public sealed record PettyCashDashboardHolder(Guid HolderId, string Name, int Count, decimal Total, DateOnly Oldest);
public sealed record PettyCashDashboardApprovals(int Count, decimal Total, decimal? ApprovalLimit, int AboveLimit,
    IReadOnlyList<PettyCashDashboardHolder> Holders);
// Each card is null unless the person holds its permission.
public sealed record PettyCashDashboardDto(PettyCashDashboardFloat? Float, PettyCashDashboardApprovals? Approvals);

// Entry filters; every part is optional. From and To are both included.
public sealed record PettyCashFilter(DateOnly? From, DateOnly? To, Guid? HolderId, IReadOnlyList<PettyCashKind> Kinds, PettyCashStatus? Status, string? Text);

// An entry with the names its row shows.
public sealed record PettyCashEntryRow(PettyCashEntry Entry, string HolderName, string? Registration, string? ExpenseItemName,
    ExpenseBucket? Bucket, string? ReviewedByName, string RecordedByName);

// Sums of one holder's entries of one kind and status, before, within and after a window of dates.
public sealed record PettyCashTally(Guid HolderId, PettyCashKind Kind, PettyCashStatus? Status, int Period, decimal Total, int Count,
    DateOnly Latest)
{
    public const int Before = 0, Within = 1, After = 2;
}

/// <summary>The entry changed after the client read it, or a client id was already used for another entry.</summary>
public sealed class PettyCashConflictException(PettyCashEntryDto? current, string? message = null)
    : Exception(message ?? "This entry was changed after you opened it. Check it and save again.")
{
    public PettyCashEntryDto? Current { get; } = current;
}

/// <summary>Cash taken back would leave the float below zero and the person may not do that.</summary>
public sealed class PettyCashBelowZeroException(decimal balanceAfter)
    : ArgumentException("This takes the float below zero, which needs the permission \"Send money that takes a float below zero\".")
{
    public decimal BalanceAfter { get; } = balanceAfter;
}

public interface IPettyCashRepository
{
    // People who record spending today, and anyone who already has entries.
    Task<IReadOnlyList<PettyCashHolderDto>> Holders(CancellationToken ct);
    Task<decimal?> ApprovalLimit(Guid userId, CancellationToken ct);
    Task<IReadOnlyList<PettyCashTally>> Tallies(IReadOnlyCollection<Guid> holderIds, DateOnly from, DateOnly through, CancellationToken ct);
    Task<decimal> Balance(Guid holderId, CancellationToken ct);
    Task<Page<PettyCashEntryRow>> Entries(SetupActor actor, IReadOnlyCollection<Guid> holderIds, PettyCashFilter filter, int page, int pageSize,
        CancellationToken ct);
    Task<PettyCashEntryRow?> Row(SetupActor actor, Guid id, CancellationToken ct);
    // The entry if the actor can see it and it is not removed, tracked for a change.
    Task<PettyCashEntry?> Entry(SetupActor actor, Guid id, CancellationToken ct);
    // Any entry with this id in the organization, removed or not; a retried create looks for its own.
    Task<PettyCashEntry?> AnyEntry(Guid id, CancellationToken ct);
    // Waiting expenses and credit notes the actor can see; a date narrows them to one day.
    Task<IReadOnlyList<PettyCashEntry>> Waiting(SetupActor actor, IReadOnlyCollection<Guid> holderIds, DateOnly? date, bool track, CancellationToken ct);
    // A vehicle in the actor's scope, with its away periods so FleetVehicle.ActiveOn reads them.
    Task<FleetVehicle?> Vehicle(SetupActor actor, Guid id, CancellationToken ct);
    Task<IReadOnlyDictionary<Guid, string>> Names(IEnumerable<Guid> userIds, CancellationToken ct);
    Task<IReadOnlyDictionary<Guid, string>> Registrations(IEnumerable<Guid> vehicleIds, CancellationToken ct);
    void Add(PettyCashEntry entry);
    Task RecordChange(SetupActor actor, PettyCashEntry entry, object? before, object after, string reason, CancellationToken ct);
}
