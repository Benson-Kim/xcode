using Auth.Domain.Setup;

namespace Auth.Application.Setup;

public sealed record Page<T>(IReadOnlyList<T> Items, int PageNumber, int PageSize, int Total);
public sealed record CompanyDto(Guid Id, string Name, int VehicleCount, bool Active, DateOnly? ArchivedOn);
public sealed record CompanyOption(Guid Id, string Name);
public sealed record TargetDto(DateOnly EffectiveFrom, decimal WeeklyAmount, int Revision);
public sealed record VehicleDto(Guid Id, Guid CompanyId, string CompanyName, string Registration, DateOnly JoinedOn,
    DateOnly? LeftOn, bool Active, decimal WeeklyTarget, IReadOnlyList<TargetDto> Targets, int RecurringItems);
// One change-log line: who changed which setup record, and the reason they gave.
public sealed record HistoryEntry(long Version, string Section, Guid EntityId, string Reason, DateTimeOffset OccurredAt, Guid ActorId, string ActorName,
    string? Before = null, string? After = null);
// Reasons are optional on these saves (contract C7): without one, the change log gets an automatic reason.
public sealed record SaveCompany(string Name, string? Reason = null);
public sealed record CompanyLifecycleRequest(string? Reason = null);
public sealed record SaveVehicle(Guid CompanyId, string Registration, DateOnly JoinedOn, decimal WeeklyTarget, string? Reason = null);
public sealed record VehicleLifecycleRequest(DateOnly LeftOn, string? Reason = null);
public sealed record VehicleRestoreRequest(string? Reason = null);
// Name is for savings only: a cost is named after its expense item. Category is ignored (Phase 1 rows keep theirs).
public sealed record SaveRecurring(string? Name, RecurringKind Kind, CostCategory? Category, decimal Amount,
    RecurrenceFrequency Frequency, int? Day, bool LastDay, DateOnly Start, DateOnly? End, List<VehicleShare> Allocations, string? Reason = null,
    Guid? ExpenseItemId = null, string? Note = null, int? Month = null)
{
    public RecurringDefinition Definition(string? name, ExpenseBucket? bucket) => new(name!, Kind, null, Amount,
        new(Frequency, Day, LastDay, Month), Start, End, Allocations, ExpenseItemId, bucket, string.IsNullOrWhiteSpace(Note) ? null : Note.Trim());
}
public sealed record StopRecurring(bool Confirmed, string Reason);
// Partial: the item also posts to vehicles outside the viewer's scope. Amount and Allocations then cover only the
// viewer's share, and only someone who can see every vehicle on it may change it.
// Amount is always the sum of Allocations, retired vehicles included; ActiveAmount is the part that still posts.
// ExpenseItemName is the item's current name; Name is the name saved on this version.
public sealed record RecurringDto(Guid Id, Guid VersionId, int Revision, string Name, RecurringKind Kind, CostCategory? Category,
    decimal Amount, RecurrenceFrequency Frequency, int? Day, bool LastDay, DateOnly Start, DateOnly? End, DateOnly? StoppedFrom,
    IReadOnlyList<AllocationDto> Allocations, bool Partial = false, Guid? ExpenseItemId = null, string? ExpenseItemName = null,
    ExpenseBucket? Bucket = null, string? Note = null, int? Month = null, decimal ActiveAmount = 0);
public sealed record AllocationDto(Guid VehicleId, decimal Amount, string? Registration, bool Active = true);
// What a recurring-item editor needs to pick vehicles, without the vehicle-management view.
public sealed record VehicleOption(Guid Id, Guid CompanyId, string CompanyName, string Registration, bool Active = true);
public sealed record PostingDto(Guid ItemId, Guid VersionId, DateOnly Date, string Name, RecurringKind Kind, CostCategory? Category, decimal Amount,
    ExpenseBucket? Bucket = null);
public sealed record VehicleReport(Guid VehicleId, DateOnly From, DateOnly Through, decimal Costs, decimal Savings, IReadOnlyList<PostingDto> Postings);
public sealed record ExpenseItemDto(Guid Id, Guid CategoryId, string Name, bool Active, DateOnly? StoppedOn);
public sealed record ExpenseCategoryDto(Guid Id, string Name, ExpenseBucket Bucket, bool Active, DateOnly? StoppedOn, IReadOnlyList<ExpenseItemDto> Items);
// An item people may pick today: the item and its category are both in use.
public sealed record ExpenseItemOption(Guid Id, string Name, Guid CategoryId, string CategoryName, ExpenseBucket Bucket);
public sealed record SaveExpenseCategory(string? Name, ExpenseBucket Bucket);
public sealed record SaveExpenseItem(string? Name);
public sealed record InvestmentEntryDto(Guid Id, DateOnly Date, string Description, decimal Amount, string RecordedBy, DateTimeOffset RecordedAt);
// Returned and PercentPaidOff stay null until the vehicle report can say what has come back.
public sealed record InvestmentDto(Guid VehicleId, decimal TotalInvested, decimal? Returned, decimal? PercentPaidOff, IReadOnlyList<InvestmentEntryDto> Entries);
public sealed record SaveInvestment(DateOnly Date, string? Description, decimal Amount);

public static class ReportPeriod
{
    // The current week or month up to the organization's business date, so a report never asks for the future.
    public static (DateOnly From, DateOnly Through) Current(string period, DateOnly today, int firstDayOfWeek) => period switch
    {
        "week" => (today.AddDays(-(((int)today.DayOfWeek - firstDayOfWeek + 7) % 7)), today),
        "month" => (new DateOnly(today.Year, today.Month, 1), today),
        _ => throw new ArgumentException("Period must be week or month.")
    };
}

public static class SetupPagination
{
    public static void Validate(int page, int pageSize)
    {
        if (page is < 1 or > 100000 || pageSize is < 1 or > 100) throw new ArgumentException("Page must be 1–100000 and page size 1–100.");
    }
    public static string Reason(string? reason)
    {
        if (string.IsNullOrWhiteSpace(reason) || reason.Trim().Length > 500) throw new ArgumentException("A reason of 1–500 characters is required.");
        return reason.Trim();
    }
    // A typed reason is checked and kept; with none, the caller writes an automatic reason instead (contract C7).
    public static string? OptionalReason(string? reason) => string.IsNullOrWhiteSpace(reason) ? null : Reason(reason);
    // Automatic reasons quote names, so they are clipped to what the change log holds.
    public static string Automatic(string reason) => reason.Length <= 500 ? reason : reason[..497] + "...";
    // "a", "a and b", "a, b and c".
    public static string Listed(IReadOnlyList<string> parts) =>
        parts.Count <= 1 ? string.Concat(parts) : string.Join(", ", parts.Take(parts.Count - 1)) + " and " + parts[^1];
}
