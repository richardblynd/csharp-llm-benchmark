using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public async Task processes_successful_items()
    {
        var results = await global::ResilientProcessor.ProcessAsync(new[] { 1, 2 }, (value, token) => Task.FromResult(value * 10), 3);

        Assert.IsTrue(results.All(r => r.Succeeded));
        CollectionAssert.AreEqual(new[] { 10, 20 }, results.Select(r => r.Value).ToArray());
    }

    [TestMethod]
    public async Task retries_transient_failures_to_limit()
    {
        var attempts = 0;
        var results = await global::ResilientProcessor.ProcessAsync(new[] { "item" }, (value, token) =>
        {
            attempts++;
            if (attempts < 3)
            {
                return Task.FromException<string>(new InvalidOperationException("transient"));
            }

            return Task.FromResult("ok");
        }, 3);

        Assert.IsTrue(results[0].Succeeded);
        Assert.AreEqual(3, results[0].Attempts);
    }

    [TestMethod]
    public async Task records_final_failure_per_item()
    {
        var results = await global::ResilientProcessor.ProcessAsync(new[] { 1 }, (value, token) =>
        {
            return Task.FromException<int>(new InvalidOperationException("nope"));
        }, 2);

        Assert.IsFalse(results[0].Succeeded);
        Assert.IsInstanceOfType(results[0].Error, typeof(InvalidOperationException));
        Assert.AreEqual(2, results[0].Attempts);
    }

    [TestMethod]
    public async Task preserves_result_order()
    {
        var results = await global::ResilientProcessor.ProcessAsync(new[] { 3, 1, 2 }, (value, token) => Task.FromResult(value), 2);

        CollectionAssert.AreEqual(new[] { 3, 1, 2 }, results.Select(r => r.Value).ToArray());
    }

    [TestMethod]
    public async Task does_not_retry_beyond_limit()
    {
        var calls = 0;
        await global::ResilientProcessor.ProcessAsync(new[] { 1 }, (value, token) =>
        {
            calls++;
            return Task.FromException<int>(new InvalidOperationException());
        }, 4);

        Assert.AreEqual(4, calls);
    }
}
