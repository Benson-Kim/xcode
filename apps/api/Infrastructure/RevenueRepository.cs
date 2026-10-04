using Auth.Application;
using Auth.Application.Revenue;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;
using System.Text.Json;

namespace Auth.Infrastructure;

public sealed class RevenueRepository(AuthDb db, IOrganizationRepository organizations, IUnitOfWork unitOfWork, IClock clock) : IRevenueRepository
{
    private IQueryable<FleetVehicle> VisibleVehicles(SetupActor actor) => db.Set<FleetVehicle>()
        .Where(v => actor.AllCompanies || actor.CompanyIds.Contains(v.CompanyId) || actor.VehicleIds.Contains(v.Id));

    public async Task<RevenueWeekDto> Week(SetupActor actor, DateOnly? weekStart, Guid? companyId, Guid? vehicleId, CancellationToken ct)
    {
        var firstDay = await FirstDayOfWeek(ct);
        var currentStart = StartOfWeek(actor.Today, firstDay);
        // Any day names its week, so a start saved before the first day of the week changed still lines up.
        var start = StartOfWeek(weekStart ?? actor.Today, firstDay);
        ValidateWeek(start, currentStart);
        var through = start.AddDays(6);

        var vehiclesQuery = VisibleVehicles(actor);
        if (companyId is not null)
            vehiclesQuery = vehiclesQuery.Where(v => v.CompanyId == companyId.Value);
        // The fleet grid lists vehicles active on some day of the week; a vehicle's detail shows it in any week.
        vehiclesQuery = vehicleId is null
            ? vehiclesQuery.Where(v => v.JoinedOn <= through && (v.LeftOn == null || v.LeftOn > start))
            : vehiclesQuery.Where(v => v.Id == vehicleId.Value);

        var vehicles = await vehiclesQuery
            .Include(v => v.Targets)
            .Include(v => v.AwayPeriods)
            .AsNoTracking()
            .OrderBy(v => v.Registration)
            .ToListAsync(ct);
        if (vehicleId is not null && vehicles.Count == 0 && !await VisibleVehicles(actor).AnyAsync(v => v.Id == vehicleId.Value, ct))
            throw new KeyNotFoundException();
        var ids = vehicles.Select(v => v.Id).ToArray();
        var visibleVehicles = VisibleVehicles(actor);
        var companies = await db.Set<PsvCompany>()
            .AsNoTracking()
            .Where(c => actor.AllCompanies || actor.CompanyIds.Contains(c.Id) ||
                db.Set<FleetVehicle>().Any(v => v.CompanyId == c.Id && actor.VehicleIds.Contains(v.Id)))
            // An archived company stays an option for the weeks it had a vehicle running, so past weeks still show it.
            .Where(c => c.ArchivedOn == null || c.ArchivedOn > actor.Today ||
                visibleVehicles.Any(v => v.CompanyId == c.Id && v.JoinedOn <= through && (v.LeftOn == null || v.LeftOn > start)))
            .OrderBy(c => c.Name)
            .ThenBy(c => c.Id)
            .Select(c => new RevenueCompanyOption(c.Id, c.Name))
            .ToListAsync(ct);
        var records = await db.Set<RevenueRecord>()
            .AsNoTracking()
            .Where(r => ids.Contains(r.VehicleId) && r.BusinessDate >= start && r.BusinessDate <= through)
            .ToListAsync(ct);
        var recordMap = records.ToDictionary(r => (r.VehicleId, r.BusinessDate));
        var vehicleCompanyIds = vehicles.Select(v => v.CompanyId).Distinct().ToArray();
        var companyNames = await db.Set<PsvCompany>().AsNoTracking()
            .Where(c => vehicleCompanyIds.Contains(c.Id))
            .ToDictionaryAsync(c => c.Id, c => c.Name, ct);
        var earliestMissing = await EarliestMissing(vehicles, actor.Today, ct);

        return BuildWeek(actor, start, through, currentStart, vehicles, companyNames, recordMap, earliestMissing, companies);
    }

