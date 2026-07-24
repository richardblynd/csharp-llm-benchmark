using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public async Task executes_all_tasks_and_preserves_results()
    {
        var result = await global::ParallelExecutor.ExecuteAsync(new[] { 3, 1, 2 }, async (value, token) =>
        {
            await Task.Delay(10 * value, token);
            return value * 2;
        }, 3);

        CollectionAssert.AreEqual(new[] { 6, 2, 4 }, result.ToArray());
    }

    [TestMethod]
    public async Task respects_concurrency_limit()
    {
        var active = 0;
        var maxSeen = 0;
        await global::ParallelExecutor.ExecuteAsync(Enumerable.Range(0, 8).ToArray(), async (value, token) =>
        {
            var current = Interlocked.Increment(ref active);
            maxSeen = Math.Max(maxSeen, current);
            await Task.Delay(30, token);
            Interlocked.Decrement(ref active);
            return value;
        }, 2);

        Assert.IsTrue(maxSeen <= 2, $"Expected max concurrency <= 2 but saw {maxSeen}.");
    }

    [TestMethod]
    public async Task propagates_exceptions()
    {
        await Assert.ThrowsExceptionAsync<InvalidOperationException>(() =>
            global::ParallelExecutor.ExecuteAsync(new[] { 1, 2 }, (value, token) =>
            {
                if (value == 2)
                {
                    return Task.FromException<int>(new InvalidOperationException("boom"));
                }

                return Task.FromResult(value);
            }, 2));
    }

    [TestMethod]
    public async Task respects_cancellation()
    {
        using var cts = new CancellationTokenSource();
        cts.Cancel();

        await Assert.ThrowsExceptionAsync<OperationCanceledException>(() =>
            global::ParallelExecutor.ExecuteAsync(new[] { 1 }, (value, token) => Task.FromResult(value), 1, cts.Token));
    }

    [TestMethod]
    public async Task handles_empty_list()
    {
        var result = await global::ParallelExecutor.ExecuteAsync(Array.Empty<int>(), (value, token) => Task.FromResult(value), 3);

        Assert.AreEqual(0, result.Count);
    }
}
