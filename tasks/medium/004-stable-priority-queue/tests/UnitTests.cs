using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void dequeues_by_priority()
    {
        var queue = new global::StablePriorityQueue<string>();
        queue.Enqueue("low", 10);
        queue.Enqueue("high", 1);
        queue.Enqueue("middle", 5);

        Assert.AreEqual("high", queue.Dequeue());
        Assert.AreEqual("middle", queue.Dequeue());
        Assert.AreEqual("low", queue.Dequeue());
    }

    [TestMethod]
    public void preserves_insertion_order_for_equal_priorities()
    {
        var queue = new global::StablePriorityQueue<string>();
        queue.Enqueue("first", 2);
        queue.Enqueue("second", 2);
        queue.Enqueue("third", 2);

        CollectionAssert.AreEqual(new[] { "first", "second", "third" }, new[] { queue.Dequeue(), queue.Dequeue(), queue.Dequeue() });
    }

    [TestMethod]
    public void peek_does_not_remove()
    {
        var queue = new global::StablePriorityQueue<string>();
        queue.Enqueue("item", 1);

        Assert.AreEqual("item", queue.Peek());
        Assert.AreEqual(1, queue.Count);
        Assert.AreEqual("item", queue.Dequeue());
    }

    [TestMethod]
    public void throws_for_empty_queue()
    {
        var queue = new global::StablePriorityQueue<string>();

        Assert.ThrowsException<InvalidOperationException>(() => queue.Peek());
        Assert.ThrowsException<InvalidOperationException>(() => queue.Dequeue());
    }

    [TestMethod]
    public void maintains_count()
    {
        var queue = new global::StablePriorityQueue<int>();
        queue.Enqueue(1, 1);
        queue.Enqueue(2, 1);
        queue.Dequeue();

        Assert.AreEqual(1, queue.Count);
    }
}
