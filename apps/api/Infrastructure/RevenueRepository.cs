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

    public async Task<RevenueWeekDto> Week(SetupActor actor, DateOnly? weekStart, Guid? companyId, CancellationToken ct)
    {
        var firstDay = await FirstDayOfWeek(ct);
        var currentStart = StartOfWeek(actor.Today, firstDay);
        var start = weekStart ?? currentStart;
        ValidateWeek(start, currentStart);
        var through = start.AddDays(6);

        var vehiclesQuery = VisibleVehicles(actor);
        if (companyId is not null)
            vehiclesQuery = vehiclesQuery.Where(v => v.CompanyId == companyId.Value);

        var vehicles = await vehiclesQuery
            .Include(v => v.Targets)
            .AsNoTracking()
            .OrderBy(v => v.Registration)
            .ToListAsync(ct);
        var ids = vehicles.Select(v => v.Id).ToArray();
        var companies = await db.Set<PsvCompany>()
            .AsNoTracking()
            .Where(c => actor.AllCompanies || actor.CompanyIds.Contains(c.Id) ||
                db.Set<FleetVehicle>().Any(v => v.CompanyId == c.Id && actor.VehicleIds.Contains(v.Id)))
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

        return BuildWeek(actor, start, through, currentStart, vehicles, companyNames, recordMap, companies);
    }

    public async Task<RevenueDashboardDto> Dashboard(SetupActor actor, string period, CancellationToken ct)
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

        var vehicles = await VisibleVehicles(actor)
            .Include(v => v.Targets)
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
            }
            if (vehicleMissing) missingVehicles.Add(vehicle.Id);
        }

        var edited = records.Count(r => r.CorrectedAfterDate);
        return new(period, from, through, actor.Today, decimal.Round(revenue, 2), decimal.Round(expected, 2),
            Percent(revenue, expected), capturedToday, vehiclesToday, missingDays, missingVehicles.Count, edited);
    }

    public Task<FleetVehicle?> Vehicle(SetupActor actor, Guid id, CancellationToken ct) =>
        VisibleVehicles(actor).Include(v => v.Targets).SingleOrDefaultAsync(v => v.Id == id, ct);

    public Task<RevenueRecord?> Record(SetupActor actor, Guid vehicleId, DateOnly date, CancellationToken ct) =>
        VisibleVehicles(actor).Where(v => v.Id == vehicleId).SelectMany(v => db.Set<RevenueRecord>()
            .Where(r => r.VehicleId == vehicleId && r.BusinessDate == date)).SingleOrDefaultAsync(ct);

    public async Task<DateOnly?> EarliestMissing(SetupActor actor, FleetVehicle vehicle, DateOnly before, CancellationToken ct)
    {
        if (before <= vehicle.JoinedOn) return null;
        var dates = await db.Set<RevenueRecord>()
            .AsNoTracking()
            .Where(r => r.VehicleId == vehicle.Id && r.BusinessDate >= vehicle.JoinedOn && r.BusinessDate < before)
            .Select(r => r.BusinessDate)
            .ToListAsync(ct);
        var recorded = dates.ToHashSet();
        for (var date = vehicle.JoinedOn; date < before; date = date.AddDays(1))
            if (vehicle.ActiveOn(date) && !recorded.Contains(date))
                return date;
        return null;
    }

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
        IReadOnlyList<RevenueCompanyOption> companies)
    {
        var rows = new List<RevenueVehicleDto>();
        decimal totalAmount = 0, totalExpected = 0;
        foreach (var vehicle in vehicles)
        {
            var firstMissing = FirstMissing(vehicle, actor.Today, records);
            var cells = new List<RevenueCellDto>();
            decimal amount = 0, expected = 0;
            for (var date = start; date <= through; date = date.AddDays(1))
            {
                var record = records.GetValueOrDefault((vehicle.Id, date));
                var active = vehicle.ActiveOn(date);
                var status = !active ? "none" : date > actor.Today ? "future" : record is null ? "missing" : record.Amount is not null ? "amount" : "reason";
                var dayExpected = vehicle.TargetOn(date) / 7m;
                var counted = active && (date < actor.Today || record is not null);
                if (counted)
                {
                    expected += dayExpected;
                    if (record?.Amount is decimal value) amount += value;
                }
                var canEdit = active && date <= actor.Today &&
                    (record is null ? actor.Permissions.Contains("revenue.capture") :
                        date == actor.Today ? actor.Permissions.Contains("revenue.capture") || actor.Permissions.Contains("revenue.correct") :
                        actor.Permissions.Contains("revenue.correct"));
                cells.Add(new(date, status, decimal.Round(dayExpected, 2), record?.Amount,
                    record?.Reason is null ? null : Label(record.Reason.Value), record?.Note, canEdit,
                    record?.CorrectedAfterDate == true));
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

    private static DateOnly? FirstMissing(FleetVehicle vehicle, DateOnly before, IReadOnlyDictionary<(Guid VehicleId, DateOnly Date), RevenueRecord> records)
    {
        for (var date = vehicle.JoinedOn; date < before; date = date.AddDays(1))
            if (vehicle.ActiveOn(date) && !records.ContainsKey((vehicle.Id, date)))
                return date;
        return null;
    }

    private static DateOnly StartOfWeek(DateOnly date, int firstDay) =>
        date.AddDays(-((int)date.DayOfWeek - firstDay + 7) % 7);

    private static int? Percent(decimal amount, decimal expected) =>
        expected == 0 ? null : (int?)Math.Round(amount / expected * 100m, MidpointRounding.AwayFromZero);

    private static string Label(RevenueNoEarningsReason reason) => reason switch
    {
        RevenueNoEarningsReason.Garage => "Garage",
        RevenueNoEarningsReason.Arrest => "Arrest",
        RevenueNoEarningsReason.NoCrew => "No Crew",
        RevenueNoEarningsReason.Other => "Other",
        _ => ""
    };

    private static void ValidateWeek(DateOnly start, DateOnly currentStart)
    {
        if (start > currentStart || start < currentStart.AddDays(-3650))
            throw new ArgumentException("Choose a week from the last ten years through the current week.");
    }
}
