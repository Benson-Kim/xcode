using System.Text.Json;
using Auth.Application;
using Auth.Application.PettyCash;
using Auth.Application.Settings;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

public sealed class PettyCashRepository(AuthDb db, IUnitOfWork unitOfWork, SettingsChangeLog log) : IPettyCashRepository
{
    private IQueryable<FleetVehicle> VisibleVehicles(SetupActor actor) => db.Set<FleetVehicle>()
        .Where(v => actor.AllCompanies || actor.CompanyIds.Contains(v.CompanyId) || actor.VehicleIds.Contains(v.Id));

    // A person's own float whole; with "View every float", everyone else's too, except spending on vehicles outside
    // their data scope. Removed entries are never shown.
    private IQueryable<PettyCashEntry> Visible(SetupActor actor)
    {
        var everyFloat = actor.Permissions.Contains(PermissionKeys.PettyCashViewAll);
        var vehicles = VisibleVehicles(actor).Select(v => v.Id);
        return db.Set<PettyCashEntry>().Where(e => e.RemovedAt == null &&
            (e.HolderId == actor.UserId || (everyFloat && (e.VehicleId == null || vehicles.Contains(e.VehicleId.Value)))));
    }

    public async Task<IReadOnlyList<PettyCashHolderDto>> Holders(CancellationToken ct)
    {
        var members = await db.Memberships.AsNoTracking()
            .Select(m => new { m.UserId, m.FirstName, m.LastName, m.Active }).ToListAsync(ct);
        var roles = (await db.PersonRoles.AsNoTracking()
                .Join(db.Roles, link => link.RoleId, role => role.Id, (link, role) => new { link.UserId, role.Name })
                .ToListAsync(ct))
            .ToLookup(x => x.UserId, x => x.Name);
        var overrides = (await db.PermissionOverrides.AsNoTracking().ToListAsync(ct)).ToLookup(x => x.UserId);
        var withEntries = (await db.Set<PettyCashEntry>().AsNoTracking().Where(e => e.RemovedAt == null)
            .Select(e => e.HolderId).Distinct().ToListAsync(ct)).ToHashSet();
        var resolver = new EffectivePermissionResolver();
        return members
            .Select(m => (Member: m, Spends: resolver
                .Resolve(roles[m.UserId].SelectMany(PermissionCatalog.DefaultsFor), overrides[m.UserId], m.Active)
                .Contains(PermissionKeys.PettyCashSpend)))
            .Where(x => x.Spends || withEntries.Contains(x.Member.UserId))
            .Select(x => new PettyCashHolderDto(x.Member.UserId, Name(x.Member.FirstName, x.Member.LastName), x.Spends))
            .OrderBy(h => h.Name, StringComparer.OrdinalIgnoreCase)
            .ThenBy(h => h.Id)
            .ToList();
    }

    public Task<decimal?> ApprovalLimit(Guid userId, CancellationToken ct) =>
        db.Memberships.AsNoTracking().Where(m => m.UserId == userId).Select(m => m.ApprovalLimit).SingleOrDefaultAsync(ct);

    public async Task<IReadOnlyList<PettyCashTally>> Tallies(SetupActor actor, IReadOnlyCollection<Guid> holderIds, DateOnly from,
        DateOnly through, CancellationToken ct) =>
        await Visible(actor).AsNoTracking()
            .Where(e => holderIds.Contains(e.HolderId))
            .GroupBy(e => new
            {
                e.HolderId,
                e.Kind,
                e.Status,
                Period = e.Date < from ? PettyCashTally.Before : e.Date > through ? PettyCashTally.After : PettyCashTally.Within
            })
            .Select(g => new PettyCashTally(g.Key.HolderId, g.Key.Kind, g.Key.Status, g.Key.Period, g.Sum(e => e.Total), g.Count(), g.Max(e => e.Date)))
            .ToListAsync(ct);

