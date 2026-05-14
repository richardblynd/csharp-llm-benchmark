using System;
using System.Collections.Generic;
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
    public ConcurrentLfuCache(int capacity, TimeSpan timeToLive, IClock? clock = null)
    {
        throw new NotImplementedException();
    }

    public int Count => throw new NotImplementedException();

    public void Set(TKey key, TValue value)
    {
        throw new NotImplementedException();
    }

    public bool TryGet(TKey key, out TValue value)
    {
        throw new NotImplementedException();
    }

    public TValue Get(TKey key)
    {
        throw new NotImplementedException();
    }

    public Task<TValue> GetOrLoadAsync(
        TKey key,
        Func<TKey, CancellationToken, Task<TValue>> loader,
        CancellationToken cancellationToken = default)
    {
        throw new NotImplementedException();
    }
}
