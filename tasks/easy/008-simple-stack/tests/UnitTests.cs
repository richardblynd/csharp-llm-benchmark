using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void pushes_and_pops_in_lifo_order()
    {
        var stack = new global::SimpleStack<int>();
        stack.Push(1);
        stack.Push(2);
        stack.Push(3);
        Assert.AreEqual(3, stack.Pop());
        Assert.AreEqual(2, stack.Pop());
        Assert.AreEqual(1, stack.Pop());
    }

    [TestMethod]
    public void peek_does_not_remove_item()
    {
        var stack = new global::SimpleStack<string>();
        stack.Push("first");
        stack.Push("second");
        Assert.AreEqual("second", stack.Peek());
        Assert.AreEqual(2, stack.Count);
    }

    [TestMethod]
    public void count_tracks_items()
    {
        var stack = new global::SimpleStack<int>();
        stack.Push(10);
        stack.Push(20);
        stack.Pop();
        Assert.AreEqual(1, stack.Count);
    }

    [TestMethod]
    public void throws_when_empty()
    {
        var stack = new global::SimpleStack<int>();
        Assert.ThrowsException<InvalidOperationException>(() => stack.Pop());
        Assert.ThrowsException<InvalidOperationException>(() => stack.Peek());
    }
}
