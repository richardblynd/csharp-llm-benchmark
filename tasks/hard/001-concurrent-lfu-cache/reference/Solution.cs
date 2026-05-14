using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

public interface IClock
{
    DateTimeOffset UtcNow { get; }
}

public sealed class SystemClock : IClock
{
    public DateTimeOffset UtcNow => DateTimeOffset.UtcNow;
}

public sealed class ConcurrentLfuCache<TKey, TValue> where TKey : notnull
{
    private sealed class Entry
    {
        public Entry(TKey key, TValue value, DateTimeOffset expiresAt, long sequence)
        {
            Key = key;
            Value = value;
            ExpiresAt = expiresAt;
            LastUsedSequence = sequence;
            Frequency = 0;
        }

        public TKey Key { get; }
        public TValue Value { get; set; }
        public DateTimeOffset ExpiresAt { get; set; }
        public int Frequency { get; set; }
        public long LastUsedSequence { get; set; }
    }

    private readonly object gate = new();
    private readonly int capacity;
    private readonly TimeSpan timeToLive;
    private readonly IClock clock;
    private readonly Dictionary<TKey, Entry> entries = new();
    private readonly Dictionary<TKey, Task<TValue>> loads = new();
    private long sequence;

    public ConcurrentLfuCache(int capacity, TimeSpan timeToLive, IClock? clock = null)
    {
        if (capacity < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(capacity), "Capacity must be positive.");
        }

        if (timeToLive <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(timeToLive), "Time to live must be greater than zero.");
        }

        this.capacity = capacity;
        this.timeToLive = timeToLive;
        this.clock = clock ?? new SystemClock();
    }

    public int Count
    {
        get
        {
            lock (gate)
            {
                RemoveExpired();
                return entries.Count;
            }
        }
    }

    public void Set(TKey key, TValue value)
    {
        lock (gate)
        {
            SetUnderLock(key, value);
        }
    }

    public bool TryGet(TKey key, out TValue value)
    {
        lock (gate)
        {
            if (TryGetFreshEntry(key, out var entry))
            {
                Touch(entry);
                value = entry.Value;
                return true;
            }
        }

        value = default!;
        return false;
    }

    public TValue Get(TKey key)
    {
        if (TryGet(key, out var value))
        {
            return value;
        }

        throw new KeyNotFoundException("The key was not found in the cache.");
    }

    public Task<TValue> GetOrLoadAsync(
        TKey key,
        Func<TKey, CancellationToken, Task<TValue>> loader,
        CancellationToken cancellationToken = default)
    {
        if (loader is null)
        {
            throw new ArgumentNullException(nameof(loader));
        }

        lock (gate)
        {
            if (TryGetFreshEntry(key, out var entry))
            {
                Touch(entry);
                return Task.FromResult(entry.Value);
            }

            if (loads.TryGetValue(key, out var existing))
            {
                return existing.WaitAsync(cancellationToken);
            }

            var completion = new TaskCompletionSource<TValue>(TaskCreationOptions.RunContinuationsAsynchronously);
            loads[key] = completion.Task;
            _ = CompleteLoadAsync(key, loader, cancellationToken, completion);
            return completion.Task.WaitAsync(cancellationToken);
        }
    }

    private async Task CompleteLoadAsync(
        TKey key,
        Func<TKey, CancellationToken, Task<TValue>> loader,
        CancellationToken cancellationToken,
        TaskCompletionSource<TValue> completion)
    {
        try
        {
            var value = await loader(key, cancellationToken).ConfigureAwait(false);
            lock (gate)
            {
                SetUnderLock(key, value);
            }

            completion.TrySetResult(value);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            completion.TrySetCanceled(cancellationToken);
        }
        catch (Exception ex)
        {
            completion.TrySetException(ex);
        }
        finally
        {
            lock (gate)
            {
                loads.Remove(key);
            }
        }
    }

    private void SetUnderLock(TKey key, TValue value)
    {
        RemoveExpired();
        if (entries.TryGetValue(key, out var existing))
        {
            existing.Value = value;
            existing.ExpiresAt = clock.UtcNow.Add(timeToLive);
            Touch(existing);
            return;
        }

        if (entries.Count >= capacity)
        {
            var victim = entries.Values
                .OrderBy(entry => entry.Frequency)
                .ThenBy(entry => entry.LastUsedSequence)
                .First();
            entries.Remove(victim.Key);
        }

        var created = new Entry(key, value, clock.UtcNow.Add(timeToLive), ++sequence);
        entries[key] = created;
    }

    private bool TryGetFreshEntry(TKey key, out Entry entry)
    {
        if (entries.TryGetValue(key, out entry!) && entry.ExpiresAt > clock.UtcNow)
        {
            return true;
        }

        if (entry is not null)
        {
            entries.Remove(key);
        }

        return false;
    }

    private void Touch(Entry entry)
    {
        entry.Frequency++;
        entry.LastUsedSequence = ++sequence;
    }

    private void RemoveExpired()
    {
        var now = clock.UtcNow;
        foreach (var key in entries.Where(pair => pair.Value.ExpiresAt <= now).Select(pair => pair.Key).ToArray())
        {
            entries.Remove(key);
        }
    }
}
