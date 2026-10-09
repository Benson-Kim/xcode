using System.Text.Json;
using Auth.Application;
using Auth.Application.CentralExpenses;
using Auth.Application.Settings;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

public sealed class CentralExpenseRepository(AuthDb db, IUnitOfWork unitOfWork, SettingsChangeLog log) : ICentralExpenseRepository
{
    private IQueryable<FleetVehicle> VisibleVehicles(SetupActor actor) => db.Set<FleetVehicle>()
        .Where(v => actor.AllCompanies || actor.CompanyIds.Contains(v.CompanyId) || actor.VehicleIds.Contains(v.Id));

    // Central expenses and approved petty cash expenses as one UNION ALL, inside each vehicle's own days
    // (FleetVehicle.ActiveOn without away periods), exactly the days FleetPostings counts. Removed rows never appear.
    private IQueryable<LedgerStoredRow> Stored(SetupActor actor, DateOnly first, DateOnly last)
    {
        var vehicles = VisibleVehicles(actor);
        var central =
            from e in db.Set<CentralExpense>().AsNoTracking()
            join v in vehicles on e.VehicleId equals v.Id
            join i in db.Set<ExpenseItem>() on e.ExpenseItemId equals i.Id
            join c in db.Set<ExpenseCategory>() on i.CategoryId equals c.Id
            where e.RemovedAt == null && e.Date >= first && e.Date <= last && e.Date >= v.JoinedOn && (v.LeftOn == null || e.Date < v.LeftOn)
            select new LedgerStoredRow
            {
                Source = PostingSource.Central, Id = e.Id, Date = e.Date, VehicleId = e.VehicleId, Registration = v.Registration,
                ExpenseItemId = e.ExpenseItemId, ItemName = i.Name, CategoryName = c.Name, Bucket = c.Bucket, Units = e.Units,
                UnitAmount = e.UnitAmount, Total = e.Total, Note = e.Note, RecordedBy = e.RecordedBy, HolderId = (Guid?)null,
                GroupId = (Guid?)e.GroupId, GroupSize = e.GroupSize, GroupTotal = e.GroupTotal, GroupUnits = e.GroupUnits,
                GroupUnitAmount = e.GroupUnitAmount, Version = (long?)e.Version
            };
        var pettyCash =
            from e in db.Set<PettyCashEntry>().AsNoTracking()
            join v in vehicles on e.VehicleId equals (Guid?)v.Id
            join i in db.Set<ExpenseItem>() on e.ExpenseItemId equals (Guid?)i.Id
            join c in db.Set<ExpenseCategory>() on i.CategoryId equals c.Id
            where e.Kind == PettyCashKind.Expense && e.Status == PettyCashStatus.Approved && e.RemovedAt == null &&
                e.Date >= first && e.Date <= last && e.Date >= v.JoinedOn && (v.LeftOn == null || e.Date < v.LeftOn)
            select new LedgerStoredRow
            {
                Source = PostingSource.PettyCash, Id = e.Id, Date = e.Date, VehicleId = v.Id, Registration = v.Registration,
                ExpenseItemId = i.Id, ItemName = i.Name, CategoryName = c.Name, Bucket = c.Bucket, Units = e.Units,
                UnitAmount = e.UnitAmount, Total = e.Total, Note = e.Note, RecordedBy = e.RecordedBy, HolderId = (Guid?)e.HolderId,
                GroupId = (Guid?)null, GroupSize = 0, GroupTotal = 0m, GroupUnits = 0m, GroupUnitAmount = 0m, Version = (long?)null
            };
        return central.Concat(pettyCash);
    }

