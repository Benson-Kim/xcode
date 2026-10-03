using System.Globalization;
using Auth.Domain;
using Auth.Domain.Setup;

namespace Auth.Application.Revenue;

public sealed record RevenueCompanyOption(Guid Id, string Name);
public sealed record RevenueCellDto(
    DateOnly Date,
    string Status,
    decimal Expected,
    decimal? Amount,
    string? Reason,
    string? Note,
    bool CanEdit,
    bool EditedAfterCapture,
    long? Version)
{
    // The week grid and a 409's current cell come from here, so clients and the server agree on what may be opened.
    public static RevenueCellDto For(SetupActor actor, FleetVehicle vehicle, DateOnly date, RevenueRecord? record, DateOnly? earliestMissing)
    {
        var status = !vehicle.ActiveOn(date) ? "none" : date > actor.Today ? "future" :
            record is null ? "missing" : record.Amount is not null ? "amount" : "reason";
        var capture = actor.Permissions.Contains("revenue.capture");
        var correct = actor.Permissions.Contains("revenue.correct");
        var canEdit = status switch
        {
            // A later missing day stays shut until the earliest missing day is filled.
            "missing" => capture && (earliestMissing is null || date <= earliestMissing.Value),
            "amount" or "reason" => date == actor.Today ? capture || correct : correct,
            _ => false
        };
        return new(date, status, decimal.Round(vehicle.TargetOn(date) / 7m, 2), record?.Amount,
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

public sealed record RevenueWeekDto(
    DateOnly WeekStart,
    DateOnly WeekThrough,
    DateOnly CurrentWeekStart,
    DateOnly BusinessDate,
    IReadOnlyList<RevenueCompanyOption> Companies,
    IReadOnlyList<RevenueVehicleDto> Vehicles,
    decimal TotalAmount,
    decimal TotalExpected,
    int? Percent);

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
public sealed class RevenueConflictException(RevenueCellDto current)
    : Exception("This day was changed after you opened it. Check the current record and save again.")
{
    public RevenueCellDto Current { get; } = current;
}

/// <summary>An earlier day has no record yet. It is still a plain 400 wherever the revenue error filter is absent.</summary>
public sealed class RevenueEarlierDayMissingException(DateOnly earliestMissing)
    : ArgumentException($"Record {earliestMissing.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)} before this date first.")
{
    public DateOnly EarliestMissing { get; } = earliestMissing;
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
    Task<RevenueWeekDto> Week(SetupActor actor, DateOnly? weekStart, Guid? companyId, Guid? vehicleId, CancellationToken ct);
    Task<RevenueDashboardDto> Dashboard(SetupActor actor, string period, Guid? companyId, CancellationToken ct);
    Task<FleetVehicle?> Vehicle(SetupActor actor, Guid id, CancellationToken ct);
    Task<RevenueRecord?> Record(SetupActor actor, Guid vehicleId, DateOnly date, CancellationToken ct);
    Task<DateOnly?> EarliestMissing(SetupActor actor, FleetVehicle vehicle, DateOnly before, CancellationToken ct);
    void Add(RevenueRecord record);
    Task RecordChange(SetupActor actor, Guid entityId, object? before, object after, string reason, CancellationToken ct);
}
