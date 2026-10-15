using Microsoft.VisualStudio.TestTools.UnitTesting;
using StackProject;

[TestClass]
public sealed class RegressionTests
{
    [TestMethod]
    public void old_push_and_pop_preserve_lifo()
    {
        var stack = new SimpleStack<int>();
        Assert.AreEqual(0, stack.Count);
        foreach (var item in new[] { 4, 7, 2 }) stack.Push(item);
        Assert.AreEqual(3, stack.Count);
        foreach (var item in new[] { 2, 7, 4 }) Assert.AreEqual(item, stack.Pop());
        Assert.AreEqual(0, stack.Count);
    }

    [TestMethod]
    public void old_peek_preserves_count()
    {
        var stack = new SimpleStack<string>();
        stack.Push("first");
        stack.Push("last");
        Assert.AreEqual("last", stack.Peek());
        Assert.AreEqual("last", stack.Peek());
        Assert.AreEqual(2, stack.Count);
        Assert.AreEqual("last", stack.Pop());
        Assert.AreEqual("first", stack.Peek());
    }

    [TestMethod]
    public void old_empty_operations_throw()
    {
        var stack = new SimpleStack<int>();
        Assert.ThrowsException<InvalidOperationException>(() => stack.Pop());
        Assert.ThrowsException<InvalidOperationException>(() => stack.Peek());
        stack.Push(1);
        stack.Pop();
        Assert.ThrowsException<InvalidOperationException>(() => stack.Pop());
        Assert.ThrowsException<InvalidOperationException>(() => stack.Peek());
    }

    [TestMethod]
    public void old_instances_are_independent()
    {
        var first = new SimpleStack<int>();
        var second = new SimpleStack<int>();
        first.Push(42);
        second.Push(9);
        Assert.AreEqual(42, first.Pop());
        Assert.AreEqual(9, second.Peek());
        Assert.AreEqual(1, second.Count);
        Assert.AreEqual(0, first.Count);
    }

    [TestMethod]
    public void old_methods_support_null_and_default_values()
    {
        var strings = new SimpleStack<string?>();
        strings.Push("value");
        strings.Push(null);
        Assert.IsNull(strings.Peek());
        Assert.IsNull(strings.Pop());
        Assert.AreEqual("value", strings.Pop());
        var numbers = new SimpleStack<int>();
        numbers.Push(0);
        Assert.AreEqual(0, numbers.Pop());
    }
}