    public async Task<RevenueDashboardDto> Dashboard(SetupActor actor, string period, Guid? companyId, CancellationToken ct)
    {
        if (period is not ("today" or "week" or "month"))
            throw new ArgumentException("Period must be today, week or month.");

        var firstDay = await FirstDayOfWeek(ct);
        var through = actor.Today;
        var from = period switch
        {
            "today" => through,
            "week" => StartOfWeek(through, firstDay),
            "month" => new DateOnly(through.Year, through.Month, 1),
            _ => through
        };

        var visible = VisibleVehicles(actor);
        // Narrows what the person already reaches; a company outside it simply matches nothing.
        if (companyId is not null) visible = visible.Where(v => v.CompanyId == companyId.Value);
        var vehicles = await visible
            .Where(v => v.JoinedOn <= through && (v.LeftOn == null || v.LeftOn > from))
            .Include(v => v.Targets)
            .Include(v => v.AwayPeriods)
            .AsNoTracking()
            .ToListAsync(ct);
        var ids = vehicles.Select(v => v.Id).ToArray();
        var records = await db.Set<RevenueRecord>().AsNoTracking()
            .Where(r => ids.Contains(r.VehicleId) && r.BusinessDate >= from && r.BusinessDate <= through)
            .ToListAsync(ct);
        var recordMap = records.ToDictionary(r => (r.VehicleId, r.BusinessDate));
        decimal revenue = 0, expected = 0;
        var missingDays = 0;
        var missingVehicles = new HashSet<Guid>();
        var capturedToday = 0;
        var edited = 0;
        var vehiclesToday = vehicles.Count(v => v.ActiveOn(actor.Today));

        foreach (var vehicle in vehicles)
        {
            var vehicleMissing = false;
            for (var date = from; date <= through; date = date.AddDays(1))
            {
                if (!vehicle.ActiveOn(date)) continue;
                var record = recordMap.GetValueOrDefault((vehicle.Id, date));
                var counted = date < actor.Today || record is not null;
                if (counted)
                {
                    expected += vehicle.TargetOn(date) / 7m;
                    if (record?.Amount is decimal amount) revenue += amount;
                }
                if (date < actor.Today && record is null)
                {
                    missingDays++;
                    vehicleMissing = true;
                }
                if (date == actor.Today && record is not null) capturedToday++;
                // Counted on the same active days as every other figure here.
                if (record?.CorrectedAfterDate == true) edited++;
            }
            if (vehicleMissing) missingVehicles.Add(vehicle.Id);
        }

        return new(period, from, through, actor.Today, decimal.Round(revenue, 2), decimal.Round(expected, 2),
            Percent(revenue, expected), capturedToday, vehiclesToday, missingDays, missingVehicles.Count, edited);
    }

    public Task<FleetVehicle?> Vehicle(SetupActor actor, Guid id, CancellationToken ct) =>
        VisibleVehicles(actor).Include(v => v.Targets).Include(v => v.AwayPeriods).SingleOrDefaultAsync(v => v.Id == id, ct);

    public Task<RevenueRecord?> Record(SetupActor actor, Guid vehicleId, DateOnly date, CancellationToken ct) =>
        VisibleVehicles(actor).Where(v => v.Id == vehicleId).SelectMany(v => db.Set<RevenueRecord>()
            .Where(r => r.VehicleId == vehicleId && r.BusinessDate == date)).SingleOrDefaultAsync(ct);

    public async Task<DateOnly?> EarliestMissing(SetupActor actor, FleetVehicle vehicle, DateOnly before, CancellationToken ct) =>
        (await EarliestMissing([vehicle], before, ct))[vehicle.Id];

    // Captures are enforced in date order, so a vehicle's records normally run unbroken from its join date. One grouped
    // query returns each vehicle's first and last recorded active day and a count (O(V) rows, not O(V*D)); only a
    // vehicle whose count shows a hole loads its own dates.
    private async Task<IReadOnlyDictionary<Guid, DateOnly?>> EarliestMissing(IReadOnlyList<FleetVehicle> vehicles, DateOnly before, CancellationToken ct)
    {
        var ids = vehicles.Select(v => v.Id).ToArray();
        var spans = await ActiveRecords(ids, before)
            .GroupBy(r => r.VehicleId)
            .Select(g => new { VehicleId = g.Key, First = g.Min(r => r.BusinessDate), Last = g.Max(r => r.BusinessDate), Count = g.Count() })
            .ToDictionaryAsync(x => x.VehicleId, ct);

        // A vehicle's active days before the date end at its leave date, or at the date itself.
        DateOnly End(FleetVehicle vehicle) => vehicle.LeftOn is { } left && left < before ? left : before;

        var result = new Dictionary<Guid, DateOnly?>();
        var holed = new List<FleetVehicle>();
        foreach (var vehicle in vehicles)
        {
            var end = End(vehicle);
            if (end <= vehicle.JoinedOn)
                result[vehicle.Id] = null;
            // A vehicle that has been away has no unbroken run of active days, so the count below would read the
            // stretch it was away as a hole. It walks its own dates instead (D4).
            else if (vehicle.AwayPeriods.Any(p => p.LeftOn < end && p.ReturnedOn > vehicle.JoinedOn))
                holed.Add(vehicle);
            else if (!spans.TryGetValue(vehicle.Id, out var span) || span.First > vehicle.JoinedOn)
                result[vehicle.Id] = vehicle.JoinedOn;
            else if (span.Count == span.Last.DayNumber - span.First.DayNumber + 1)
                result[vehicle.Id] = span.Last.AddDays(1) < end ? span.Last.AddDays(1) : null;
            else
                holed.Add(vehicle);
        }

        if (holed.Count == 0) return result;
        var dates = (await ActiveRecords(holed.Select(v => v.Id).ToArray(), before)
                .Select(r => new { r.VehicleId, r.BusinessDate })
                .ToListAsync(ct))
            .ToLookup(x => x.VehicleId, x => x.BusinessDate);
        foreach (var vehicle in holed)
        {
            var recorded = dates[vehicle.Id].ToHashSet();
            var end = End(vehicle);
            var date = vehicle.JoinedOn;
            while (date < end && (recorded.Contains(date) || !vehicle.ActiveOn(date))) date = date.AddDays(1);
            result[vehicle.Id] = date < end ? date : null;
        }
        return result;
    }

