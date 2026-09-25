using Auth.Domain.Setup;

namespace Auth.Application.Setup;

public sealed record Page<T>(IReadOnlyList<T> Items, int PageNumber, int PageSize, int Total);
public sealed record CompanyDto(Guid Id, string Name, int VehicleCount);
public sealed record TargetDto(DateOnly EffectiveFrom, decimal WeeklyAmount, int Revision);
public sealed record VehicleDto(Guid Id, Guid CompanyId, string CompanyName, string Registration, DateOnly JoinedOn,
    decimal WeeklyTarget, IReadOnlyList<TargetDto> Targets);
public sealed record SaveCompany(string Name, string Reason);
public sealed record SaveVehicle(Guid CompanyId, string Registration, DateOnly JoinedOn, decimal WeeklyTarget, string Reason);
public sealed record SaveRecurring(string Name, RecurringKind Kind, CostCategory? Category, decimal Amount,
    RecurrenceFrequency Frequency, int? Day, bool LastDay, DateOnly Start, DateOnly? End, List<VehicleShare> Allocations, string Reason)
{
    public RecurringDefinition Definition() => new(Name, Kind, Category, Amount, new(Frequency, Day, LastDay), Start, End, Allocations);
}
public sealed record StopRecurring(bool Confirmed, string Reason);
public sealed record RecurringDto(Guid Id, Guid VersionId, int Revision, string Name, RecurringKind Kind, CostCategory? Category,
    decimal Amount, RecurrenceFrequency Frequency, int? Day, bool LastDay, DateOnly Start, DateOnly? End, DateOnly? StoppedFrom,
    IReadOnlyList<VehicleShare> Allocations);
public sealed record PostingDto(Guid ItemId, Guid VersionId, DateOnly Date, string Name, RecurringKind Kind, CostCategory? Category, decimal Amount);
public sealed record VehicleReport(Guid VehicleId, DateOnly From, DateOnly Through, decimal Costs, decimal Savings, IReadOnlyList<PostingDto> Postings);

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
}