using Auth.Application;
using Auth.Application.Revenue;
using Auth.Application.Settings;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;
using System.Text.Json;

namespace Auth.Infrastructure;

public sealed class RevenueRepository(AuthDb db, IUnitOfWork unitOfWork, SettingsChangeLog log) : IRevenueRepository
{
    private IQueryable<FleetVehicle> VisibleVehicles(SetupActor actor) => db.Set<FleetVehicle>()
        .Where(v => actor.AllCompanies || actor.CompanyIds.Contains(v.CompanyId) || actor.VehicleIds.Contains(v.Id));

    public async Task<RevenueWeekDto> Week(SetupActor actor, DateOnly? weekStart, Guid? companyId, Guid? vehicleId, RevenueWeekPage? page,
        CancellationToken ct)
    {
        var firstDay = await FirstDayOfWeek(ct);
        var currentStart = StartOfWeek(actor.Today, firstDay);
        // Any day names its week, so a start saved before the first day of the week changed still lines up.
        var start = StartOfWeek(weekStart ?? actor.Today, firstDay);
        ValidateWeek(start, currentStart);
        var through = start.AddDays(6);

        var grid = VisibleVehicles(actor);
        if (companyId is not null)
            grid = grid.Where(v => v.CompanyId == companyId.Value);
        // The fleet grid lists vehicles active on some day of the week; a vehicle's detail shows it in any week.
        grid = vehicleId is null
            ? grid.Where(v => v.JoinedOn <= through && (v.LeftOn == null || v.LeftOn > start))
            : grid.Where(v => v.Id == vehicleId.Value);

        // Every vehicle in the grid, not just the page: the week's figures and its first gap cover them all. A target
        // set after the week cannot apply to it. Away periods stay whole, because the earliest missing day reads the
        // vehicle's whole history. Split queries keep targets and away periods from multiplying each other's rows.
        var vehicles = await grid
            .Include(v => v.Targets.Where(t => t.EffectiveFrom <= through))
            .Include(v => v.AwayPeriods)
            .AsSplitQuery()
            .AsNoTracking()
            .OrderBy(v => v.Registration)
            .ThenBy(v => v.Id)
            .ToListAsync(ct);
        if (vehicleId is not null && vehicles.Count == 0 && !await VisibleVehicles(actor).AnyAsync(v => v.Id == vehicleId.Value, ct))
            throw new KeyNotFoundException();
        var listed = page ?? RevenueWeekPage.Legacy;
        var shown = vehicles.Skip((listed.Number - 1) * listed.Size).Take(listed.Size).ToList();
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
        // The cells of the listed vehicles only, with just the columns a cell shows.
        var shownIds = shown.Select(v => v.Id).ToArray();
        var records = await db.Set<RevenueRecord>()
            .AsNoTracking()
            .Where(r => shownIds.Contains(r.VehicleId) && r.BusinessDate >= start && r.BusinessDate <= through)
            .Select(r => new RevenueDayRecord(r.VehicleId, r.BusinessDate, r.Amount, r.Reason, r.Note, r.CorrectedAfterDate, r.Version))
            .ToDictionaryAsync(r => (r.VehicleId, r.BusinessDate), ct);
        // The whole grid's records, summed by day. A day before today counts whatever was recorded on it, so its sum is
        // enough; from today on a vehicle's day counts only once it has a record, so those days stay per vehicle.
        var today = actor.Today;
        var tally = await ActiveDayRecords(grid, start, through)
            .GroupBy(r => new { r.BusinessDate, VehicleId = r.BusinessDate < today ? (Guid?)null : r.VehicleId })
            .Select(g => new WeekTally(g.Key.BusinessDate, g.Key.VehicleId, g.Sum(r => r.Amount)))
            .ToListAsync(ct);
        var shownCompanyIds = shown.Select(v => v.CompanyId).Distinct().ToArray();
        var companyNames = await db.Set<PsvCompany>().AsNoTracking()
            .Where(c => shownCompanyIds.Contains(c.Id))
            .ToDictionaryAsync(c => c.Id, c => c.Name, ct);
        var earliestMissing = await EarliestMissing(vehicles, grid, actor.Today, ct);

        return BuildWeek(actor, start, currentStart, vehicles, shown, page, companyNames, records, tally, earliestMissing, companies);
    }

