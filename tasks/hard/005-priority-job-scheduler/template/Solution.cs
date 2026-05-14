using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

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
    public DependencyCycleException(IReadOnlyList<string> path)
    {
        Path = path;
    }

    public IReadOnlyList<string> Path { get; }
}

public sealed class PriorityJobScheduler
{
    public Task<SchedulerResult> RunAsync(
        IEnumerable<JobDefinition> jobs,
        int maxDegreeOfParallelism,
        CancellationToken cancellationToken = default)
    {
        throw new NotImplementedException();
    }
}
