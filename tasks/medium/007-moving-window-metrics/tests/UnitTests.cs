using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void aggregates_values_inside_window()
    {
        var now = new DateTime(2026, 1, 1, 12, 0, 0);
        var aggregator = new global::MovingWindowAggregator(TimeSpan.FromMinutes(10));
        aggregator.Add(now.AddMinutes(-5), 10);
        aggregator.Add(now.AddMinutes(-1), 5);

        var snapshot = aggregator.GetSnapshot(now);
        Assert.AreEqual(2, snapshot.Count);
        Assert.AreEqual(15, snapshot.Sum);
    }

    [TestMethod]
    public void removes_expired_events()
    {
        var now = new DateTime(2026, 1, 1, 12, 0, 0);
        var aggregator = new global::MovingWindowAggregator(TimeSpan.FromMinutes(10));
        aggregator.Add(now.AddMinutes(-11), 99);
        aggregator.Add(now.AddMinutes(-10), 1);

        var snapshot = aggregator.GetSnapshot(now);
        Assert.AreEqual(1, snapshot.Count);
        Assert.AreEqual(1, snapshot.Sum);
    }

    [TestMethod]
    public void calculates_min_max_and_average()
    {
        var now = new DateTime(2026, 1, 1, 12, 0, 0);
        var aggregator = new global::MovingWindowAggregator(TimeSpan.FromMinutes(10));
        aggregator.Add(now.AddMinutes(-3), 2);
        aggregator.Add(now.AddMinutes(-2), 8);
        aggregator.Add(now.AddMinutes(-1), 5);

        var snapshot = aggregator.GetSnapshot(now);
        Assert.AreEqual(2, snapshot.Min);
        Assert.AreEqual(8, snapshot.Max);
        Assert.AreEqual(5, snapshot.Average);
    }

    [TestMethod]
    public void handles_out_of_order_events()
    {
        var now = new DateTime(2026, 1, 1, 12, 0, 0);
        var aggregator = new global::MovingWindowAggregator(TimeSpan.FromMinutes(10));
        aggregator.Add(now.AddMinutes(-1), 10);
        aggregator.Add(now.AddMinutes(-20), 100);
        aggregator.Add(now.AddMinutes(-5), 20);

        Assert.AreEqual(30, aggregator.GetSnapshot(now).Sum);
    }

    [TestMethod]
    public void returns_empty_state_correctly()
    {
        var snapshot = new global::MovingWindowAggregator(TimeSpan.FromMinutes(1)).GetSnapshot(DateTime.UtcNow);

        Assert.AreEqual(0, snapshot.Count);
        Assert.AreEqual(0, snapshot.Sum);
        Assert.AreEqual(0, snapshot.Min);
        Assert.AreEqual(0, snapshot.Max);
        Assert.AreEqual(0, snapshot.Average);
    }
}
