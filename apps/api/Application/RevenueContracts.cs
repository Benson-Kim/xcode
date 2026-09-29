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
    bool EditedAfterCapture);

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
    decimal Revenue,
    decimal Expected,
    int? Percent,
    int CapturedToday,
    int VehiclesToday,
    int MissingDays,
    int MissingVehicles,
    int EditedRecords);

public sealed record SaveRevenue(decimal? Amount, string? Reason, string? Note)
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
    Task<RevenueWeekDto> Week(SetupActor actor, DateOnly? weekStart, Guid? companyId, CancellationToken ct);
    Task<RevenueDashboardDto> Dashboard(SetupActor actor, string period, CancellationToken ct);
    Task<FleetVehicle?> Vehicle(SetupActor actor, Guid id, CancellationToken ct);
    Task<RevenueRecord?> Record(SetupActor actor, Guid vehicleId, DateOnly date, CancellationToken ct);
    Task<DateOnly?> EarliestMissing(SetupActor actor, FleetVehicle vehicle, DateOnly before, CancellationToken ct);
    void Add(RevenueRecord record);
    Task RecordChange(SetupActor actor, Guid entityId, object? before, object after, string reason, CancellationToken ct);
}