    // Recorded amounts on one day of the week grid: every vehicle's together before today, one vehicle's from today on.
    private sealed record WeekTally(DateOnly Date, Guid? VehicleId, decimal? Amount);

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
        var fleet = visible.Where(v => v.JoinedOn <= through && (v.LeftOn == null || v.LeftOn > from));
        // Each vehicle's calendar for the window: the targets that can apply to it and the away periods that overlap it.
        var vehicles = await fleet
            .Include(v => v.Targets.Where(t => t.EffectiveFrom <= through))
            .Include(v => v.AwayPeriods.Where(p => p.LeftOn <= through && p.ReturnedOn > from))
            .AsSplitQuery()
            .AsNoTracking()
            .ToListAsync(ct);
        // The database sums each vehicle's records on its active days: one row per vehicle, however many days the
        // period holds.
        var tallies = await ActiveDayRecords(fleet, from, through)
            .GroupBy(r => r.VehicleId)
            .Select(g => new
            {
                VehicleId = g.Key,
                Revenue = g.Sum(r => r.Amount),
                RecordedBefore = g.Count(r => r.BusinessDate < through),
                RecordedToday = g.Count(r => r.BusinessDate == through),
                Edited = g.Count(r => r.CorrectedAfterDate)
            })
            .ToDictionaryAsync(x => x.VehicleId, ct);

        decimal revenue = 0, expected = 0;
        int missingDays = 0, missingVehicles = 0, capturedToday = 0, vehiclesToday = 0, edited = 0;
        foreach (var vehicle in vehicles)
        {
            var tally = tallies.GetValueOrDefault(vehicle.Id);
            var activeBefore = 0;
            // Every active day before today counts toward the target; today counts once it has a record.
            for (var date = from; date < through; date = date.AddDays(1))
            {
                if (!vehicle.ActiveOn(date)) continue;
                activeBefore++;
                expected += vehicle.TargetOn(date) / 7m;
            }
            if (vehicle.ActiveOn(through))
            {
                vehiclesToday++;
                if (tally?.RecordedToday > 0) expected += vehicle.TargetOn(through) / 7m;
            }
            var missing = activeBefore - (tally?.RecordedBefore ?? 0);
            missingDays += missing;
            if (missing > 0) missingVehicles++;
            revenue += tally?.Revenue ?? 0;
            capturedToday += tally?.RecordedToday ?? 0;
            edited += tally?.Edited ?? 0;
        }

