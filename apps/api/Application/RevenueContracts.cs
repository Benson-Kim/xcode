using System.Globalization;
using System.Text.Json.Serialization;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;

namespace Auth.Application.Revenue;

public sealed record RevenueCompanyOption(Guid Id, string Name);

// The columns of a day's record that the grid shows; the grid never loads whole records.
public sealed record RevenueDayRecord(Guid VehicleId, DateOnly BusinessDate, decimal? Amount, RevenueNoEarningsReason? Reason,
    string? Note, bool CorrectedAfterDate, long Version)
{
    public static RevenueDayRecord Of(RevenueRecord record) =>
        new(record.VehicleId, record.BusinessDate, record.Amount, record.Reason, record.Note, record.CorrectedAfterDate, record.Version);
}

// The wire values are the clients' RevenueStatus (packages/shared/src/revenue.ts).
[JsonConverter(typeof(JsonStringEnumConverter<CellStatus>))]
public enum CellStatus
{
    [JsonStringEnumMemberName("none")] None,
    [JsonStringEnumMemberName("future")] Future,
    [JsonStringEnumMemberName("missing")] Missing,
    [JsonStringEnumMemberName("amount")] Amount,
    [JsonStringEnumMemberName("reason")] Reason
}

public sealed record RevenueCellDto(
    DateOnly Date,
    CellStatus Status,
    decimal Expected,
    decimal? Amount,
    string? Reason,
    string? Note,
    bool CanEdit,
    bool EditedAfterCapture,
    long? Version)
{
    public static CellStatus StatusOf(FleetVehicle vehicle, DateOnly date, DateOnly today, RevenueDayRecord? record) =>
        !vehicle.ActiveOn(date) ? CellStatus.None : date > today ? CellStatus.Future :
        record is null ? CellStatus.Missing : record.Amount is not null ? CellStatus.Amount : CellStatus.Reason;

    // The week grid and a 409's current cell come from here, so clients and the server agree on what may be opened.
    // target is the vehicle's weekly target that day (FleetVehicle.TargetOn), which the caller works out once.
    public static RevenueCellDto For(SetupActor actor, FleetVehicle vehicle, DateOnly date, decimal target, RevenueDayRecord? record)
    {
        var status = StatusOf(vehicle, date, actor.Today, record);
        var capture = actor.Permissions.Contains(PermissionKeys.RevenueCapture);
        var correct = actor.Permissions.Contains(PermissionKeys.RevenueCorrect);
        var canEdit = status switch
        {
            // Days are captured in any order, so every missing day is open to capture.
            CellStatus.Missing => capture,
            CellStatus.Amount or CellStatus.Reason => date == actor.Today ? capture || correct : correct,
            CellStatus.None or CellStatus.Future => false,
            _ => throw new InvalidOperationException($"Unknown cell status {status}.")
        };
        return new(date, status, decimal.Round(target / 7m, 2), record?.Amount,
            record?.Reason is null ? null : RevenueEntry.Label(record.Reason), record?.Note, canEdit,
            record?.CorrectedAfterDate == true, record?.Version);
    }
}

public sealed record RevenueVehicleDto(
    Guid Id,
    Guid CompanyId,
    string CompanyName,
    string Registration,
    DateOnly JoinedOn,
    DateOnly? LeftOn,
    DateOnly? EarliestMissing,
    IReadOnlyList<RevenueCellDto> Days,
    decimal TotalAmount,
    decimal TotalExpected,
    int? Percent);

// The week's figures (totals, percent, day totals, first gap) cover every vehicle in the grid; Vehicles lists one page
// of it in registration order. The fields after Percent were added later, so released clients read the rest unchanged.
public sealed record RevenueWeekDto(
    DateOnly WeekStart,
    DateOnly WeekThrough,
    DateOnly CurrentWeekStart,
    DateOnly BusinessDate,
    IReadOnlyList<RevenueCompanyOption> Companies,
    IReadOnlyList<RevenueVehicleDto> Vehicles,
    decimal TotalAmount,
    decimal TotalExpected,
    int? Percent,
    int PageNumber,
    int PageSize,
    int TotalVehicles,
    bool Truncated,
    IReadOnlyList<RevenueDayTotalDto> DayTotals,
    RevenueGapDto? FirstGap);

