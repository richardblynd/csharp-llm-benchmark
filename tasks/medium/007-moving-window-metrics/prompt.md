Write a public class named `MovingWindowAggregator` and a public immutable record or class named `MetricsSnapshot`.

Required public API:

```csharp
public MovingWindowAggregator(TimeSpan window)
public void Add(DateTime timestamp, double value)
public MetricsSnapshot GetSnapshot(DateTime now)
```

`MetricsSnapshot` must expose `Count`, `Sum`, `Min`, `Max` and `Average`.

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- The window is inclusive of events where `timestamp >= now - window` and `timestamp <= now`.
- Ignore future events when producing a snapshot for a given `now`, but keep them for later snapshots.
- Expired events should not affect count, sum, min, max or average.
- Empty snapshots have count `0` and numeric values `0`.
- Throw `ArgumentOutOfRangeException` for non-positive windows.
