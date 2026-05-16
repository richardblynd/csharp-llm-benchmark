Write a versioned interval index.

Required public API:

```csharp
public sealed record Interval<T>(int Start, int End, T Value, long Sequence);

public sealed class InvalidIntervalException : Exception
{
    public int Start { get; }
    public int End { get; }
}

public sealed class VersionedIntervalIndex<T>
{
    public int CurrentVersion { get; }
    public int Add(int start, int end, T value)
    public IReadOnlyList<Interval<T>> Query(int start, int end)
    public IReadOnlyList<Interval<T>> QueryVersion(int version, int start, int end)
}
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- Intervals are half-open ranges: `[Start, End)`.
- A query intersects an interval when `interval.Start < queryEnd` and `queryStart < interval.End`.
- Adjacent ranges such as `[0, 10)` and `[10, 20)` do not intersect.
- Version `0` is the empty index. Each successful `Add` creates and returns the next version.
- Queries without an explicit version use `CurrentVersion`.
- Previous versions must remain observable and unchanged after later inserts.
- Invalid intervals have `start >= end` and must throw `InvalidIntervalException` without changing `CurrentVersion`.
- Invalid query ranges also throw `InvalidIntervalException`.
- Invalid version numbers throw `ArgumentOutOfRangeException`.
- Query results must be deterministic: sort by `Start`, then `End`, then insertion `Sequence`.
- `Sequence` starts at `1` for the first successful insert and increases by one for each successful insert.
