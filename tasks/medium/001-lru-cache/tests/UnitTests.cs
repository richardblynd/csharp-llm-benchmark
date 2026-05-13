using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void stores_and_retrieves_values()
    {
        var cache = new global::LruCache<string, int>(2);
        cache.Put("a", 10);

        Assert.IsTrue(cache.TryGet("a", out var value));
        Assert.AreEqual(10, value);
        Assert.AreEqual(1, cache.Count);
    }

    [TestMethod]
    public void updates_existing_item_without_duplicating()
    {
        var cache = new global::LruCache<string, int>(2);
        cache.Put("a", 1);
        cache.Put("a", 2);
        cache.Put("b", 3);

        Assert.AreEqual(2, cache.Count);
        Assert.AreEqual(2, cache.Get("a"));
    }

    [TestMethod]
    public void evicts_least_recently_used_item()
    {
        var cache = new global::LruCache<string, int>(2);
        cache.Put("a", 1);
        cache.Put("b", 2);
        cache.Put("c", 3);

        Assert.IsFalse(cache.TryGet("a", out _));
        Assert.AreEqual(2, cache.Get("b"));
        Assert.AreEqual(3, cache.Get("c"));
    }

    [TestMethod]
    public void get_updates_recency()
    {
        var cache = new global::LruCache<string, int>(2);
        cache.Put("a", 1);
        cache.Put("b", 2);
        Assert.AreEqual(1, cache.Get("a"));
        cache.Put("c", 3);

        Assert.IsTrue(cache.TryGet("a", out _));
        Assert.IsFalse(cache.TryGet("b", out _));
        Assert.IsTrue(cache.TryGet("c", out _));
    }

    [TestMethod]
    public void rejects_invalid_capacity()
    {
        Assert.ThrowsException<ArgumentOutOfRangeException>(() => new global::LruCache<int, int>(0));
    }
}
