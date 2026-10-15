using Microsoft.VisualStudio.TestTools.UnitTesting;
using StackProject;

[TestClass]
public sealed class FeatureTests
{
    [TestMethod]
    public void try_operations_on_empty_stack_return_false_and_default()
    {
        var numbers = new SimpleStack<int>();
        Assert.IsFalse(numbers.TryPop(out var popped));
        Assert.AreEqual(0, popped);
        Assert.IsFalse(numbers.TryPeek(out var peeked));
        Assert.AreEqual(0, peeked);
        Assert.AreEqual(0, numbers.Count);
        var strings = new SimpleStack<string>();
        Assert.IsFalse(strings.TryPeek(out var text));
        Assert.IsNull(text);
    }

    [TestMethod]
    public void try_pop_removes_the_latest_item()
    {
        var stack = new SimpleStack<int>();
        stack.Push(10);
        stack.Push(20);
        Assert.IsTrue(stack.TryPop(out var first));
        Assert.AreEqual(20, first);
        Assert.AreEqual(1, stack.Count);
        Assert.IsTrue(stack.TryPop(out var second));
        Assert.AreEqual(10, second);
        Assert.AreEqual(0, stack.Count);
        Assert.IsFalse(stack.TryPop(out _));
    }

    [TestMethod]
    public void try_peek_preserves_the_latest_item()
    {
        var stack = new SimpleStack<int>();
        stack.Push(10);
        stack.Push(20);
        for (var i = 0; i < 3; i++)
        {
            Assert.IsTrue(stack.TryPeek(out var value));
            Assert.AreEqual(20, value);
            Assert.AreEqual(2, stack.Count);
        }
        Assert.AreEqual(20, stack.Pop());
    }

    [TestMethod]
    public void try_operations_support_null_values()
    {
        var stack = new SimpleStack<string?>();
        stack.Push(null);
        Assert.IsTrue(stack.TryPeek(out var peeked));
        Assert.IsNull(peeked);
        Assert.IsTrue(stack.TryPop(out var popped));
        Assert.IsNull(popped);
        Assert.AreEqual(0, stack.Count);
        var numbers = new SimpleStack<int>();
        numbers.Push(0);
        Assert.IsTrue(numbers.TryPop(out var zero));
        Assert.AreEqual(0, zero);
    }

    [TestMethod]
    public void try_operations_interoperate_with_existing_methods()
    {
        var stack = new SimpleStack<int>();
        stack.Push(1);
        stack.Push(2);
        Assert.IsTrue(stack.TryPop(out var value));
        Assert.AreEqual(2, value);
        stack.Push(3);
        Assert.IsTrue(stack.TryPeek(out var top));
        Assert.AreEqual(3, top);
        Assert.AreEqual(3, stack.Pop());
        Assert.AreEqual(1, stack.Peek());
        Assert.IsTrue(stack.TryPop(out var last));
        Assert.AreEqual(1, last);
        Assert.AreEqual(0, stack.Count);
    }
}
