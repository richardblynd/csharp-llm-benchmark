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

    [TestMethod]
    public void sorts_simple_graph()
    {
        var graph = new global::DependencyGraph();
        graph.AddItem("app");
        graph.AddItem("lib");
        graph.AddDependency("app", "lib");

        CollectionAssert.AreEqual(new[] { "lib", "app" }, graph.GetExecutionOrder().ToArray());
    }

    [TestMethod]
    public void sorts_independent_components_deterministically()
    {
        var graph = new global::DependencyGraph();
        foreach (var item in new[] { "z", "a", "m" })
        {
            graph.AddItem(item);
        }

        CollectionAssert.AreEqual(new[] { "a", "m", "z" }, graph.GetExecutionOrder().ToArray());
    }

    [TestMethod]
    public void detects_cycle()
    {
        var graph = new global::DependencyGraph();
        graph.AddItem("a");
        graph.AddItem("b");
        graph.AddDependency("a", "b");
        graph.AddDependency("b", "a");

        Assert.ThrowsException<InvalidOperationException>(() => graph.GetExecutionOrder());
    }

    [TestMethod]
    public void detects_unknown_dependency()
    {
        var graph = new global::DependencyGraph();
        graph.AddItem("app");

        AssertThrowsArgumentException(() => graph.AddDependency("app", "missing"));
    }

    [TestMethod]
    public void handles_empty_graph()
    {
        Assert.AreEqual(0, new global::DependencyGraph().GetExecutionOrder().Count);
    }
}
