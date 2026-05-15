Write a public static class named `ResilientProcessor` and a public immutable record or class named `ProcessingResult<T>`.

Required public API:

```csharp
public static Task<IReadOnlyList<ProcessingResult<TResult>>> ProcessAsync<TInput, TResult>(
    IReadOnlyList<TInput> inputs,
    Func<TInput, CancellationToken, Task<TResult>> process,
    int maxAttempts,
    CancellationToken cancellationToken = default)
```

`ProcessingResult<T>` must expose:

```csharp
public bool Succeeded { get; }
public T? Value { get; }
public Exception? Error { get; }
public int Attempts { get; }
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- Process items in input order and return results in input order.
- Retry a failed item until it succeeds or reaches `maxAttempts`.
- A final failure should be represented in `ProcessingResult<T>` instead of stopping the whole batch.
- Do not retry after success and do not exceed `maxAttempts`.
- Respect `CancellationToken` by propagating cancellation.
- Throw an argument exception for null inputs, null process or `maxAttempts < 1`.
