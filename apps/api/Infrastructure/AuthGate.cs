using System.Collections.Concurrent;

namespace Auth.Infrastructure;

// Per-user locking: serializes auth for the same account while unrelated users proceed concurrently.
// Capped at MaxEntries to prevent memory exhaustion from attackers probing many phone numbers.
public sealed class AuthGate
{
    private const int MaxEntries = 10_000;
    private readonly ConcurrentDictionary<string, Entry> locks = new();

    private sealed class Entry
    {
        public SemaphoreSlim Semaphore { get; } = new(1, 1);
        public long LastUsedTicks = Environment.TickCount64;
    }

    public SemaphoreSlim For(string key)
    {
        var entry = locks.GetOrAdd(key, _ => new Entry());
        entry.LastUsedTicks = Environment.TickCount64;

        if (locks.Count > MaxEntries)
            Evict();

        return entry.Semaphore;
    }

    private void Evict()
    {
        var target = (int)(MaxEntries * 0.8);
        var candidates = locks
            .Where(kv => kv.Value.Semaphore.CurrentCount > 0)
            .OrderBy(kv => kv.Value.LastUsedTicks)
            .ToList();

        foreach (var kv in candidates)
        {
            if (locks.Count <= target) break;
            locks.TryRemove(kv);
        }
    }
}
