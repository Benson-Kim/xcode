using System.Text.Json;
using Auth.Application;
using Auth.Application.Setup;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure.Setup;

public sealed class SetupRepository(AuthDb db, IOrganizationRepository organizations, IUnitOfWork unitOfWork, IClock clock) : ISetupRepository
{
    private IQueryable<FleetVehicle> VisibleVehicles(SetupActor actor) => db
        .Set<FleetVehicle>()
        .Where(v => actor.AllCompanies || actor.CompanyIds.Contains(v.CompanyId) || actor.VehicleIds.Contains(v.Id));

    private IQueryable<PsvCompany> VisibleCompanies(SetupActor actor) => db
        .Set<PsvCompany>()
        .Where(c => actor.AllCompanies || actor.CompanyIds.Contains(c.Id) ||
                VisibleVehicles(actor).Any(v => v.CompanyId == c.Id));

    private IQueryable<RecurringItem> VisibleRecurring(SetupActor actor) => db
        .Set<RecurringItem>()
        .Where(i => actor.AllCompanies || i.Versions.Any(v => v.Allocations.Any(a => VisibleVehicles(actor).Any(vehicle => vehicle.Id == a.VehicleId))));

    public async Task<Page<CompanyDto>> Companies(SetupActor actor, int page, int pageSize, CancellationToken ct)
    {
        var query = VisibleCompanies(actor).AsNoTracking();
        var total = await query.CountAsync(ct);
        var items = await query
            .OrderBy(c => c.Name)
            .ThenBy(c => c.Id)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .Select(c => new CompanyDto(c.Id, c.Name,
                VisibleVehicles(actor).Count(v => v.CompanyId == c.Id && (v.LeftOn == null || v.LeftOn > actor.Today)),
                c.ArchivedOn == null || c.ArchivedOn > actor.Today, c.ArchivedOn))
            .ToListAsync(ct);
        return new(items, page, pageSize, total);
    }

    public Task<PsvCompany?> Company(SetupActor actor, Guid id, CancellationToken ct) =>
        VisibleCompanies(actor).SingleOrDefaultAsync(c => c.Id == id, ct);

    public async Task<IReadOnlyList<CompanyOption>> CompanyOptions(SetupActor actor, CancellationToken ct) =>
        await VisibleCompanies(actor)
            .AsNoTracking()
            .Where(c => c.ArchivedOn == null || c.ArchivedOn > actor.Today)
            .OrderBy(c => c.Name)
            .ThenBy(c => c.Id)
            .Select(c => new CompanyOption(c.Id, c.Name))
            .ToListAsync(ct);

    public Task<bool> HasActiveVehicles(Guid companyId, DateOnly today, CancellationToken ct) =>
        db.Set<FleetVehicle>().AnyAsync(v => v.CompanyId == companyId && (v.LeftOn == null || v.LeftOn > today), ct);

    public Task<bool> CompanyNameExists(Guid organizationId, string normalizedName, Guid? except, CancellationToken ct)
        => db
        .Set<PsvCompany>()
        .AnyAsync(c => c.OrganizationId == organizationId && c.NormalizedName == normalizedName && c.Id != except, ct);

    public async Task<Page<VehicleDto>> Vehicles(SetupActor actor, int page, int pageSize, CancellationToken ct)
    {
        var query = VisibleVehicles(actor).AsNoTracking();
        var total = await query.CountAsync(ct);
        var rows = await query
            .OrderBy(v => v.Registration)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .Select(v => new
            {
                v.Id,
                v.CompanyId,
                CompanyName = db.Set<PsvCompany>().Where(c => c.Id == v.CompanyId).Select(c => c.Name).First(),
                v.Registration,
                v.JoinedOn,
                v.LeftOn,
                Targets = v.Targets.OrderBy(t => t.Revision).Select(t => new TargetDto(t.EffectiveFrom, t.WeeklyAmount, t.Revision)).ToList()
            })
            .ToListAsync(ct);

        var vehicleIds = rows.Select(v => v.Id).ToList();
        var activeVehicleIds = rows.Where(v => v.LeftOn is null || v.LeftOn > actor.Today).Select(v => v.Id).ToHashSet();
        // Items still posting to each active vehicle: the current version allocates to it and has not ended or stopped.
        var current = await db.Set<RecurringVersion>().AsNoTracking()
            .Where(v => !db.Set<RecurringVersion>().Any(other => other.ItemId == v.ItemId && other.Revision > v.Revision)
                && v.Allocations.Any(a => vehicleIds.Contains(a.VehicleId)))
            .Select(v => new
            {
                v.ItemId,
                v.End,
                StoppedFrom = db.Set<RecurringItem>().Where(i => i.Id == v.ItemId).Select(i => i.StoppedFrom).First(),
                Vehicles = v.Allocations.Select(a => a.VehicleId).ToList()
            })
            .ToListAsync(ct);
        var recurringItems = current
            .Where(v => (v.End == null || v.End >= actor.Today) && (v.StoppedFrom == null || v.StoppedFrom > actor.Today))
            .SelectMany(v => v.Vehicles.Where(activeVehicleIds.Contains).Select(vehicleId => (v.ItemId, VehicleId: vehicleId)))
            .GroupBy(x => x.VehicleId)
            .ToDictionary(g => g.Key, g => g.Select(x => x.ItemId).Distinct().Count());

        return new(rows.Select(v =>
        {
            var active = v.LeftOn is null || v.LeftOn > actor.Today;
            var currentTarget = active
                ? v.Targets.Where(t => t.EffectiveFrom <= (actor.Today < v.JoinedOn ? v.JoinedOn : actor.Today))
                    .OrderByDescending(t => t.EffectiveFrom)
                    .ThenByDescending(t => t.Revision)
                    .Select(t => t.WeeklyAmount)
                    .FirstOrDefault()
                : 0m;
            return new VehicleDto(v.Id, v.CompanyId, v.CompanyName, v.Registration, v.JoinedOn, v.LeftOn, active,
                currentTarget, v.Targets, recurringItems.GetValueOrDefault(v.Id));
        }).ToList(), page, pageSize, total);
    }

