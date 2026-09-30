using Auth.Domain.Setup;

namespace Auth.Application.Setup;

public sealed record Page<T>(IReadOnlyList<T> Items, int PageNumber, int PageSize, int Total);
public sealed record CompanyDto(Guid Id, string Name, int VehicleCount, bool Active, DateOnly? ArchivedOn);
public sealed record CompanyOption(Guid Id, string Name);
public sealed record TargetDto(DateOnly EffectiveFrom, decimal WeeklyAmount, int Revision);
// The weekly target and the scheduled item count are null, and the targets empty, for someone who lists vehicles only
// to reach their investment (invest.view without vehicles.manage).
public sealed record VehicleDto(Guid Id, Guid CompanyId, string CompanyName, string Registration, DateOnly JoinedOn,
    DateOnly? LeftOn, bool Active, decimal? WeeklyTarget, IReadOnlyList<TargetDto> Targets, int? RecurringItems);
// One change-log line: who changed which setup record, and the reason they gave.
public sealed record HistoryEntry(long Version, string Section, Guid EntityId, string Reason, DateTimeOffset OccurredAt, Guid ActorId, string ActorName,
    string? Before = null, string? After = null);
// Reasons are optional on these saves (contract C7): the change log always gets an automatic reason, and a typed one follows it.
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
// Contract C6: money in against the target, money out in its three buckets, and what is left before and after savings.
// MoneyOut is the three buckets and nothing else (investment never counts); Costs repeats it for Phase 1 clients.
public sealed record VehicleReport(Guid VehicleId, DateOnly From, DateOnly Through, decimal MoneyIn, decimal Target,
    decimal Repairs, decimal Charges, decimal Loans, decimal MoneyOut, decimal Net, decimal Savings, decimal AfterSavings,
    decimal Costs, IReadOnlyList<PostingDto> Postings);
public sealed record ExpenseItemDto(Guid Id, Guid CategoryId, string Name, bool Active, DateOnly? StoppedOn);
public sealed record ExpenseCategoryDto(Guid Id, string Name, ExpenseBucket Bucket, bool Active, DateOnly? StoppedOn, IReadOnlyList<ExpenseItemDto> Items);
// An item people may pick today: the item and its category are both in use.
public sealed record ExpenseItemOption(Guid Id, string Name, Guid CategoryId, string CategoryName, ExpenseBucket Bucket);
public sealed record SaveExpenseCategory(string? Name, ExpenseBucket Bucket);
public sealed record SaveExpenseItem(string? Name);
public sealed record InvestmentEntryDto(Guid Id, DateOnly Date, string Description, decimal Amount, string RecordedBy, DateTimeOffset RecordedAt);
// Returned is the net contribution since the vehicle joined (InvestmentUseCases.Get); PercentPaidOff is null when nothing went in.
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
    // A typed reason is checked and kept; the change log shows it after the automatic reason (contract C7).
    public static string? OptionalReason(string? reason) => string.IsNullOrWhiteSpace(reason) ? null : Reason(reason);
    // Automatic reasons quote names, so they are clipped to what the change log holds.
    public static string Automatic(string reason) => reason.Length <= 500 ? reason : reason[..497] + "...";
    // Keeps the automatic reason and adds a typed one after it, as in "Removed access for Grace Achieng. Reason: Moved to
    // another SACCO." When both do not fit the change log, the automatic part is shortened first, so the words a person
    // typed are kept whole wherever they fit.
    public static string Automatic(string reason, string? typed)
    {
        if (string.IsNullOrEmpty(typed)) return Automatic(reason);
        var suffix = $". Reason: {typed}{(typed[^1] is '.' or '!' or '?' ? "" : ".")}";
        var room = Math.Max(500 - suffix.Length, 100);
        return Automatic((reason.Length <= room ? reason : reason[..(room - 3)] + "...") + suffix);
    }
    // "a", "a and b", "a, b and c".
    public static string Listed(IReadOnlyList<string> parts) =>
        parts.Count <= 1 ? string.Concat(parts) : string.Join(", ", parts.Take(parts.Count - 1)) + " and " + parts[^1];
}
