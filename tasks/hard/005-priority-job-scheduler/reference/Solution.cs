using System;
using System.Collections.Generic;
using System.Linq;
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
        : base("The job graph contains a dependency cycle.")
    {
        Path = path;
    }

    public IReadOnlyList<string> Path { get; }
}

public sealed class PriorityJobScheduler
{
    public async Task<SchedulerResult> RunAsync(
        IEnumerable<JobDefinition> jobs,
        int maxDegreeOfParallelism,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(jobs);
        if (maxDegreeOfParallelism < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(maxDegreeOfParallelism), "Max degree of parallelism must be positive.");
        }

        var definitions = NormalizeJobs(jobs);
        var dependencies = definitions.ToDictionary(
            pair => pair.Key,
            pair => new HashSet<string>(pair.Value.Dependencies ?? Array.Empty<string>(), StringComparer.Ordinal),
            StringComparer.Ordinal);
        ValidateDependencies(definitions, dependencies);
        ThrowIfCyclic(definitions, dependencies);

        var dependents = BuildDependents(definitions, dependencies);
        var results = new Dictionary<string, JobResult>(StringComparer.Ordinal);
        var ready = new HashSet<string>(dependencies.Where(pair => pair.Value.Count == 0).Select(pair => pair.Key), StringComparer.Ordinal);
        var active = new List<(string Id, Task<JobResult> Task)>();

        while (results.Count + active.Count < definitions.Count)
        {
            if (cancellationToken.IsCancellationRequested)
            {
                break;
            }

            while (active.Count < maxDegreeOfParallelism && ready.Count > 0 && !cancellationToken.IsCancellationRequested)
            {
                var next = ready
                    .OrderByDescending(id => definitions[id].Priority)
                    .ThenBy(id => id, StringComparer.Ordinal)
                    .First();
                ready.Remove(next);
                active.Add((next, ExecuteJobAsync(definitions[next], cancellationToken)));
            }

            if (active.Count == 0)
            {
                break;
            }

            var completedTask = await Task.WhenAny(active.Select(item => item.Task)).ConfigureAwait(false);
            var completed = active.Single(item => item.Task == completedTask);
            active.Remove(completed);
            var result = await completedTask.ConfigureAwait(false);
            results[result.Id] = result;
            ReleaseDependents(result.Id, definitions, dependencies, dependents, results, ready);
        }

        if (active.Count > 0)
        {
            var completedResults = await Task.WhenAll(active.Select(item => item.Task)).ConfigureAwait(false);
            foreach (var result in completedResults)
            {
                results[result.Id] = result;
            }
        }

        if (cancellationToken.IsCancellationRequested)
        {
            foreach (var id in definitions.Keys.Where(id => !results.ContainsKey(id)).ToArray())
            {
                results[id] = new JobResult(id, JobStatus.Canceled, 0, null);
            }
        }

        foreach (var id in definitions.Keys.Where(id => !results.ContainsKey(id)).ToArray())
        {
            results[id] = new JobResult(id, JobStatus.Skipped, 0, null);
        }

