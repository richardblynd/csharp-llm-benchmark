Write a priority job scheduler with dependencies.

Required public API:

```csharp
public sealed record JobDefinition(
    string Id,
    int Priority,
    Func<CancellationToken, Task> Work,
    IReadOnlyCollection<string>? Dependencies = null,
    int MaxAttempts = 1);

public enum JobStatus
{
    Succeeded,
    Failed,
    Skipped,
    Canceled
}

public sealed record JobResult(string Id, JobStatus Status, int Attempts, Exception? Error);
public sealed record SchedulerResult(IReadOnlyList<JobResult> Jobs);

public sealed class DependencyCycleException : Exception
{
    public IReadOnlyList<string> Path { get; }
}

public sealed class PriorityJobScheduler
{
    public Task<SchedulerResult> RunAsync(
        IEnumerable<JobDefinition> jobs,
        int maxDegreeOfParallelism,
        CancellationToken cancellationToken = default)
}
```

Rules:
- Do not include a namespace.
- Do not use external libraries.
- All code, public identifiers, exception messages and comments must be written in English.
- Job ids must be non-empty and unique.
- `maxDegreeOfParallelism` and `MaxAttempts` must be positive.
- A job may start only after all dependencies have succeeded.
- Among currently ready jobs, start higher priority first, then ordinal id order.
- At no point may more than `maxDegreeOfParallelism` jobs run at once.
- Retry a failed job until it succeeds or reaches `MaxAttempts`; do not retry after success.
- If a job ultimately fails, mark all jobs that depend on it directly or transitively as `Skipped`.
- If cancellation is requested, stop starting new jobs and mark unfinished jobs as `Canceled`.
- Detect dependency cycles before running any job and throw `DependencyCycleException` with a diagnostic path.
