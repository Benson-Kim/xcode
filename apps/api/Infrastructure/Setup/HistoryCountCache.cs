using Auth.Application;
using Auth.Application.Setup;
using Microsoft.Extensions.Caching.Memory;

namespace Auth.Infrastructure.Setup;

// The change log's count, kept per organization, settings version, viewer scope and filter. Every change-log row is
// written with a new settings version, so a version read before counting names one exact count; the expiry only
// bounds memory. Each replica keeps its own copy and never needs telling.
public sealed class HistoryCountCache : IDisposable
{
    private readonly MemoryCache cache = new(new MemoryCacheOptions { SizeLimit = 10_000 });

    private sealed record Key(Guid OrganizationId, long SettingsVersion, string Scope, bool SeesPeople, HistoryFilter Filter);

    public async Task<int> Count(SetupActor actor, bool seesPeople, HistoryFilter filter, Func<Task<int>> count)
    {
        if (actor.SettingsVersion is not { } version)
            return await count();

        var scope = actor.AllCompanies ? "all"
            : string.Join(",", actor.CompanyIds.Order()) + "|" + string.Join(",", actor.VehicleIds.Order());
        var key = new Key(actor.OrganizationId, version, scope, seesPeople, filter);
        Lazy<Task<int>>? mine = null;
        var shared = cache.GetOrCreate(key, entry =>
        {
            entry.Size = 1;
            entry.AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(5);
            return mine = new Lazy<Task<int>>(count);
        })!;
        try
        {
            return await shared.Value;
        }
        catch when (!ReferenceEquals(shared, mine))
        {
            // Another request's count failed or was cancelled with it; this request counts for itself.
            Forget(key, shared);
            return await count();
        }
        catch
        {
            // A failed or cancelled count is not an answer for the next caller.
            Forget(key, shared);
            throw;
        }
    }

    private void Forget(Key key, Lazy<Task<int>> failed)
    {
        if (cache.TryGetValue(key, out Lazy<Task<int>>? current) && ReferenceEquals(current, failed))
            cache.Remove(key);
    }

    public void Clear() => cache.Clear();

    public void Dispose() => cache.Dispose();
}
