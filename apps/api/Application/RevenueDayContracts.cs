namespace Auth.Application.Revenue;

// Capture revenue for one day: every vehicle the person sees that is active on the date, in registration order, with
// its cell and what it recorded on the same day a week earlier. Truncated says more vehicles were active than listed.
public sealed record RevenueDayDto(DateOnly Date, DateOnly BusinessDate, IReadOnlyList<RevenueDayVehicleDto> Vehicles, bool Truncated)
{
    public const int Limit = RevenueWeekPage.LegacyLimit;
}

public sealed record RevenueDayVehicleDto(Guid Id, Guid CompanyId, string Registration, RevenueCellDto Day, RevenueLastWeekDto? LastWeek);

// The same day a week earlier: an amount or a no-earnings reason, or null when that day has no record.
public sealed record RevenueLastWeekDto(decimal? Amount, string? Reason);

// One day for several vehicles, saved together or not at all. Each row follows the rules of a single save, version
// included; a row identical to the saved record changes nothing.
public sealed record SaveRevenueDay(IReadOnlyList<SaveRevenueDayRow>? Rows);

public sealed record SaveRevenueDayRow(Guid VehicleId, decimal? Amount, string? Reason, string? Note, long? Version = null)
{
    public SaveRevenue Input => new(Amount, Reason, Note, Version);
}

public sealed record RevenueDaySaved(IReadOnlyList<RevenueDayRowSaved> Rows);

public sealed record RevenueDayRowSaved(Guid VehicleId, Guid Id, long Version);
