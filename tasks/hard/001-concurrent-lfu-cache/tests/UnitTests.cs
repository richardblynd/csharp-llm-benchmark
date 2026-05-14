using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    private static void AssertThrowsArgumentException(Action action)
    {
        try
        {
            action();
        }
        catch (ArgumentException)
        {
            return;
        }
        catch (Exception exception)
        {
            Assert.Fail($"Expected ArgumentException or a derived type, but {exception.GetType().Name} was thrown.");
        }

        Assert.Fail("Expected ArgumentException or a derived type, but no exception was thrown.");
    }

    private sealed class FakeClock : global::IClock
    {
        public DateTimeOffset UtcNow { get; private set; } = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);

        public void Advance(TimeSpan amount) => UtcNow = UtcNow.Add(amount);
    }

    [TestMethod]
    public void stores_and_returns_values_before_ttl()
    {
        var clock = new FakeClock();
        var cache = new global::ConcurrentLfuCache<string, int>(2, TimeSpan.FromMinutes(5), clock);

        cache.Set("a", 10);

        Assert.IsTrue(cache.TryGet("a", out var value));
        Assert.AreEqual(10, value);
        Assert.AreEqual(10, cache.Get("a"));
        Assert.AreEqual(1, cache.Count);
    }

    [TestMethod]
    public void expires_entries_using_injected_clock()
    {
        var clock = new FakeClock();
        var cache = new global::ConcurrentLfuCache<string, int>(2, TimeSpan.FromSeconds(10), clock);
        cache.Set("a", 1);

        clock.Advance(TimeSpan.FromSeconds(10));

        Assert.IsFalse(cache.TryGet("a", out _));
        Assert.ThrowsException<KeyNotFoundException>(() => cache.Get("a"));
        Assert.AreEqual(0, cache.Count);
    }

    [TestMethod]
    public void evicts_by_frequency_then_recency()
    {
        var cache = new global::ConcurrentLfuCache<string, string>(2, TimeSpan.FromMinutes(10), new FakeClock());
        cache.Set("a", "first");
        cache.Set("b", "second");
        Assert.AreEqual("first", cache.Get("a"));
        cache.Set("c", "third");

        Assert.IsTrue(cache.TryGet("a", out _));
        Assert.IsFalse(cache.TryGet("b", out _));
        Assert.AreEqual("third", cache.Get("c"));

        cache.Set("d", "fourth");

        Assert.IsTrue(cache.TryGet("a", out _));
        Assert.IsFalse(cache.TryGet("c", out _));
        Assert.AreEqual("fourth", cache.Get("d"));
    }

    [TestMethod]
    public async Task coalesces_concurrent_loads_for_same_key()
    {
        var cache = new global::ConcurrentLfuCache<string, int>(2, TimeSpan.FromMinutes(5), new FakeClock());
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var calls = 0;

        var requests = Enumerable.Range(0, 12)
            .Select(_ => cache.GetOrLoadAsync("shared", async (key, token) =>
            {
                Interlocked.Increment(ref calls);
                await release.Task.WaitAsync(token);
                return 42;
            }))
            .ToArray();

        Assert.IsTrue(SpinWait.SpinUntil(() => Volatile.Read(ref calls) >= 1, TimeSpan.FromSeconds(1)));
        release.SetResult();
        var values = await Task.WhenAll(requests);

        Assert.AreEqual(1, calls);
        CollectionAssert.AreEqual(Enumerable.Repeat(42, 12).ToArray(), values);
        Assert.AreEqual(42, cache.Get("shared"));
    }

    [TestMethod]
    public async Task loader_failure_does_not_poison_cache()
    {
        var cache = new global::ConcurrentLfuCache<string, int>(2, TimeSpan.FromMinutes(5), new FakeClock());
        var attempts = 0;

        await Assert.ThrowsExceptionAsync<InvalidOperationException>(() => cache.GetOrLoadAsync("a", (key, token) =>
        {
            attempts++;
            return Task.FromException<int>(new InvalidOperationException("temporary"));
        }));

        var value = await cache.GetOrLoadAsync("a", (key, token) =>
        {
            attempts++;
            return Task.FromResult(99);
        });

        Assert.AreEqual(99, value);
        Assert.AreEqual(2, attempts);
        Assert.AreEqual(99, cache.Get("a"));
    }

    [TestMethod]
    public void validates_capacity_and_ttl()
    {
        AssertThrowsArgumentException(() => new global::ConcurrentLfuCache<int, int>(0, TimeSpan.FromSeconds(1)));
        AssertThrowsArgumentException(() => new global::ConcurrentLfuCache<int, int>(1, TimeSpan.Zero));
    }
}