    public async Task<decimal> Balance(Guid holderId, CancellationToken ct)
    {
        var sums = await db.Set<PettyCashEntry>().AsNoTracking()
            .Where(e => e.RemovedAt == null && e.HolderId == holderId)
            .GroupBy(e => e.Kind)
            .Select(g => new { Kind = g.Key, Total = g.Sum(e => e.Total) })
            .ToListAsync(ct);
        return sums.Sum(s => s.Kind == PettyCashKind.Cash ? s.Total : -s.Total);
    }

    public async Task<Page<PettyCashEntryRow>> Entries(SetupActor actor, IReadOnlyCollection<Guid> holderIds, PettyCashFilter filter, int page,
        int pageSize, CancellationToken ct)
    {
        var query = Visible(actor).AsNoTracking().Where(e => holderIds.Contains(e.HolderId));
        if (filter.From is { } from) query = query.Where(e => e.Date >= from);
        if (filter.To is { } to) query = query.Where(e => e.Date <= to);
        if (filter.Kinds.Count > 0) query = query.Where(e => filter.Kinds.Contains(e.Kind));
        if (filter.Status is { } status) query = query.Where(e => e.Status == status);
        if (filter.Text is { } text)
        {
            // The vehicle, the item, the payee, the note or the person: what a row shows. Matching is the database's
            // own, which is case-insensitive under the collations XCODE runs on.
            var pattern = $"%{text.Replace("[", "[[]").Replace("%", "[%]").Replace("_", "[_]")}%";
            var people = db.Memberships.Where(m => EF.Functions.Like(m.FirstName + " " + m.LastName, pattern)).Select(m => m.UserId);
            var vehicles = db.Set<FleetVehicle>().Where(v => EF.Functions.Like(v.Registration, pattern)).Select(v => v.Id);
            var items = db.Set<ExpenseItem>().Where(i => EF.Functions.Like(i.Name, pattern)).Select(i => i.Id);
            query = query.Where(e =>
                (e.Note != null && EF.Functions.Like(e.Note, pattern)) ||
                (e.Payee != null && EF.Functions.Like(e.Payee, pattern)) ||
                people.Contains(e.HolderId) ||
                (e.VehicleId != null && vehicles.Contains(e.VehicleId.Value)) ||
                (e.ExpenseItemId != null && items.Contains(e.ExpenseItemId.Value)));
        }

        var total = await query.CountAsync(ct);
        var entries = await query
            .OrderBy(e => e.Date)
            .ThenBy(e => e.Kind)
            .ThenBy(e => e.Id)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync(ct);
        return new Page<PettyCashEntryRow>(await Rows(entries, ct), page, pageSize, total);
    }

    public async Task<PettyCashEntryRow?> Row(SetupActor actor, Guid id, CancellationToken ct)
    {
        var entry = await Visible(actor).AsNoTracking().SingleOrDefaultAsync(e => e.Id == id, ct);
        return entry is null ? null : (await Rows([entry], ct))[0];
    }

    public Task<PettyCashEntry?> Entry(SetupActor actor, Guid id, CancellationToken ct) =>
        Visible(actor).SingleOrDefaultAsync(e => e.Id == id, ct);

    public Task<PettyCashEntry?> AnyEntry(Guid id, CancellationToken ct) =>
        db.Set<PettyCashEntry>().SingleOrDefaultAsync(e => e.Id == id, ct);

    public async Task<IReadOnlyList<PettyCashEntry>> Waiting(SetupActor actor, IReadOnlyCollection<Guid> holderIds, DateOnly? date, bool track,
        CancellationToken ct)
    {
        var query = Visible(actor).Where(e => e.Status == PettyCashStatus.Waiting && holderIds.Contains(e.HolderId));
        if (date is { } day) query = query.Where(e => e.Date == day);
        if (!track) query = query.AsNoTracking();
        return await query.OrderBy(e => e.Date).ThenBy(e => e.Id).ToListAsync(ct);
    }

    public Task<FleetVehicle?> Vehicle(SetupActor actor, Guid id, CancellationToken ct) =>
        VisibleVehicles(actor).AsNoTracking().Include(v => v.AwayPeriods).SingleOrDefaultAsync(v => v.Id == id, ct);

    public async Task<IReadOnlyDictionary<Guid, string>> Names(IEnumerable<Guid> userIds, CancellationToken ct)
    {
        var wanted = userIds.Distinct().ToArray();
        return (await db.Memberships.AsNoTracking().Where(m => wanted.Contains(m.UserId))
                .Select(m => new { m.UserId, m.FirstName, m.LastName }).ToListAsync(ct))
            .ToDictionary(m => m.UserId, m => Name(m.FirstName, m.LastName));
    }

    public async Task<IReadOnlyDictionary<Guid, string>> Registrations(IEnumerable<Guid> vehicleIds, CancellationToken ct)
    {
        var wanted = vehicleIds.Distinct().ToArray();
        if (wanted.Length == 0) return new Dictionary<Guid, string>();
        return await db.Set<FleetVehicle>().AsNoTracking().Where(v => wanted.Contains(v.Id)).ToDictionaryAsync(v => v.Id, v => v.Registration, ct);
    }

    public void Add(PettyCashEntry entry) => db.Set<PettyCashEntry>().Add(entry);

    // An expense's line carries its vehicle, so the change log shows it to the people who can see that vehicle.
    public async Task RecordChange(SetupActor actor, PettyCashEntry entry, object? before, object after, string reason, CancellationToken ct)
    {
        await log.Record(actor.OrganizationId, actor.UserId, actor.CorrelationId, "pettycash", entry.Id,
            JsonSerializer.Serialize(before), JsonSerializer.Serialize(after), reason, entry.VehicleId, ct);
        unitOfWork.Audit("pettycash.recorded", entry.Id.ToString(), before, after);
    }

    // The names and labels a page of rows shows, read once for the whole page.
    private async Task<IReadOnlyList<PettyCashEntryRow>> Rows(IReadOnlyList<PettyCashEntry> entries, CancellationToken ct)
    {
        if (entries.Count == 0) return [];
        var names = await Names(entries.SelectMany(e => new[] { e.HolderId, e.RecordedBy, e.ReviewedBy ?? e.HolderId }), ct);
        var registrations = await Registrations(entries.Where(e => e.VehicleId is not null).Select(e => e.VehicleId!.Value), ct);
        var itemIds = entries.Where(e => e.ExpenseItemId is not null).Select(e => e.ExpenseItemId!.Value).Distinct().ToArray();
        var items = itemIds.Length == 0
            ? new Dictionary<Guid, (string Name, ExpenseBucket Bucket)>()
            : (await db.Set<ExpenseItem>().AsNoTracking()
                    .Where(i => itemIds.Contains(i.Id))
                    .Join(db.Set<ExpenseCategory>(), i => i.CategoryId, c => c.Id, (i, c) => new { i.Id, i.Name, c.Bucket })
                    .ToListAsync(ct))
                .ToDictionary(x => x.Id, x => (x.Name, x.Bucket));

        return [.. entries.Select(e =>
        {
            var item = e.ExpenseItemId is { } itemId && items.TryGetValue(itemId, out var found) ? found : ((string Name, ExpenseBucket Bucket)?)null;
            return new PettyCashEntryRow(e, names.GetValueOrDefault(e.HolderId, ""),
                e.VehicleId is { } vehicleId ? registrations.GetValueOrDefault(vehicleId) : null,
                item?.Name, item?.Bucket,
                e.ReviewedBy is { } reviewer ? names.GetValueOrDefault(reviewer) : null,
                names.GetValueOrDefault(e.RecordedBy, ""));
        })];
    }

    private static string Name(string first, string last) => $"{first} {last}".Trim();
}