    private IQueryable<LedgerStoredRow> Filtered(SetupActor actor, LedgerFilter filter)
    {
        var query = Stored(actor, filter.From, filter.Through);
        if (filter.Source is { } source)
            query = query.Where(r => r.Source == source);
        if (filter.Text is { } text)
        {
            // Matching is the database's own, which is case-insensitive under the collations XCODE runs on.
            var pattern = $"%{text.Replace("[", "[[]").Replace("%", "[%]").Replace("_", "[_]")}%";
            var people = db.Memberships.Where(m => EF.Functions.Like(m.FirstName + " " + m.LastName, pattern)).Select(m => m.UserId);
            query = query.Where(r =>
                EF.Functions.Like(r.Registration, pattern) || EF.Functions.Like(r.ItemName, pattern) ||
                EF.Functions.Like(r.CategoryName, pattern) || (r.Note != null && EF.Functions.Like(r.Note, pattern)) ||
                people.Contains(r.RecordedBy) || (r.HolderId != null && people.Contains(r.HolderId.Value)));
        }
        return query;
    }

    public async Task<IReadOnlyList<LedgerDay>> StoredDays(SetupActor actor, LedgerFilter filter, CancellationToken ct) =>
        await Filtered(actor, filter)
            .GroupBy(r => r.Date)
            .Select(g => new LedgerDay(g.Key, g.Count(), g.Sum(r => r.Total)))
            .ToListAsync(ct);

    public async Task<IReadOnlyList<LedgerSourceTotal>> StoredTotals(SetupActor actor, DateOnly from, DateOnly through, CancellationToken ct) =>
        await Stored(actor, from, through)
            .GroupBy(r => r.Source)
            .Select(g => new LedgerSourceTotal(g.Key, g.Sum(r => r.Total)))
            .ToListAsync(ct);

    public async Task<IReadOnlyList<LedgerStoredRow>> StoredRows(SetupActor actor, LedgerFilter filter, int skip, int take, CancellationToken ct) =>
        await Filtered(actor, filter)
            .OrderByDescending(r => r.Date).ThenBy(r => r.Source).ThenBy(r => r.Registration).ThenBy(r => r.Id)
            .Skip(skip).Take(take)
            .ToListAsync(ct);

    public async Task<IReadOnlyList<FleetVehicle>> Vehicles(SetupActor actor, DateOnly from, DateOnly through, CancellationToken ct) =>
        await VisibleVehicles(actor).AsNoTracking()
            .Where(v => v.JoinedOn <= through && (v.LeftOn == null || v.LeftOn > from))
            .ToListAsync(ct);

    public async Task<IReadOnlyDictionary<Guid, FleetVehicle>> VehiclesById(SetupActor actor, IEnumerable<Guid> ids, CancellationToken ct)
    {
        var wanted = ids.Distinct().ToArray();
        return await VisibleVehicles(actor).AsNoTracking().Include(v => v.AwayPeriods)
            .Where(v => wanted.Contains(v.Id)).ToDictionaryAsync(v => v.Id, ct);
    }

    // Only vehicles a row may be recorded on that day (FleetVehicle.ActiveOn), which is what recording checks.
    public async Task<IReadOnlyList<VehicleOption>> VehicleOptions(SetupActor actor, DateOnly date, CancellationToken ct)
    {
        var vehicles = await VisibleVehicles(actor).AsNoTracking().Include(v => v.AwayPeriods)
            .Where(v => v.JoinedOn <= date && (v.LeftOn == null || v.LeftOn > date))
            .ToListAsync(ct);
        var companies = await db.Set<PsvCompany>().AsNoTracking().ToDictionaryAsync(c => c.Id, c => c.Name, ct);
        return [.. vehicles
            .Where(v => v.ActiveOn(date))
            .OrderBy(v => v.Registration, StringComparer.Ordinal)
            .Select(v => new VehicleOption(v.Id, v.CompanyId, companies.GetValueOrDefault(v.CompanyId, ""), v.Registration, true))];
    }

    public async Task<IReadOnlyList<CentralExpense>> Purchase(Guid id, CancellationToken ct) =>
        await db.Set<CentralExpense>().AsNoTracking().Where(e => e.GroupId == id || e.Id == id).ToListAsync(ct);

    public Task<CentralExpense?> Entry(SetupActor actor, Guid id, CancellationToken ct)
    {
        var vehicles = VisibleVehicles(actor).Select(v => v.Id);
        return db.Set<CentralExpense>()
            .Where(e => e.RemovedAt == null && vehicles.Contains(e.VehicleId))
            .SingleOrDefaultAsync(e => e.Id == id, ct);
    }

    public Task<bool> PurchaseHasVehicle(Guid groupId, Guid vehicleId, Guid except, CancellationToken ct) =>
        db.Set<CentralExpense>().AnyAsync(e => e.GroupId == groupId && e.VehicleId == vehicleId && e.Id != except, ct);

    public async Task<IReadOnlyDictionary<Guid, string>> Names(IEnumerable<Guid> userIds, CancellationToken ct)
    {
        var wanted = userIds.Distinct().ToArray();
        if (wanted.Length == 0) return new Dictionary<Guid, string>();
        return (await db.Memberships.AsNoTracking().Where(m => wanted.Contains(m.UserId))
                .Select(m => new { m.UserId, m.FirstName, m.LastName }).ToListAsync(ct))
            .ToDictionary(m => m.UserId, m => $"{m.FirstName} {m.LastName}".Trim());
    }

    public async Task<IReadOnlyDictionary<Guid, string>> ItemNames(IEnumerable<Guid> itemIds, CancellationToken ct)
    {
        var wanted = itemIds.Distinct().ToArray();
        return await db.Set<ExpenseItem>().AsNoTracking().Where(i => wanted.Contains(i.Id)).ToDictionaryAsync(i => i.Id, i => i.Name, ct);
    }

    public void Add(CentralExpense row) => db.Set<CentralExpense>().Add(row);

    // The row's vehicle goes with the change log entry, so the people who can see that vehicle see the change.
    public async Task RecordChange(SetupActor actor, CentralExpense row, object? before, object after, string reason, CancellationToken ct)
    {
        await log.Record(actor.OrganizationId, actor.UserId, actor.CorrelationId, "centralexpenses", row.Id,
            JsonSerializer.Serialize(before), JsonSerializer.Serialize(after), reason, row.VehicleId, ct);
        unitOfWork.Audit("expenses.recorded", row.Id.ToString(), before, after);
    }
}