    public Task<FleetVehicle?> Vehicle(SetupActor actor, Guid id, CancellationToken ct) => VisibleVehicles(actor)
        .Include(v => v.Targets)
        .SingleOrDefaultAsync(v => v.Id == id, ct);

    public Task<bool> RegistrationExists(Guid organizationId, string registration, CancellationToken ct)
        => db
        .Set<FleetVehicle>()
        .AnyAsync(v => v.OrganizationId == organizationId && v.Registration == registration, ct);

    public async Task<IReadOnlyList<VehicleOption>> VehicleOptions(SetupActor actor, CancellationToken ct) => await VisibleVehicles(actor)
        .AsNoTracking()
        .Where(v => (v.LeftOn == null || v.LeftOn > actor.Today) &&
            db.Set<PsvCompany>().Any(c => c.Id == v.CompanyId && (c.ArchivedOn == null || c.ArchivedOn > actor.Today)))
        .OrderBy(v => v.Registration)
        .Select(v => new VehicleOption(v.Id, v.CompanyId, db.Set<PsvCompany>().Where(c => c.Id == v.CompanyId).Select(c => c.Name).First(), v.Registration, true))
        .ToListAsync(ct);

    public async Task<int> FirstDayOfWeek(CancellationToken ct) =>
        await db.Localizations.AsNoTracking().Select(x => (int?)x.FirstDayOfWeek).SingleOrDefaultAsync(ct) ?? 1;

    public async Task<Page<RecurringDto>> Recurring(SetupActor actor, int page, int pageSize, CancellationToken ct)
    {
        var query = VisibleRecurring(actor).AsNoTracking();
        var total = await query.CountAsync(ct);
        // Pages follow the current name, so page two continues where page one stopped.
        var ids = await query
            .OrderBy(i => i.Versions.OrderByDescending(v => v.Revision).Select(v => v.Name).FirstOrDefault())
            .ThenBy(i => i.Id)
            .Skip((page - 1) * pageSize).Take(pageSize).Select(i => i.Id).ToListAsync(ct);
        var visibleIds = VisibleVehicles(actor).Select(v => v.Id);
        // Project the editor's shares, including retired vehicles so their history remains inspectable.
        var rows = await db.Set<RecurringVersion>().AsNoTracking().Where(v => ids.Contains(v.ItemId) && !db
            .Set<RecurringVersion>()
            .Any(other => other.ItemId == v.ItemId && other.Revision > v.Revision))
            .Select(v => new
            {
                v.ItemId,
                v.Id,
                v.Revision,
                v.Name,
                v.Kind,
                v.Category,
                v.Frequency,
                v.Day,
                v.LastDay,
                v.Start,
                v.End,
                StoppedFrom = db.Set<RecurringItem>().Where(i => i.Id == v.ItemId).Select(i => i.StoppedFrom).First(),
                Allocations = v.Allocations.Where(a => visibleIds.Contains(a.VehicleId)).Select(a => new
                {
                    a.VehicleId,
                    a.Amount,
                    Registration = db.Set<FleetVehicle>().Where(vehicle => vehicle.Id == a.VehicleId).Select(vehicle => vehicle.Registration).FirstOrDefault(),
                    Active = db.Set<FleetVehicle>().Where(vehicle => vehicle.Id == a.VehicleId)
                        .Select(vehicle => vehicle.LeftOn == null || vehicle.LeftOn > actor.Today).FirstOrDefault()
                }).ToList(),
                AllocationCount = v.Allocations.Count()
            }).ToListAsync(ct);
        rows = [.. rows.OrderBy(v => ids.IndexOf(v.ItemId))];
        return new(rows.Select(v =>
        {
            var allocations = v.Allocations.Select(a => new AllocationDto(a.VehicleId, a.Amount, a.Registration, a.Active)).ToList();
            return new RecurringDto(v.ItemId, v.Id, v.Revision, v.Name, v.Kind, v.Category,
                allocations.Where(a => a.Active).Sum(a => a.Amount), v.Frequency, v.Day, v.LastDay, v.Start, v.End, v.StoppedFrom,
                allocations, v.Allocations.Count != v.AllocationCount);
        }).ToList(), page, pageSize, total);
    }

