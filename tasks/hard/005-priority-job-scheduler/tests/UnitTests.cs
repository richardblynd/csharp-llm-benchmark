using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public async Task runs_ready_jobs_by_priority()
    {
        var order = new List<string>();
        var scheduler = new global::PriorityJobScheduler();
        var jobs = new[]
        {
            Job("low", 1, order),
            Job("high", 10, order),
            Job("middle", 5, order)
        };

        var result = await scheduler.RunAsync(jobs, maxDegreeOfParallelism: 1);

        CollectionAssert.AreEqual(new[] { "high", "middle", "low" }, order);
        Assert.IsTrue(result.Jobs.All(job => job.Status == global::JobStatus.Succeeded));
    }

    [TestMethod]
    public async Task waits_for_successful_dependencies()
    {
        var order = new List<string>();
        var scheduler = new global::PriorityJobScheduler();
        var jobs = new[]
        {
            Job("child", 100, order, dependencies: new[] { "parent" }),
            Job("parent", 1, order)
        };

        await scheduler.RunAsync(jobs, maxDegreeOfParallelism: 2);

        CollectionAssert.AreEqual(new[] { "parent", "child" }, order);
    }

    [TestMethod]
    public async Task enforces_max_parallelism()
    {
        var active = 0;
        var observedMax = 0;
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var twoStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var jobs = Enumerable.Range(0, 6)
            .Select(index => new global::JobDefinition($"job-{index}", 0, async token =>
            {
                var current = Interlocked.Increment(ref active);
                UpdateMax(ref observedMax, current);
                if (current == 2)
                {
                    twoStarted.TrySetResult();
                }

                await release.Task.WaitAsync(token);
                Interlocked.Decrement(ref active);
            }))
            .ToArray();

        var run = new global::PriorityJobScheduler().RunAsync(jobs, maxDegreeOfParallelism: 2);
        await twoStarted.Task.WaitAsync(TimeSpan.FromSeconds(1));
        Assert.AreEqual(2, observedMax);

        release.SetResult();
        await run;

        Assert.IsTrue(observedMax <= 2);
    }

    [TestMethod]
    public async Task retries_failed_jobs_to_configured_limit()
    {
        var attempts = 0;
        var job = new global::JobDefinition("unstable", 0, token =>
        {
            attempts++;
            if (attempts < 3)
            {
                throw new InvalidOperationException("Not yet.");
            }

            return Task.CompletedTask;
        }, MaxAttempts: 4);

        var result = await new global::PriorityJobScheduler().RunAsync(new[] { job }, 1);

        var jobResult = result.Jobs.Single(job => job.Id == "unstable");
        Assert.AreEqual(global::JobStatus.Succeeded, jobResult.Status);
        Assert.AreEqual(3, jobResult.Attempts);
    }

    [TestMethod]
    public async Task skips_dependents_after_failed_dependency()
    {
        var childRan = false;
        var jobs = new[]
        {
            new global::JobDefinition("parent", 0, token => throw new InvalidOperationException("failed")),
            new global::JobDefinition("child", 10, token =>
            {
                childRan = true;
                return Task.CompletedTask;
            }, new[] { "parent" })
        };

        var result = await new global::PriorityJobScheduler().RunAsync(jobs, 2);

        Assert.IsFalse(childRan);
        Assert.AreEqual(global::JobStatus.Failed, result.Jobs.Single(job => job.Id == "parent").Status);
        Assert.AreEqual(global::JobStatus.Skipped, result.Jobs.Single(job => job.Id == "child").Status);
    }

    [TestMethod]
    public async Task honors_cancellation()
    {
        using var cts = new CancellationTokenSource();
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var jobs = new[]
        {
            new global::JobDefinition("running", 10, async token =>
            {
                started.SetResult();
                await Task.Delay(TimeSpan.FromSeconds(30), token);
            }),
            new global::JobDefinition("waiting", 0, token => Task.CompletedTask)
        };

        var run = new global::PriorityJobScheduler().RunAsync(jobs, 1, cts.Token);
        await started.Task.WaitAsync(TimeSpan.FromSeconds(1));
        cts.Cancel();
        var result = await run;

        Assert.AreEqual(global::JobStatus.Canceled, result.Jobs.Single(job => job.Id == "running").Status);
        Assert.AreEqual(global::JobStatus.Canceled, result.Jobs.Single(job => job.Id == "waiting").Status);
    }

    [TestMethod]
    public async Task detects_dependency_cycles_before_running()
    {
        var ran = false;
        var jobs = new[]
        {
            new global::JobDefinition("a", 0, token =>
            {
                ran = true;
                return Task.CompletedTask;
            }, new[] { "b" }),
            new global::JobDefinition("b", 0, token => Task.CompletedTask, new[] { "c" }),
            new global::JobDefinition("c", 0, token => Task.CompletedTask, new[] { "a" })
        };

        var exception = await Assert.ThrowsExceptionAsync<global::DependencyCycleException>(
            () => new global::PriorityJobScheduler().RunAsync(jobs, 2));

        Assert.IsFalse(ran);
        Assert.AreEqual(exception.Path.First(), exception.Path.Last());
    }

    private static global::JobDefinition Job(string id, int priority, List<string> order, IReadOnlyCollection<string>? dependencies = null)
    {
        return new global::JobDefinition(id, priority, token =>
        {
            order.Add(id);
            return Task.CompletedTask;
        }, dependencies);
    }

    private static void UpdateMax(ref int target, int value)
    {
        while (true)
        {
            var current = Volatile.Read(ref target);
            if (value <= current || Interlocked.CompareExchange(ref target, value, current) == current)
            {
                return;
            }
        }
    }
}
