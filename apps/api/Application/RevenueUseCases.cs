using System.Text.Json;
using Auth.Application.Setup;
using Auth.Domain;

namespace Auth.Application.Revenue;

public sealed class RevenueUseCases(ISetupExecution execution, IRevenueRepository repository, IClock clock)
{
    private static readonly string[] WritePermissions = ["revenue.capture", "revenue.correct"];
    private static readonly string[] DashboardPermissions = ["dash.capture", "dash.revenue", "dash.gaps", "dash.edits"];

    public Task<RevenueWeekDto> Week(DateOnly? weekStart, Guid? companyId, CancellationToken ct) =>
        execution.Read("revenue.view", actor => repository.Week(actor, weekStart, companyId, ct), ct);

    public Task<RevenueDashboardDto> Dashboard(string period, CancellationToken ct) =>
        execution.ReadAny(DashboardPermissions, actor => repository.Dashboard(actor, period, ct), ct);

    public Task<Guid> Save(Guid vehicleId, DateOnly date, SaveRevenue input, CancellationToken ct) =>
        execution.WriteAny(WritePermissions, async actor =>
        {
            var entry = input.Entry();
            if (date == default || date > actor.Today)
                throw new ArgumentException("Revenue cannot be recorded for a future date.");

            var vehicle = await repository.Vehicle(actor, vehicleId, ct) ?? throw new KeyNotFoundException();
            if (!vehicle.ActiveOn(date))
                throw new ArgumentException("Revenue can only be recorded while the vehicle is active.");
            if (entry.Reason is not null && !actor.Permissions.Contains("revenue.no_earnings"))
                throw new UnauthorizedAccessException();

            var existing = await repository.Record(actor, vehicleId, date, ct);
            var canCapture = actor.Permissions.Contains("revenue.capture");
            var canCorrect = actor.Permissions.Contains("revenue.correct");
            if (existing is null && !canCapture)
                throw new UnauthorizedAccessException();
            if (existing is not null && date < actor.Today && !canCorrect)
                throw new UnauthorizedAccessException();
            if (existing is not null && date == actor.Today && !canCapture && !canCorrect)
                throw new UnauthorizedAccessException();

            if (existing is not null && existing.Matches(entry))
                return existing.Id;

            if (existing is null)
            {
                var earliest = await repository.EarliestMissing(actor, vehicle, date, ct);
                if (earliest is not null && earliest.Value != date)
                    throw new ArgumentException($"Record {earliest.Value:yyyy-MM-dd} before this date first.");
            }

            var before = existing is null ? null : Snapshot(existing);
            if (existing is null)
            {
                existing = new RevenueRecord(actor.OrganizationId, vehicleId, date, entry, clock.UtcNow, actor.UserId);
                repository.Add(existing);
            }
            else
            {
                existing.Replace(entry, date, clock.UtcNow, actor.UserId);
            }

            var after = Snapshot(existing);
            var reason = before is null
                ? entry.Reason is null ? "Recorded revenue" : $"Recorded no revenue: {entry.DisplayReason}"
                : "Corrected revenue after capture";
            await repository.RecordChange(actor, existing.Id, before, after, reason, ct);
            return existing.Id;
        }, ct);

    private static object Snapshot(RevenueRecord record) => new
    {
        record.Id,
        record.VehicleId,
        record.BusinessDate,
        record.Amount,
        Reason = record.Reason?.ToString(),
        record.Note,
        record.CapturedAt,
        record.CapturedBy,
        record.UpdatedAt,
        record.UpdatedBy,
        record.CorrectedAfterDate,
        record.Version
    };
}
