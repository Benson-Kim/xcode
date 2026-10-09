using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure.Setup;

// Three reads however many postings there are, plus one for the categories of scheduled items that name an expense
// item. Each is a projection of what a posting shows, so no entity is tracked.
public sealed class FleetPostings(AuthDb db) : IFleetPostings
{
    private static Dictionary<Guid, (DateOnly First, DateOnly Last)> Windows(SetupActor actor, IReadOnlyCollection<FleetVehicle> vehicles,
        DateOnly from, DateOnly through)
    {
        var windows = new Dictionary<Guid, (DateOnly First, DateOnly Last)>();
        foreach (var vehicle in vehicles)
        {
            var first = from < vehicle.JoinedOn ? vehicle.JoinedOn : from;
            var last = through < actor.Today ? through : actor.Today;
            if (vehicle.LeftOn is { } left && left <= last) last = left.AddDays(-1);
            if (first <= last) windows[vehicle.Id] = (first, last);
        }
        return windows;
    }

    public async Task<IReadOnlyList<FleetPosting>> Scheduled(SetupActor actor, IReadOnlyCollection<FleetVehicle> vehicles, DateOnly from,
        DateOnly through, CancellationToken ct) =>
        await Scheduled(Windows(actor, vehicles, from, through), ct);

    public async Task<IReadOnlyList<FleetPosting>> Load(SetupActor actor, IReadOnlyCollection<FleetVehicle> vehicles, DateOnly from,
        DateOnly through, CancellationToken ct)
    {
        var windows = Windows(actor, vehicles, from, through);
        if (windows.Count == 0) return [];

        var ids = windows.Keys.ToList();
        var low = windows.Values.Min(w => w.First);
        var high = windows.Values.Max(w => w.Last);
        bool Inside(Guid vehicleId, DateOnly date) =>
            windows.TryGetValue(vehicleId, out var window) && date >= window.First && date <= window.Last;

        var postings = new List<FleetPosting>();

        var central = await (
                from e in db.Set<CentralExpense>().AsNoTracking()
                join i in db.Set<ExpenseItem>() on e.ExpenseItemId equals i.Id
                join c in db.Set<ExpenseCategory>() on i.CategoryId equals c.Id
                where e.RemovedAt == null && ids.Contains(e.VehicleId) && e.Date >= low && e.Date <= high
                select new
                {
                    e.Id, e.Date, e.VehicleId, e.ExpenseItemId, ItemName = i.Name, CategoryName = c.Name, c.Bucket, e.Units, e.UnitAmount,
                    e.Total, e.Note, e.RecordedBy, e.GroupId, e.GroupSize, e.GroupTotal, e.GroupUnits, e.GroupUnitAmount, e.Version
                })
            .ToListAsync(ct);
        postings.AddRange(central.Where(e => Inside(e.VehicleId, e.Date)).Select(e => new FleetPosting(PostingSource.Central,
            RecurringKind.Cost, e.Date, e.VehicleId, e.Id, null, e.ItemName, e.ExpenseItemId, e.CategoryName, e.Bucket, e.Units, e.UnitAmount,
            e.Total, e.Note, e.RecordedBy, null, new PostingGroup(e.GroupId, e.GroupSize, e.GroupTotal, e.GroupUnits, e.GroupUnitAmount),
            e.Version)));

        var pettyCash = await (
                from e in db.Set<PettyCashEntry>().AsNoTracking()
                join i in db.Set<ExpenseItem>() on e.ExpenseItemId equals i.Id
                join c in db.Set<ExpenseCategory>() on i.CategoryId equals c.Id
                where e.Kind == PettyCashKind.Expense && e.Status == PettyCashStatus.Approved && e.RemovedAt == null &&
                    e.VehicleId != null && ids.Contains(e.VehicleId.Value) && e.Date >= low && e.Date <= high
                select new
                {
                    e.Id, e.Date, VehicleId = e.VehicleId!.Value, e.ExpenseItemId, ItemName = i.Name, CategoryName = c.Name, c.Bucket,
                    e.Units, e.UnitAmount, e.Total, e.Note, e.RecordedBy, e.HolderId
                })
            .ToListAsync(ct);
        postings.AddRange(pettyCash.Where(e => Inside(e.VehicleId, e.Date)).Select(e => new FleetPosting(PostingSource.PettyCash,
            RecurringKind.Cost, e.Date, e.VehicleId, e.Id, null, e.ItemName, e.ExpenseItemId, e.CategoryName, e.Bucket, e.Units, e.UnitAmount,
            e.Total, e.Note, e.RecordedBy, e.HolderId, null, null)));

        postings.AddRange(await Scheduled(windows, ct));
        return postings;
    }

    // One row per version however many vehicles an item is shared with: only the shares asked for are loaded, and
    // each version's due dates are stepped (RecurringItem.DueBetween).
    private async Task<List<FleetPosting>> Scheduled(Dictionary<Guid, (DateOnly First, DateOnly Last)> windows, CancellationToken ct)
    {
        if (windows.Count == 0) return [];
        var ids = windows.Keys.ToList();
        var low = windows.Values.Min(w => w.First);
        var high = windows.Values.Max(w => w.Last);
        bool Inside(Guid vehicleId, DateOnly date) =>
            windows.TryGetValue(vehicleId, out var window) && date >= window.First && date <= window.Last;

        var items = await db.Set<RecurringItem>().AsNoTracking()
            .Where(i => i.Versions.Any(v => v.Allocations.Any(a => ids.Contains(a.VehicleId))))
            .Include(i => i.Versions).ThenInclude(v => v.Allocations.Where(a => ids.Contains(a.VehicleId)))
            .ToListAsync(ct);
        var scheduled = items
            .SelectMany(item => item.DueBetween(low, high).SelectMany(due => due.Version.Allocations
                .Where(share => Inside(share.VehicleId, due.Date))
                .Select(share => (Item: item, due.Date, due.Version, Share: share))))
            .ToList();
        var itemIds = scheduled.Where(x => x.Version.ExpenseItemId is not null).Select(x => x.Version.ExpenseItemId!.Value).Distinct().ToList();
        var categories = itemIds.Count == 0
            ? new Dictionary<Guid, string>()
            : await (from i in db.Set<ExpenseItem>().AsNoTracking()
                    join c in db.Set<ExpenseCategory>() on i.CategoryId equals c.Id
                    where itemIds.Contains(i.Id)
                    select new { i.Id, c.Name })
                .ToDictionaryAsync(x => x.Id, x => x.Name, ct);
        return [.. scheduled.Select(x => new FleetPosting(PostingSource.Scheduled, x.Version.Kind, x.Date, x.Share.VehicleId, x.Item.Id,
            x.Version.Id, x.Version.Name, x.Version.ExpenseItemId,
            x.Version.ExpenseItemId is { } itemId ? categories.GetValueOrDefault(itemId) : null, x.Version.ReportedBucket(), 1, x.Share.Amount,
            x.Share.Amount, x.Version.Note, null, null, null, null))];
    }
}
