using Auth.Application;
using Auth.Application.Reports;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure.Reports;

// Reads only; each is one query however many vehicles or days a report covers.
public sealed class ReportRepository(AuthDb db) : IReportRepository
{
    public async Task<IReadOnlyList<ReportVehicle>> Vehicles(SetupActor actor, Guid? companyId, CancellationToken ct)
    {
        var vehicles = db.Set<FleetVehicle>().AsNoTracking()
            .Where(v => actor.AllCompanies || actor.CompanyIds.Contains(v.CompanyId) || actor.VehicleIds.Contains(v.Id));
        if (companyId is { } company) vehicles = vehicles.Where(v => v.CompanyId == company);
        var rows = await vehicles.Include(v => v.Targets).Include(v => v.AwayPeriods).AsSplitQuery().ToListAsync(ct);
        var companyIds = rows.Select(v => v.CompanyId).Distinct().ToList();
        var names = await db.Set<PsvCompany>().AsNoTracking().Where(c => companyIds.Contains(c.Id)).ToDictionaryAsync(c => c.Id, c => c.Name, ct);
        return [.. rows.Select(v => new ReportVehicle(v, names.GetValueOrDefault(v.CompanyId, ""))).OrderBy(x => x.Registration, StringComparer.Ordinal)];
    }

    public async Task<IReadOnlyList<ReportRevenueDay>> Revenue(IReadOnlyCollection<Guid> vehicleIds, DateOnly from, DateOnly through,
        CancellationToken ct) =>
        await db.Set<RevenueRecord>().AsNoTracking()
            .Where(r => vehicleIds.Contains(r.VehicleId) && r.BusinessDate >= from && r.BusinessDate <= through)
            .Select(r => new ReportRevenueDay(r.VehicleId, r.BusinessDate, r.Amount))
            .ToListAsync(ct);

    public async Task<IReadOnlyDictionary<Guid, string>> ItemNames(IReadOnlyCollection<Guid> itemIds, CancellationToken ct) =>
        itemIds.Count == 0
            ? new Dictionary<Guid, string>()
            : await db.Set<ExpenseItem>().AsNoTracking().Where(i => itemIds.Contains(i.Id)).ToDictionaryAsync(i => i.Id, i => i.Name, ct);

    public async Task<string> OrganizationName(CancellationToken ct) =>
        await db.Brandings.AsNoTracking().Select(b => b.DisplayName).SingleOrDefaultAsync(ct) is { Length: > 0 } name ? name : "XCODE";

    // Summed here: SQLite, used in tests, cannot sum decimals in the database.
    public async Task<IReadOnlyDictionary<Guid, decimal>> Invested(IReadOnlyCollection<Guid> vehicleIds, CancellationToken ct) =>
        (await db.Set<VehicleInvestment>().AsNoTracking()
            .Where(i => vehicleIds.Contains(i.VehicleId))
            .Select(i => new { i.VehicleId, i.Amount })
            .ToListAsync(ct))
        .GroupBy(i => i.VehicleId)
        .ToDictionary(g => g.Key, g => g.Sum(i => i.Amount));
}