    // Records on each vehicle's active days (JoinedOn up to LeftOn) before a date.
    private IQueryable<RevenueRecord> ActiveRecords(Guid[] vehicleIds, DateOnly before) => db.Set<RevenueRecord>()
        .AsNoTracking()
        .Where(r => vehicleIds.Contains(r.VehicleId) && r.BusinessDate < before)
        .Join(db.Set<FleetVehicle>(), r => r.VehicleId, v => v.Id, (r, v) => new { Record = r, v.JoinedOn, v.LeftOn })
        .Where(x => x.Record.BusinessDate >= x.JoinedOn && (x.LeftOn == null || x.Record.BusinessDate < x.LeftOn))
        .Select(x => x.Record);

    public void Add(RevenueRecord record) => db.Set<RevenueRecord>().Add(record);

    public async Task RecordChange(SetupActor actor, Guid entityId, object? before, object after, string reason, CancellationToken ct)
    {
        var organization = await organizations.Get(ct) ?? throw new UnauthorizedAccessException();
        organization.SettingsChanged();
        db.Set<OrganizationSettingsVersion>().Add(new(
            actor.OrganizationId, actor.UserId, organization.SettingsVersion, "revenue", entityId,
            clock.UtcNow, JsonSerializer.Serialize(before), JsonSerializer.Serialize(after), reason, actor.CorrelationId));
        unitOfWork.Audit("revenue.recorded", entityId.ToString(), before, after);
    }

    private async Task<int> FirstDayOfWeek(CancellationToken ct) =>
        await db.Localizations.AsNoTracking().Select(x => (int?)x.FirstDayOfWeek).SingleOrDefaultAsync(ct) ?? 1;

    private static RevenueWeekDto BuildWeek(SetupActor actor, DateOnly start, DateOnly through, DateOnly currentStart,
        IReadOnlyList<FleetVehicle> vehicles, IReadOnlyDictionary<Guid, string> companyNames,
        IReadOnlyDictionary<(Guid VehicleId, DateOnly Date), RevenueRecord> records,
        IReadOnlyDictionary<Guid, DateOnly?> earliestMissing, IReadOnlyList<RevenueCompanyOption> companies)
    {
        var rows = new List<RevenueVehicleDto>();
        decimal totalAmount = 0, totalExpected = 0;
        foreach (var vehicle in vehicles)
        {
            var firstMissing = earliestMissing[vehicle.Id];
            var cells = new List<RevenueCellDto>();
            decimal amount = 0, expected = 0;
            for (var date = start; date <= through; date = date.AddDays(1))
            {
                var record = records.GetValueOrDefault((vehicle.Id, date));
                // Future days, days outside the fleet and today before capture are not shortfalls.
                if (vehicle.ActiveOn(date) && (date < actor.Today || record is not null))
                {
                    expected += vehicle.TargetOn(date) / 7m;
                    if (record?.Amount is decimal value) amount += value;
                }
                cells.Add(RevenueCellDto.For(actor, vehicle, date, record, firstMissing));
            }
            totalAmount += amount;
            totalExpected += expected;
            rows.Add(new(vehicle.Id, vehicle.CompanyId, companyNames.GetValueOrDefault(vehicle.CompanyId, ""),
                vehicle.Registration, vehicle.JoinedOn, vehicle.LeftOn, firstMissing, cells, decimal.Round(amount, 2),
                decimal.Round(expected, 2), Percent(amount, expected)));
        }

        return new(start, through, currentStart, actor.Today, companies, rows, decimal.Round(totalAmount, 2),
            decimal.Round(totalExpected, 2), Percent(totalAmount, totalExpected));
    }

    private static DateOnly StartOfWeek(DateOnly date, int firstDay) =>
        date.AddDays(-((int)date.DayOfWeek - firstDay + 7) % 7);

    // A tiny target against a large record can pass what an int holds; the figure stops there rather than failing
    // the whole week or dashboard.
    private static int? Percent(decimal amount, decimal expected) =>
        expected == 0 ? null : (int?)Math.Clamp(Math.Round(amount / expected * 100m, MidpointRounding.AwayFromZero), int.MinValue, int.MaxValue);

    private static void ValidateWeek(DateOnly start, DateOnly currentStart)
    {
        if (start > currentStart || start < currentStart.AddDays(-3650))
            throw new ArgumentException("Choose a week from the last ten years through the current week.");
    }
}
