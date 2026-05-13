using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void accepts_non_conflicting_events()
    {
        var scheduler = new global::CalendarScheduler();
        Assert.IsTrue(scheduler.AddEvent("morning", new DateTime(2026, 1, 1, 9, 0, 0), new DateTime(2026, 1, 1, 10, 0, 0)));
        Assert.IsTrue(scheduler.AddEvent("late", new DateTime(2026, 1, 1, 11, 0, 0), new DateTime(2026, 1, 1, 12, 0, 0)));
    }

    [TestMethod]
    public void rejects_partial_overlap()
    {
        var scheduler = new global::CalendarScheduler();
        scheduler.AddEvent("base", new DateTime(2026, 1, 1, 9, 0, 0), new DateTime(2026, 1, 1, 11, 0, 0));

        Assert.IsFalse(scheduler.AddEvent("overlap", new DateTime(2026, 1, 1, 10, 30, 0), new DateTime(2026, 1, 1, 12, 0, 0)));
        Assert.AreEqual(1, scheduler.ListEvents().Count);
    }

    [TestMethod]
    public void allows_adjacent_events()
    {
        var scheduler = new global::CalendarScheduler();
        Assert.IsTrue(scheduler.AddEvent("first", new DateTime(2026, 1, 1, 9, 0, 0), new DateTime(2026, 1, 1, 10, 0, 0)));
        Assert.IsTrue(scheduler.AddEvent("second", new DateTime(2026, 1, 1, 10, 0, 0), new DateTime(2026, 1, 1, 11, 0, 0)));
    }

    [TestMethod]
    public void lists_events_in_chronological_order()
    {
        var scheduler = new global::CalendarScheduler();
        scheduler.AddEvent("b", new DateTime(2026, 1, 1, 13, 0, 0), new DateTime(2026, 1, 1, 14, 0, 0));
        scheduler.AddEvent("a", new DateTime(2026, 1, 1, 8, 0, 0), new DateTime(2026, 1, 1, 9, 0, 0));

        CollectionAssert.AreEqual(new[] { "a", "b" }, scheduler.ListEvents().Select(e => e.Id).ToArray());
    }

    [TestMethod]
    public void validates_invalid_interval()
    {
        var scheduler = new global::CalendarScheduler();
        Assert.ThrowsException<ArgumentException>(() => scheduler.AddEvent("bad", DateTime.Today, DateTime.Today));
    }
}
