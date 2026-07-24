using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    private sealed class FakeClock : global::IClock
    {
        public DateTimeOffset UtcNow { get; set; } = new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);
    }

    [TestMethod]
    public void allows_requests_below_limit()
    {
        var limiter = new global::InMemoryRateLimiter(2, TimeSpan.FromMinutes(1), new FakeClock());

        Assert.IsTrue(limiter.TryAcquire("a").Allowed);
        var second = limiter.TryAcquire("a");
        Assert.IsTrue(second.Allowed);
        Assert.AreEqual(0, second.Remaining);
    }

    [TestMethod]
    public void blocks_requests_above_limit()
    {
        var limiter = new global::InMemoryRateLimiter(1, TimeSpan.FromMinutes(1), new FakeClock());
        limiter.TryAcquire("a");

        var blocked = limiter.TryAcquire("a");

        Assert.IsFalse(blocked.Allowed);
        Assert.IsTrue(blocked.RetryAfter > TimeSpan.Zero);
    }

    [TestMethod]
    public void isolates_counters_by_key()
    {
        var limiter = new global::InMemoryRateLimiter(1, TimeSpan.FromMinutes(1), new FakeClock());
        limiter.TryAcquire("a");

        Assert.IsTrue(limiter.TryAcquire("b").Allowed);
    }

    [TestMethod]
    public void resets_after_window_advances()
    {
        var clock = new FakeClock();
        var limiter = new global::InMemoryRateLimiter(1, TimeSpan.FromMinutes(1), clock);
        limiter.TryAcquire("a");
        clock.UtcNow = clock.UtcNow.AddMinutes(1).AddTicks(1);

        Assert.IsTrue(limiter.TryAcquire("a").Allowed);
    }

    [TestMethod]
    public async Task is_safe_under_concurrency()
    {
        var limiter = new global::InMemoryRateLimiter(10, TimeSpan.FromMinutes(1), new FakeClock());
        var results = await Task.WhenAll(Enumerable.Range(0, 50).Select(_ => Task.Run(() => limiter.TryAcquire("same").Allowed)));

        Assert.AreEqual(10, results.Count(allowed => allowed));
    }
}