        return new(period, from, through, actor.Today, decimal.Round(revenue, 2), decimal.Round(expected, 2),
            Percent(revenue, expected), capturedToday, vehiclesToday, missingDays, missingVehicles, edited);
    }

    public Task<FleetVehicle?> Vehicle(SetupActor actor, Guid id, CancellationToken ct) =>
        VisibleVehicles(actor).Include(v => v.Targets).Include(v => v.AwayPeriods).SingleOrDefaultAsync(v => v.Id == id, ct);

    public Task<RevenueRecord?> Record(SetupActor actor, Guid vehicleId, DateOnly date, CancellationToken ct) =>
        VisibleVehicles(actor).Where(v => v.Id == vehicleId).SelectMany(v => db.Set<RevenueRecord>()
            .Where(r => r.VehicleId == vehicleId && r.BusinessDate == date)).SingleOrDefaultAsync(ct);

    public async Task<DateOnly?> EarliestMissing(SetupActor actor, FleetVehicle vehicle, DateOnly before, CancellationToken ct) =>
        (await EarliestMissing([vehicle], db.Set<FleetVehicle>().Where(v => v.Id == vehicle.Id), before, ct))[vehicle.Id];

    // Captures are enforced in date order, so a vehicle's records normally run unbroken from its join date. One grouped
    // query returns each vehicle's first and last recorded active day and a count (O(V) rows, not O(V*D)); only a
    // vehicle whose count shows a hole loads its own dates. The vehicles must carry their whole history of away periods,
    // and source is the query they were loaded from, which the records are joined to.
    private async Task<IReadOnlyDictionary<Guid, DateOnly?>> EarliestMissing(IReadOnlyList<FleetVehicle> vehicles,
        IQueryable<FleetVehicle> source, DateOnly before, CancellationToken ct)
    {
        var spans = await ActiveRecords(source, before)
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
        var holedIds = holed.Select(v => v.Id).ToArray();
        var dates = (await ActiveRecords(source.Where(v => holedIds.Contains(v.Id)), before)
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
    private IQueryable<RevenueRecord> ActiveRecords(IQueryable<FleetVehicle> vehicles, DateOnly before) => db.Set<RevenueRecord>()
        .AsNoTracking()
        .Where(r => r.BusinessDate < before)
        .Join(vehicles, r => r.VehicleId, v => v.Id, (r, v) => new { Record = r, v.JoinedOn, v.LeftOn })
        .Where(x => x.Record.BusinessDate >= x.JoinedOn && (x.LeftOn == null || x.Record.BusinessDate < x.LeftOn))
        .Select(x => x.Record);

    // Records from one date through another on each vehicle's active days, as FleetVehicle.ActiveOn reads them: joined,
    // not yet left and not away.
    private IQueryable<RevenueRecord> ActiveDayRecords(IQueryable<FleetVehicle> vehicles, DateOnly from, DateOnly through) =>
        db.Set<RevenueRecord>()
            .AsNoTracking()
            .Where(r => r.BusinessDate >= from && r.BusinessDate <= through)
            .Join(vehicles, r => r.VehicleId, v => v.Id, (r, v) => new { Record = r, v.JoinedOn, v.LeftOn })
            .Where(x => x.Record.BusinessDate >= x.JoinedOn && (x.LeftOn == null || x.Record.BusinessDate < x.LeftOn))
            .Where(x => !db.Set<VehicleAwayPeriod>().Any(p =>
                p.VehicleId == x.Record.VehicleId && p.LeftOn <= x.Record.BusinessDate && x.Record.BusinessDate < p.ReturnedOn))
            .Select(x => x.Record);

    public void Add(RevenueRecord record) => db.Set<RevenueRecord>().Add(record);

    public async Task RecordChange(SetupActor actor, Guid entityId, object? before, object after, string reason, CancellationToken ct)
    {
        // The record being logged was just added or loaded for this save, so it is tracked.
        var vehicleId = db.Set<RevenueRecord>().Local.Single(r => r.Id == entityId).VehicleId;
        await log.Record(actor.OrganizationId, actor.UserId, actor.CorrelationId, "revenue", entityId,
            JsonSerializer.Serialize(before), JsonSerializer.Serialize(after), reason, vehicleId, ct);
        unitOfWork.Audit("revenue.recorded", entityId.ToString(), before, after);
    }

    private async Task<int> FirstDayOfWeek(CancellationToken ct) =>
        await db.Localizations.AsNoTracking().Select(x => (int?)x.FirstDayOfWeek).SingleOrDefaultAsync(ct) ?? 1;

    // The week's figures (totals, day totals and first gap) cover every vehicle in the grid, from the vehicles' calendars
    // and the tally; only the listed vehicles get rows, from their own records. Totals are summed unrounded and rounded once.
    private static RevenueWeekDto BuildWeek(SetupActor actor, DateOnly start, DateOnly currentStart,
        IReadOnlyList<FleetVehicle> vehicles, IReadOnlyList<FleetVehicle> shown, RevenueWeekPage? page,
        IReadOnlyDictionary<Guid, string> companyNames, IReadOnlyDictionary<(Guid VehicleId, DateOnly Date), RevenueDayRecord> records,
        IReadOnlyList<WeekTally> tally, IReadOnlyDictionary<Guid, DateOnly?> earliestMissing, IReadOnlyList<RevenueCompanyOption> companies)
    {
        var today = actor.Today;
        var through = start.AddDays(6);
        // Future days, days outside the fleet and today before capture are not shortfalls.
        bool Counts(FleetVehicle vehicle, DateOnly date, bool recorded) => vehicle.ActiveOn(date) && (date < today || recorded);

        var dayAmounts = new decimal[7];
        var dayExpected = new decimal[7];
        decimal totalAmount = 0, totalExpected = 0;
        var recordedFromToday = new HashSet<(Guid VehicleId, DateOnly Date)>();
        foreach (var day in tally)
        {
            totalAmount += day.Amount ?? 0;
            // A day's total is what its cells show as amounts, and a day after today shows none.
            if (day.Date <= today) dayAmounts[day.Date.DayNumber - start.DayNumber] += day.Amount ?? 0;
            if (day.VehicleId is { } vehicleId) recordedFromToday.Add((vehicleId, day.Date));
        }

        RevenueGapDto? firstGap = null;
        foreach (var vehicle in vehicles)
        {
            for (var day = 0; day < 7; day++)
            {
                var date = start.AddDays(day);
                if (!Counts(vehicle, date, recordedFromToday.Contains((vehicle.Id, date)))) continue;
                var expected = vehicle.TargetOn(date) / 7m;
                dayExpected[day] += expected;
                totalExpected += expected;
            }
            // The first day the vehicle can be captured: its earliest gap, or today while today has no record. The
            // earliest such day wins, and on a tie the vehicle that comes first in the grid.
            var todayMissing = today >= start && today <= through && vehicle.ActiveOn(today) && !recordedFromToday.Contains((vehicle.Id, today));
            if ((earliestMissing[vehicle.Id] ?? (todayMissing ? today : null)) is { } opens && (firstGap is null || opens < firstGap.Date))
                firstGap = new(vehicle.Id, opens);
        }

        var rows = new List<RevenueVehicleDto>(shown.Count);
        foreach (var vehicle in shown)
        {
            var firstMissing = earliestMissing[vehicle.Id];
            var cells = new List<RevenueCellDto>(7);
            decimal amount = 0, expected = 0;
            for (var day = 0; day < 7; day++)
            {
                var date = start.AddDays(day);
                var record = records.GetValueOrDefault((vehicle.Id, date));
                var target = vehicle.TargetOn(date);
                if (Counts(vehicle, date, record is not null))
                {
                    expected += target / 7m;
                    if (record?.Amount is decimal value) amount += value;
                }
                cells.Add(RevenueCellDto.For(actor, vehicle, date, target, record, firstMissing));
            }
            rows.Add(new(vehicle.Id, vehicle.CompanyId, companyNames.GetValueOrDefault(vehicle.CompanyId, ""),
                vehicle.Registration, vehicle.JoinedOn, vehicle.LeftOn, firstMissing, cells, decimal.Round(amount, 2),
                decimal.Round(expected, 2), Percent(amount, expected)));
        }

        var listed = page ?? RevenueWeekPage.Legacy;
        var dayTotals = Enumerable.Range(0, 7)
            .Select(day => new RevenueDayTotalDto(start.AddDays(day), decimal.Round(dayAmounts[day], 2), decimal.Round(dayExpected[day], 2)))
            .ToArray();
        return new(start, through, currentStart, today, companies, rows, decimal.Round(totalAmount, 2),
            decimal.Round(totalExpected, 2), Percent(totalAmount, totalExpected), listed.Number, listed.Size, vehicles.Count,
            page is null && vehicles.Count > listed.Size, dayTotals, firstGap);
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