// Amount sums the days recorded with an amount; Expected sums each vehicle's expected figure for the days that count.
public sealed record RevenueDayTotalDto(DateOnly Date, decimal Amount, decimal Expected);

// Where capture starts: the earliest day still missing a record, and the first vehicle in grid order missing it.
public sealed record RevenueGapDto(Guid VehicleId, DateOnly Date);

// Which of a week grid's vehicles one response lists.
public sealed record RevenueWeekPage(int Number, int Size)
{
    // Released clients ask with neither page nor pageSize and get the whole grid, up to this many vehicles.
    public const int LegacyLimit = 500;
    public const int DefaultSize = 100;
    public static readonly RevenueWeekPage Legacy = new(1, LegacyLimit);

    // Null when neither is given. Either one alone asks for paging, with the other defaulted.
    public static RevenueWeekPage? Of(int? page, int? pageSize)
    {
        if (page is null && pageSize is null) return null;
        var requested = new RevenueWeekPage(page ?? 1, pageSize ?? DefaultSize);
        SetupPagination.Validate(requested.Number, requested.Size);
        return requested;
    }
}

public sealed record RevenueDashboardDto(
    string Period,
    DateOnly From,
    DateOnly Through,
    DateOnly BusinessDate,
    decimal? Revenue,
    decimal? Expected,
    int? Percent,
    int? CapturedToday,
    int? VehiclesToday,
    int? MissingDays,
    int? MissingVehicles,
    int? EditedRecords);

public sealed record RevenueSaved(Guid Id, long Version);

/// <summary>The day holds a different record than the one this save was based on.</summary>
public sealed class RevenueConflictException(RevenueCellDto current, Guid? vehicleId = null, string? registration = null)
    : Exception(registration is null
        ? "This day was changed after you opened it. Check the current record and save again."
        : $"{registration} was changed after you opened the day. Check its current record and save again.")
{
    public RevenueCellDto Current { get; } = current;

    // Set when the save covered several vehicles, so the client knows which row changed.
    public Guid? VehicleId { get; } = vehicleId;
}

// Version is the record version the client last saw; it is required to change an existing record.
public sealed record SaveRevenue(decimal? Amount, string? Reason, string? Note, long? Version = null)
{
    public RevenueEntry Entry()
    {
        RevenueNoEarningsReason? reason = Reason?.Trim() switch
        {
            null or "" => null,
            "Garage" => RevenueNoEarningsReason.Garage,
            "Arrest" => RevenueNoEarningsReason.Arrest,
            "No Crew" or "NoCrew" => RevenueNoEarningsReason.NoCrew,
            "Other" => RevenueNoEarningsReason.Other,
            _ => throw new ArgumentException("Choose a valid no-earnings reason.")
        };
        var entry = new RevenueEntry(Amount, reason, Note);
        entry.Validate();
        return entry;
    }
}

public interface IRevenueRepository
{
    // A null page lists the whole grid up to RevenueWeekPage.LegacyLimit; a vehicle's own week is never paged.
    Task<RevenueWeekDto> Week(SetupActor actor, DateOnly? weekStart, Guid? companyId, Guid? vehicleId, RevenueWeekPage? page, CancellationToken ct);
    Task<RevenueDashboardDto> Dashboard(SetupActor actor, string period, Guid? companyId, CancellationToken ct);
    Task<FleetVehicle?> Vehicle(SetupActor actor, Guid id, CancellationToken ct);
    Task<RevenueRecord?> Record(SetupActor actor, Guid vehicleId, DateOnly date, CancellationToken ct);
    Task<RevenueDayDto> Day(SetupActor actor, DateOnly date, Guid? companyId, CancellationToken ct);
    Task<IReadOnlyList<FleetVehicle>> Vehicles(SetupActor actor, Guid[] ids, CancellationToken ct);
    Task<IReadOnlyList<RevenueRecord>> Records(SetupActor actor, Guid[] vehicleIds, DateOnly date, CancellationToken ct);
    void Add(RevenueRecord record);
    Task RecordChange(SetupActor actor, Guid entityId, object? before, object after, string reason, CancellationToken ct);
}
