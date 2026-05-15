Write a public generic class named `ConcurrentLfuCache<TKey, TValue>` and a public clock abstraction named `IClock`.

Required public API:

```csharp
public interface IClock
{
    DateTimeOffset UtcNow { get; }
}

public sealed class SystemClock : IClock
{
    public DateTimeOffset UtcNow { get; }
}

public sealed class ConcurrentLfuCache<TKey, TValue> where TKey : notnull
{
    public ConcurrentLfuCache(int capacity, TimeSpan timeToLive, IClock? clock = null)
    public int Count { get; }
    public void Set(TKey key, TValue value)
    public bool TryGet(TKey key, out TValue value)
    public TValue Get(TKey key)
    public Task<TValue> GetOrLoadAsync(
        TKey key,
        Func<TKey, CancellationToken, Task<TValue>> loader,
        CancellationToken cancellationToken = default)
}
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- `capacity` must be positive and `timeToLive` must be greater than zero.
- Entries expire when the injected clock reaches or passes their expiration instant.
- Successful `TryGet`, `Get` and cache hits through `GetOrLoadAsync` increase the entry frequency and make it the most recent entry for tie breaking.
- When inserting beyond capacity, evict the entry with the lowest frequency; if multiple entries have the same frequency, evict the least recently used among them.
- `Get` must throw `KeyNotFoundException` for missing or expired keys.
- `GetOrLoadAsync` must guarantee single-flight loading per key: concurrent callers for the same missing or expired key must share one loader invocation.
- If the loader fails or is canceled, do not store a value for that key and propagate the same failure to callers.
- The cache must be safe for concurrent callers.
