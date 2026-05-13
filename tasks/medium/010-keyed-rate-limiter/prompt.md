Write a public class named `InMemoryRateLimiter`, a public interface named `IClock`, and a public immutable record or class named `RateLimitResult`.

Required public API:

```csharp
public interface IClock
{
    DateTimeOffset UtcNow { get; }
}

public InMemoryRateLimiter(int limit, TimeSpan window, IClock clock)
public RateLimitResult TryAcquire(string key)
```

`RateLimitResult` must expose `Allowed`, `Remaining` and `RetryAfter`.

Rules:
- Do not include a namespace.
- Do not use external libraries.
- All code, public identifiers, exception messages and comments must be written in English.
- Use a fixed window per key.
- Calls below or equal to the limit are allowed. Calls above the limit are blocked until the key's window resets.
- Counters are isolated by key.
- Use the injected clock only; do not call `DateTime.UtcNow` directly.
- `TryAcquire` must be safe for concurrent callers.
- Throw an argument exception for invalid constructor arguments or blank keys.
