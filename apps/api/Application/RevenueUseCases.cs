using System.Globalization;
using System.Text.Json;
using Auth.Application.Setup;
using Auth.Domain;

namespace Auth.Application.Revenue;

public sealed class RevenueUseCases(ISetupExecution execution, IRevenueRepository repository, IClock clock)
{
    private static readonly string[] WritePermissions = ["revenue.capture", "revenue.correct"];
    private static readonly string[] DashboardPermissions = ["dash.capture", "dash.revenue", "dash.gaps", "dash.edits"];

    public Task<RevenueWeekDto> Week(DateOnly? weekStart, Guid? companyId, Guid? vehicleId, CancellationToken ct) =>
        execution.Read("revenue.view", actor => repository.Week(actor, weekStart, companyId, vehicleId, ct), ct);

    // The cards can be narrowed to one PSV company, the same filter the week grid takes (D15). It can only
    // narrow what the person already reaches, never widen it.
    public Task<RevenueDashboardDto> Dashboard(string period, Guid? companyId, CancellationToken ct) =>
        execution.ReadAny(DashboardPermissions, async actor => Visible(actor, await repository.Dashboard(actor, period, companyId, ct)), ct);

    // Each card's figures reach only the people who hold that card's own permission; the rest are null. Capture
    // (the Revenue clerk's card) never opens the revenue totals, and the revenue card never opens the capture counts.
    private static RevenueDashboardDto Visible(SetupActor actor, RevenueDashboardDto dashboard)
    {
        var revenue = actor.Permissions.Contains("dash.revenue");
        var capture = actor.Permissions.Contains("dash.capture");
        var gaps = actor.Permissions.Contains("dash.gaps");
        var edits = actor.Permissions.Contains("dash.edits");
        return dashboard with
        {
            Revenue = revenue ? dashboard.Revenue : null,
            Expected = revenue ? dashboard.Expected : null,
            Percent = revenue ? dashboard.Percent : null,
            CapturedToday = capture ? dashboard.CapturedToday : null,
            VehiclesToday = capture ? dashboard.VehiclesToday : null,
            MissingDays = gaps ? dashboard.MissingDays : null,
            MissingVehicles = gaps ? dashboard.MissingVehicles : null,
            EditedRecords = edits ? dashboard.EditedRecords : null
        };
    }

    public Task<RevenueSaved> Save(Guid vehicleId, DateOnly date, SaveRevenue input, CancellationToken ct) =>
        execution.WriteAny(WritePermissions, async actor =>
        {
            var entry = input.Entry();
            var vehicle = await repository.Vehicle(actor, vehicleId, ct) ?? throw new KeyNotFoundException();
            var existing = await repository.Record(actor, vehicleId, date, ct);

            // An identical replay changes nothing, so a phone draining its queue late (even after the day closed) always succeeds.
            if (existing is not null && existing.Matches(entry))
                return new RevenueSaved(existing.Id, existing.Version);

            if (date == default || date > actor.Today)
                throw new ArgumentException("Revenue cannot be recorded for a future date.");
            if (!vehicle.ActiveOn(date))
                throw new ArgumentException(vehicle.AwayOn(date)
                    ? "The vehicle was away from the fleet on this day, so it is not a day revenue is recorded for."
                    : "Revenue can only be recorded while the vehicle is active.");
            // Authorization comes before state disclosure (D5): the conflict below carries the saved record, so
            // whoever reads it must be someone who was allowed to make this change in the first place.
            if (entry.Reason is not null && !actor.Permissions.Contains("revenue.no_earnings"))
                throw Needs("Recording a no-earnings reason", "revenue.no_earnings");
            var canCapture = actor.Permissions.Contains("revenue.capture");
            var canCorrect = actor.Permissions.Contains("revenue.correct");
            if (existing is null && !canCapture)
                throw Needs("Recording a day that has no record yet", "revenue.capture");
            if (existing is not null && date < actor.Today && !canCorrect)
                throw Needs("Changing a past day", "revenue.correct");

            // Never overwrite what the client did not see.
            if (existing is not null && input.Version != existing.Version)
                throw new RevenueConflictException(RevenueCellDto.For(actor, vehicle, date, existing, null));

            if (existing is null)
            {
                var earliest = await repository.EarliestMissing(actor, vehicle, date, ct);
                if (earliest is not null)
                    throw new RevenueEarlierDayMissingException(earliest.Value);
            }

            var before = existing is null ? null : Snapshot(existing);
            if (existing is null)
            {
                existing = new RevenueRecord(actor.OrganizationId, vehicleId, date, entry, clock.UtcNow, actor.UserId);
                repository.Add(existing);
            }
            else
            {
                existing.Replace(entry, date, actor.Today, clock.UtcNow, actor.UserId);
            }

            var after = Snapshot(existing);
            // The change log names the vehicle and the day, as in "Corrected revenue for KDA 482M on 28 Sep 2026".
            var which = $"for {vehicle.Registration} on {date.ToString("d MMM yyyy", CultureInfo.InvariantCulture)}";
            var reason = before is null
                ? entry.Reason is null ? $"Recorded revenue {which}" : $"Recorded no revenue {which}: {entry.DisplayReason}"
                : existing.BusinessDate < actor.Today ? $"Corrected revenue {which}" : $"Updated revenue {which}";
            await repository.RecordChange(actor, existing.Id, before, after, reason, ct);
            return new RevenueSaved(existing.Id, existing.Version);
        }, ct);

    // A refusal names the permission it needs, as People and access labels it, so the phone and the web can say so.
    private static UnauthorizedAccessException Needs(string action, string permission) =>
        new($"{action} needs the permission \"{PermissionCatalog.Groups.SelectMany(g => g.Items).Single(i => i.Key == permission).Label}\".");

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
