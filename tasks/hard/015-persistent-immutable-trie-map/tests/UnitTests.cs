using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void inserts_and_finds_simple_keys()
    {
        var map = global::PersistentTrieMap<int>.Empty.Set("alpha", 1).Set("beta", 2);

        Assert.AreEqual(2, map.Count);
        Assert.IsTrue(map.TryGetValue("alpha", out var alpha));
        Assert.AreEqual(1, alpha);
        Assert.IsTrue(map.TryGetValue("beta", out var beta));
        Assert.AreEqual(2, beta);
    }

    [TestMethod]
    public void removes_key_without_affecting_others()
    {
        var map = global::PersistentTrieMap<string>.Empty.Set("car", "red").Set("cart", "blue").Set("dog", "black");

        var removed = map.Remove("car");

        Assert.IsFalse(removed.TryGetValue("car", out _));
        Assert.IsTrue(removed.TryGetValue("cart", out var cart));
        Assert.AreEqual("blue", cart);
        Assert.AreEqual(2, removed.Count);
    }

    [TestMethod]
    public void preserves_old_versions_after_changes()
    {
        var empty = global::PersistentTrieMap<int>.Empty;
        var first = empty.Set("a", 1);
        var second = first.Set("ab", 2);
        var third = second.Remove("a");

        Assert.AreEqual(0, empty.Count);
        Assert.IsTrue(first.TryGetValue("a", out _));
        Assert.IsTrue(second.TryGetValue("a", out _));
        Assert.IsFalse(third.TryGetValue("a", out _));
        Assert.IsTrue(third.TryGetValue("ab", out var value));
        Assert.AreEqual(2, value);
    }

    [TestMethod]
    public void scans_prefix_in_lexicographic_order()
    {
        var map = global::PersistentTrieMap<int>.Empty
            .Set("car", 1)
            .Set("cat", 2)
            .Set("cart", 3)
            .Set("dog", 4)
            .Set("carbon", 5);

        var keys = map.ScanPrefix("car").Select(pair => pair.Key).ToArray();

        CollectionAssert.AreEqual(new[] { "car", "carbon", "cart" }, keys);
    }

    [TestMethod]
    public void handles_empty_null_and_missing_keys()
    {
        var map = global::PersistentTrieMap<string>.Empty.Set("", "root");

        Assert.IsTrue(map.TryGetValue("", out var value));
        Assert.AreEqual("root", value);
        Assert.IsFalse(map.TryGetValue("missing", out var missing));
        Assert.IsNull(missing);
        Assert.AreEqual(1, map.Remove("missing").Count);
        Assert.ThrowsException<ArgumentNullException>(() => map.Set(null!, "bad"));
        Assert.ThrowsException<ArgumentNullException>(() => map.ScanPrefix(null!));
    }

    [TestMethod]
    public void stores_generic_values()
    {
        var map = global::PersistentTrieMap<Payload>.Empty.Set("item", new Payload("x", 9));

        Assert.IsTrue(map.TryGetValue("item", out var payload));
        Assert.AreEqual(new Payload("x", 9), payload);
    }

    [TestMethod]
    public void avoids_observable_mutation_between_instances()
    {
        var first = global::PersistentTrieMap<int>.Empty.Set("a", 1).Set("b", 2);
        var scanBefore = first.ScanPrefix("").ToArray();

        var second = first.Set("c", 3).Remove("a");
        var scanAfter = first.ScanPrefix("").ToArray();

        CollectionAssert.AreEqual(scanBefore, scanAfter);
        CollectionAssert.AreEqual(new[] { "b", "c" }, second.ScanPrefix("").Select(pair => pair.Key).ToArray());
    }

    private sealed record Payload(string Name, int Count);
}
