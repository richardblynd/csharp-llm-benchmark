using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void inserts_and_queries_simple_intervals()
    {
        var index = new global::VersionedIntervalIndex<string>();

        var version = index.Add(0, 10, "alpha");
        var result = index.Query(3, 4);

        Assert.AreEqual(1, version);
        Assert.AreEqual(1, index.CurrentVersion);
        Assert.AreEqual("alpha", result.Single().Value);
        Assert.AreEqual(1L, result.Single().Sequence);
    }

    [TestMethod]
    public void returns_all_range_intersections()
    {
        var index = new global::VersionedIntervalIndex<string>();
        index.Add(0, 5, "a");
        index.Add(4, 8, "b");
        index.Add(10, 12, "c");
        index.Add(-3, 1, "d");

        var result = index.Query(0, 6).Select(interval => interval.Value).ToArray();

        CollectionAssert.AreEqual(new[] { "d", "a", "b" }, result);
    }

    [TestMethod]
    public void preserves_snapshot_versions()
    {
        var index = new global::VersionedIntervalIndex<string>();
        var v1 = index.Add(0, 10, "first");
        var v2 = index.Add(20, 30, "second");

        index.Add(5, 25, "third");

        CollectionAssert.AreEqual(new[] { "first" }, index.QueryVersion(v1, 0, 100).Select(interval => interval.Value).ToArray());
        CollectionAssert.AreEqual(new[] { "first", "second" }, index.QueryVersion(v2, 0, 100).Select(interval => interval.Value).ToArray());
        CollectionAssert.AreEqual(new[] { "first", "third", "second" }, index.Query(0, 100).Select(interval => interval.Value).ToArray());
    }

    [TestMethod]
    public void treats_adjacent_intervals_as_non_overlapping()
    {
        var index = new global::VersionedIntervalIndex<string>();
        index.Add(0, 10, "left");
        index.Add(10, 20, "right");

        var left = index.Query(0, 10).Select(interval => interval.Value).ToArray();
        var pointAtBoundary = index.Query(10, 11).Select(interval => interval.Value).ToArray();

        CollectionAssert.AreEqual(new[] { "left" }, left);
        CollectionAssert.AreEqual(new[] { "right" }, pointAtBoundary);
    }

    [TestMethod]
    public void rejects_invalid_intervals_without_changing_state()
    {
        var index = new global::VersionedIntervalIndex<string>();
        index.Add(1, 2, "valid");

        var exception = Assert.ThrowsException<global::InvalidIntervalException>(() => index.Add(5, 5, "bad"));
        Assert.AreEqual(5, exception.Start);
        Assert.AreEqual(5, exception.End);
        Assert.AreEqual(1, index.CurrentVersion);
        CollectionAssert.AreEqual(new[] { "valid" }, index.Query(0, 10).Select(interval => interval.Value).ToArray());
        Assert.ThrowsException<global::InvalidIntervalException>(() => index.Query(2, 2));
    }

    [TestMethod]
    public void returns_results_in_deterministic_order()
    {
        var index = new global::VersionedIntervalIndex<string>();
        index.Add(5, 8, "third");
        index.Add(0, 3, "first");
        index.Add(0, 2, "zeroth");
        index.Add(0, 3, "second");

        var result = index.Query(-1, 10).Select(interval => interval.Value).ToArray();

        CollectionAssert.AreEqual(new[] { "zeroth", "first", "second", "third" }, result);
    }

    [TestMethod]
    public void handles_empty_index_and_old_versions()
    {
        var index = new global::VersionedIntervalIndex<int>();

        CollectionAssert.AreEqual(Array.Empty<int>(), index.Query(0, 1).Select(interval => interval.Value).ToArray());
        CollectionAssert.AreEqual(Array.Empty<int>(), index.QueryVersion(0, 0, 1).Select(interval => interval.Value).ToArray());
        Assert.ThrowsException<ArgumentOutOfRangeException>(() => index.QueryVersion(1, 0, 1));
    }
}
