Write a public static class named `ParallelExecutor`.

Required public API:

```csharp
public static Task<IReadOnlyList<TResult>> ExecuteAsync<TInput, TResult>(
    IReadOnlyList<TInput> inputs,
    Func<TInput, CancellationToken, Task<TResult>> work,
    int maxConcurrency,
    CancellationToken cancellationToken = default)
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- Execute at most `maxConcurrency` operations at the same time.
- Preserve input order in the returned results.
- Propagate exceptions from `work`.
- Respect cancellation before starting new work and while waiting for concurrency slots.
- Return an empty list for an empty input.
- Throw an argument exception for null inputs, null work or `maxConcurrency < 1`.
