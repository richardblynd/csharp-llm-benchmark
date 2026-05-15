Write a public generic class named `LruCache<TKey, TValue>`.

Required public API:

```csharp
public LruCache(int capacity)
public int Count { get; }
public bool TryGet(TKey key, out TValue value)
public TValue Get(TKey key)
public void Put(TKey key, TValue value)
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- The cache has a fixed positive capacity. Throw `ArgumentOutOfRangeException` for capacities less than `1`.
- `Put` inserts or updates a value. Updating an existing key must not increase `Count`.
- When inserting past capacity, evict the least recently used key.
- Successful `TryGet` and `Get` calls must make the key most recently used.
- `Get` must throw `KeyNotFoundException` when the key is missing.
