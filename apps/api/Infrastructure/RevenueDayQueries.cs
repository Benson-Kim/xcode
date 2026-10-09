using Auth.Application;
using Auth.Application.Revenue;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

// Capture revenue for one day: the vehicles active that day with their records, and the loads a day's save needs.
public sealed partial class RevenueRepository
{
    public async Task<RevenueDayDto> Day(SetupActor actor, DateOnly date, Guid? companyId, CancellationToken ct)
    {
        var source = VisibleVehicles(actor).Where(v => v.JoinedOn <= date && (v.LeftOn == null || v.LeftOn > date));
        if (companyId is not null)
            source = source.Where(v => v.CompanyId == companyId.Value);
        // Away periods are a per-date lookup, so the loaded rows are filtered for them.
        var active = (await source
                .Include(v => v.Targets.Where(t => t.EffectiveFrom <= date))
                .Include(v => v.AwayPeriods.Where(p => p.LeftOn <= date && date < p.ReturnedOn))
                .AsSplitQuery()
                .AsNoTracking()
                .OrderBy(v => v.Registration)
                .ThenBy(v => v.Id)
                .ToListAsync(ct))
            .Where(v => v.ActiveOn(date))
            .ToList();
        var shown = active.Take(RevenueDayDto.Limit).ToList();

        var ids = shown.Select(v => v.Id).ToArray();
        var lastWeek = date.AddDays(-7);
        var records = await db.Set<RevenueRecord>()
            .AsNoTracking()
            .Where(r => ids.Contains(r.VehicleId) && (r.BusinessDate == date || r.BusinessDate == lastWeek))
            .Select(r => new RevenueDayRecord(r.VehicleId, r.BusinessDate, r.Amount, r.Reason, r.Note, r.CorrectedAfterDate, r.Version))
            .ToDictionaryAsync(r => (r.VehicleId, r.BusinessDate), ct);

        var rows = shown.Select(vehicle =>
        {
            var before = records.GetValueOrDefault((vehicle.Id, lastWeek));
            return new RevenueDayVehicleDto(vehicle.Id, vehicle.CompanyId, vehicle.Registration,
                RevenueCellDto.For(actor, vehicle, date, vehicle.TargetOn(date), records.GetValueOrDefault((vehicle.Id, date))),
                before is null ? null : new RevenueLastWeekDto(before.Amount, before.Reason is null ? null : RevenueEntry.Label(before.Reason)));
        }).ToList();
        return new(date, actor.Today, rows, active.Count > shown.Count);
    }

    public async Task<IReadOnlyList<FleetVehicle>> Vehicles(SetupActor actor, Guid[] ids, CancellationToken ct) =>
        await VisibleVehicles(actor)
            .Where(v => ids.Contains(v.Id))
            .Include(v => v.Targets)
            .Include(v => v.AwayPeriods)
            .AsSplitQuery()
            .ToListAsync(ct);

    public async Task<IReadOnlyList<RevenueRecord>> Records(SetupActor actor, Guid[] vehicleIds, DateOnly date, CancellationToken ct) =>
        await VisibleVehicles(actor)
            .Where(v => vehicleIds.Contains(v.Id))
            .SelectMany(v => db.Set<RevenueRecord>().Where(r => r.VehicleId == v.Id && r.BusinessDate == date))
            .ToListAsync(ct);
}