        return new SchedulerResult(results.Values.OrderBy(result => result.Id, StringComparer.Ordinal).ToArray());
    }

    private static async Task<JobResult> ExecuteJobAsync(JobDefinition job, CancellationToken cancellationToken)
    {
        var attempts = 0;
        Exception? lastError = null;
        for (var attempt = 1; attempt <= job.MaxAttempts; attempt++)
        {
            attempts = attempt;
            try
            {
                cancellationToken.ThrowIfCancellationRequested();
                await job.Work(cancellationToken).ConfigureAwait(false);
                return new JobResult(job.Id, JobStatus.Succeeded, attempts, null);
            }
            catch (OperationCanceledException ex) when (cancellationToken.IsCancellationRequested)
            {
                return new JobResult(job.Id, JobStatus.Canceled, attempts, ex);
            }
            catch (Exception ex)
            {
                lastError = ex;
            }
        }

        return new JobResult(job.Id, JobStatus.Failed, attempts, lastError);
    }

    private static Dictionary<string, JobDefinition> NormalizeJobs(IEnumerable<JobDefinition> jobs)
    {
        var definitions = new Dictionary<string, JobDefinition>(StringComparer.Ordinal);
        foreach (var job in jobs)
        {
            ArgumentNullException.ThrowIfNull(job);
            if (string.IsNullOrWhiteSpace(job.Id))
            {
                throw new ArgumentException("Job ids must be non-empty.", nameof(jobs));
            }

            if (job.Work is null)
            {
                throw new ArgumentException("Job work is required.", nameof(jobs));
            }

            if (job.MaxAttempts < 1)
            {
                throw new ArgumentOutOfRangeException(nameof(jobs), "Max attempts must be positive.");
            }

            if (!definitions.TryAdd(job.Id.Trim(), job with { Id = job.Id.Trim() }))
            {
                throw new ArgumentException("Job ids must be unique.", nameof(jobs));
            }
        }

        return definitions;
    }

    private static void ValidateDependencies(
        IReadOnlyDictionary<string, JobDefinition> definitions,
        IReadOnlyDictionary<string, HashSet<string>> dependencies)
    {
        foreach (var (id, set) in dependencies)
        {
            foreach (var dependency in set)
            {
                if (!definitions.ContainsKey(dependency))
                {
                    throw new ArgumentException($"Job '{id}' depends on missing job '{dependency}'.", nameof(dependencies));
                }
            }
        }
    }

    private static Dictionary<string, HashSet<string>> BuildDependents(
        IReadOnlyDictionary<string, JobDefinition> definitions,
        IReadOnlyDictionary<string, HashSet<string>> dependencies)
    {
        var dependents = definitions.Keys.ToDictionary(id => id, _ => new HashSet<string>(StringComparer.Ordinal), StringComparer.Ordinal);
        foreach (var (id, set) in dependencies)
        {
            foreach (var dependency in set)
            {
                dependents[dependency].Add(id);
            }
        }

        return dependents;
    }

    private static void ReleaseDependents(
        string completedId,
        IReadOnlyDictionary<string, JobDefinition> definitions,
        IReadOnlyDictionary<string, HashSet<string>> dependencies,
        IReadOnlyDictionary<string, HashSet<string>> dependents,
        Dictionary<string, JobResult> results,
        HashSet<string> ready)
    {
        if (!dependents.TryGetValue(completedId, out var children))
        {
            return;
        }

        foreach (var child in children)
        {
            if (results.ContainsKey(child))
            {
                continue;
            }

            var dependencyResults = dependencies[child]
                .Where(results.ContainsKey)
                .Select(id => results[id])
                .ToArray();
            if (dependencyResults.Length != dependencies[child].Count)
            {
                continue;
            }

            if (dependencyResults.Any(result => result.Status != JobStatus.Succeeded))
            {
                MarkSkipped(child, dependents, results);
            }
            else
            {
                ready.Add(child);
            }
        }
    }

    private static void MarkSkipped(
        string id,
        IReadOnlyDictionary<string, HashSet<string>> dependents,
        Dictionary<string, JobResult> results)
    {
        if (results.ContainsKey(id))
        {
            return;
        }

        results[id] = new JobResult(id, JobStatus.Skipped, 0, null);
        if (!dependents.TryGetValue(id, out var children))
        {
            return;
        }

        foreach (var child in children)
        {
            MarkSkipped(child, dependents, results);
        }
    }

    private static void ThrowIfCyclic(
        IReadOnlyDictionary<string, JobDefinition> definitions,
        IReadOnlyDictionary<string, HashSet<string>> dependencies)
    {
        var visiting = new HashSet<string>(StringComparer.Ordinal);
        var visited = new HashSet<string>(StringComparer.Ordinal);
        var stack = new List<string>();
        foreach (var id in definitions.Keys.OrderBy(id => id, StringComparer.Ordinal))
        {
            var path = Visit(id, dependencies, visiting, visited, stack);
            if (path.Count > 0)
            {
                throw new DependencyCycleException(path);
            }
        }
    }

    private static IReadOnlyList<string> Visit(
        string id,
        IReadOnlyDictionary<string, HashSet<string>> dependencies,
        HashSet<string> visiting,
        HashSet<string> visited,
        List<string> stack)
    {
        if (visited.Contains(id))
        {
            return Array.Empty<string>();
        }

        if (visiting.Contains(id))
        {
            var start = stack.IndexOf(id);
            var cycle = stack.Skip(start).ToList();
            cycle.Add(id);
            return cycle;
        }

        visiting.Add(id);
        stack.Add(id);
        foreach (var dependency in dependencies[id].OrderBy(value => value, StringComparer.Ordinal))
        {
            var path = Visit(dependency, dependencies, visiting, visited, stack);
            if (path.Count > 0)
            {
                return path;
            }
        }

        stack.RemoveAt(stack.Count - 1);
        visiting.Remove(id);
        visited.Add(id);
        return Array.Empty<string>();
    }
}