    public Task<RecurringItem?> RecurringItem(SetupActor actor, Guid id, CancellationToken ct)
        => VisibleRecurring(actor).Include(i => i.Versions).ThenInclude(v => v.Allocations).SingleOrDefaultAsync(i => i.Id == id, ct);

    public async Task<VehicleReport> Report(SetupActor actor, Guid vehicleId, DateOnly from, DateOnly through, CancellationToken ct)
    {
        // A bounded, deterministic projection of immutable schedule versions: due dates post automatically,
        // without hard deletes or a request-path mutation. A materialized ledger can consume this same rule.
        var items = await db.Set<RecurringItem>().AsNoTracking()
            .Where(i => i.Versions.Any(v => v.Allocations.Any(a => a.VehicleId == vehicleId)))
            .Include(i => i.Versions).ThenInclude(v => v.Allocations).ToListAsync(ct);
        var vehicle = await VisibleVehicles(actor).Where(v => v.Id == vehicleId)
            .Select(v => new { v.JoinedOn, v.LeftOn }).SingleAsync(ct);
        var postings = new List<PostingDto>();

        for (var day = from; day <= through; day = day.AddDays(1))
        {
            if (day < vehicle.JoinedOn || vehicle.LeftOn is not null && day >= vehicle.LeftOn) continue;
            foreach (var item in items)
            {
                var version = item.DueOn(day);
                var share = version?.Allocations.SingleOrDefault(a => a.VehicleId == vehicleId);
                if (version is not null && share is not null) postings.Add(new(item.Id, version.Id, day, version.Name, version.Kind, version.Category, share.Amount));
            }
        }
        return new(vehicleId, from, through, postings.Where(p => p.Kind == RecurringKind.Cost).Sum(p => p.Amount),
            postings.Where(p => p.Kind == RecurringKind.Savings).Sum(p => p.Amount), postings);
    }

    public async Task<Page<HistoryEntry>> History(SetupActor actor, int page, int pageSize, CancellationToken ct)
    {
        var vehicles = VisibleVehicles(actor).Select(v => v.Id);
        var companies = VisibleCompanies(actor).Select(c => c.Id);
        var completeItems = db.Set<RecurringItem>().Where(i => !i.Versions.Any(v => v.Allocations.Any(a => !vehicles.Contains(a.VehicleId)))).Select(i => i.Id);
        var query = db.Set<OrganizationSettingsVersion>().AsNoTracking().Where(v => actor.AllCompanies ||
            (v.Section == "companies" && companies.Contains(v.EntityId)) || (v.Section == "vehicles" && vehicles.Contains(v.EntityId)) ||
            (v.Section == "recurring" && completeItems.Contains(v.EntityId)));
        var entries = await query.OrderByDescending(v => v.Version).Skip((page - 1) * pageSize).Take(pageSize)
            .Select(v => new HistoryEntry(v.Version, v.Section, v.EntityId, v.Reason, v.OccurredAt, v.ActorId,
                db.Memberships.Where(m => m.UserId == v.ActorId).Select(m => m.FirstName + " " + m.LastName).FirstOrDefault() ?? "",
                v.Before, v.After))
            .ToListAsync(ct);
        return new(entries, page, pageSize, await query.CountAsync(ct));
    }

    public void Add(PsvCompany company) => db.Set<PsvCompany>().Add(company);

    public void Add(FleetVehicle vehicle) => db.Set<FleetVehicle>().Add(vehicle);

    public void Add(RecurringItem item) => db.Set<RecurringItem>().Add(item);

    public async Task RecordChange(SetupActor actor, string section, Guid entityId, object? before, object after, string reason, CancellationToken ct)
    {
        var organization = await organizations.Get(ct) ?? throw new UnauthorizedAccessException();
        organization.SettingsChanged();
        db.Set<OrganizationSettingsVersion>()
            .Add(new(actor.OrganizationId, actor.UserId, organization.SettingsVersion, section, entityId,
            clock.UtcNow, JsonSerializer.Serialize(before), JsonSerializer.Serialize(after), reason, actor.CorrelationId));
        unitOfWork.Audit("setup." + section, entityId.ToString(), before, after);
    }
}
