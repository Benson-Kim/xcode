using System.Security.Cryptography;
using System.Text;
using Auth.Application.Revenue;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.Extensions.Caching.Memory;

namespace Auth.Infrastructure;

// Dashboard figures kept per organization, settings version, business date, period, company filter and data scope.
// Every write that changes a figure's inputs (revenue, a vehicle's dates, targets, company or time away, the business
// date, the first day of the week) adds a change-log row and so moves the settings version, which each request reads
// before any figures. An entry is therefore never older than the version it is filed under, and the expiry only bounds
// memory. Each replica keeps its own copy and never needs telling. The figures are kept unmasked: what each person may
// see of them is applied per request, after this.
public sealed class RevenueDashboardCache : IDisposable
{
    private static readonly TimeSpan Lifetime = TimeSpan.FromSeconds(60);
    private readonly MemoryCache cache = new(new MemoryCacheOptions { SizeLimit = 10_000 });
    private readonly Lock gate = new();

    private sealed record Key(Guid OrganizationId, long SettingsVersion, DateOnly Today, string Period, Guid? CompanyId, string Scope);

    // The first request for a key works the figures out in its own scope; requests for the same key meanwhile wait for
    // that one computation.
    public async Task<RevenueDashboardDto> Get(SetupActor actor, string period, Guid? companyId,
        Func<Task<RevenueDashboardDto>> compute, CancellationToken ct)
    {
        if (actor.SettingsVersion is not { } version)
            return await compute();

        var key = new Key(actor.OrganizationId, version, actor.Today, period, companyId, Scope(actor));
        Task<RevenueDashboardDto>? shared;
        TaskCompletionSource<RevenueDashboardDto>? mine = null;
        lock (gate)
        {
            if (!cache.TryGetValue(key, out shared) || shared is null)
            {
                mine = new(TaskCreationOptions.RunContinuationsAsynchronously);
                shared = mine.Task;
                cache.Set(key, shared, new MemoryCacheEntryOptions { Size = 1, AbsoluteExpirationRelativeToNow = Lifetime });
            }
        }

        if (mine is null)
        {
            try
            {
                return await shared.WaitAsync(ct);
            }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested)
            {
                // The computation this request waited for failed or was cancelled; it works the figures out itself.
                return await compute();
            }
        }

        try
        {
            var figures = await compute();
            mine.SetResult(figures);
            return figures;
        }
        catch
        {
            // A failed or cancelled computation is not an answer for the next request.
            lock (gate)
            {
                if (cache.TryGetValue(key, out Task<RevenueDashboardDto>? current) && ReferenceEquals(current, shared))
                    cache.Remove(key);
            }
            mine.SetCanceled();
            throw;
        }
    }

    // Everyone who reaches every company shares one entry; anyone narrower shares only with the same companies and vehicles.
    private static string Scope(SetupActor actor)
    {
        if (actor.AllCompanies) return "all";
        var scope = string.Join(",", actor.CompanyIds.Order()) + "|" + string.Join(",", actor.VehicleIds.Order());
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(scope)));
    }

    public void Dispose() => cache.Dispose();
}

// The repository with its dashboard figures served from RevenueDashboardCache; everything else passes straight through.
public sealed class CachedRevenueRepository(RevenueRepository inner, RevenueDashboardCache cache) : IRevenueRepository
{
    public Task<RevenueWeekDto> Week(SetupActor actor, DateOnly? weekStart, Guid? companyId, Guid? vehicleId, RevenueWeekPage? page,
        CancellationToken ct) => inner.Week(actor, weekStart, companyId, vehicleId, page, ct);

    public Task<RevenueDashboardDto> Dashboard(SetupActor actor, string period, Guid? companyId, CancellationToken ct) =>
        cache.Get(actor, period, companyId, () => inner.Dashboard(actor, period, companyId, ct), ct);

    public Task<FleetVehicle?> Vehicle(SetupActor actor, Guid id, CancellationToken ct) => inner.Vehicle(actor, id, ct);

    public Task<RevenueRecord?> Record(SetupActor actor, Guid vehicleId, DateOnly date, CancellationToken ct) =>
        inner.Record(actor, vehicleId, date, ct);

    public Task<DateOnly?> EarliestMissing(SetupActor actor, FleetVehicle vehicle, DateOnly before, CancellationToken ct) =>
        inner.EarliestMissing(actor, vehicle, before, ct);

    public void Add(RevenueRecord record) => inner.Add(record);

    public Task RecordChange(SetupActor actor, Guid entityId, object? before, object after, string reason, CancellationToken ct) =>
        inner.RecordChange(actor, entityId, before, after, reason, ct);
}
