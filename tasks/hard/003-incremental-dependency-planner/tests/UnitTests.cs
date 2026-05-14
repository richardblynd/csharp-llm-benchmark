using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void orders_acyclic_dependencies()
    {
        var planner = new global::DependencyPlanner();
        planner.AddItem("deploy");
        planner.AddItem("build");
        planner.AddItem("test");
        planner.AddDependency("test", "build");
        planner.AddDependency("deploy", "test");

        var plan = planner.BuildPlan();

        CollectionAssert.AreEqual(new[] { "build", "test", "deploy" }, plan.ToArray());
    }

    [TestMethod]
    public void uses_deterministic_priority_then_id_order()
    {
        var planner = new global::DependencyPlanner();
        planner.AddItem("beta", priority: 1);
        planner.AddItem("alpha", priority: 1);
        planner.AddItem("critical", priority: 10);
        planner.AddItem("after-critical", priority: 100);
        planner.AddDependency("after-critical", "critical");

        var plan = planner.BuildPlan();

        CollectionAssert.AreEqual(new[] { "critical", "after-critical", "alpha", "beta" }, plan.ToArray());
    }

    [TestMethod]
    public void detects_cycle_with_diagnostic_path()
    {
        var planner = new global::DependencyPlanner();
        planner.AddItem("a");
        planner.AddItem("b");
        planner.AddItem("c");
        planner.AddDependency("a", "b");
        planner.AddDependency("b", "c");
        planner.AddDependency("c", "a");

        var exception = Assert.ThrowsException<global::DependencyCycleException>(() => planner.BuildPlan());

        CollectionAssert.Contains(exception.Path.ToArray(), "a");
        Assert.AreEqual(exception.Path.First(), exception.Path.Last());
        Assert.IsTrue(exception.Path.Count >= 4);
    }

    [TestMethod]
    public void detects_missing_dependency()
    {
        var planner = new global::DependencyPlanner();
        planner.AddItem("package");
        planner.AddDependency("package", "compile");

        var exception = Assert.ThrowsException<global::MissingDependencyException>(() => planner.BuildPlan());

        Assert.AreEqual("package", exception.ItemId);
        Assert.AreEqual("compile", exception.DependencyId);
    }

    [TestMethod]
    public void updates_plan_after_dependency_changes()
    {
        var planner = new global::DependencyPlanner();
        planner.AddItem("a");
        planner.AddItem("b");
        planner.AddItem("c");
        planner.AddDependency("c", "a");

        CollectionAssert.AreEqual(new[] { "a", "b", "c" }, planner.BuildPlan().ToArray());

        planner.RemoveDependency("c", "a");
        planner.AddDependency("b", "c");

        CollectionAssert.AreEqual(new[] { "a", "c", "b" }, planner.BuildPlan().ToArray());
    }

    [TestMethod]
    public void separates_affected_and_unaffected_items()
    {
        var planner = new global::DependencyPlanner();
        planner.AddItem("core");
        planner.AddItem("api");
        planner.AddItem("ui");
        planner.AddItem("docs");
        planner.AddDependency("api", "core");
        planner.AddDependency("ui", "api");

        var update = planner.BuildPlanForChanges(new[] { "core", "missing" });

        CollectionAssert.AreEqual(new[] { "core", "api", "ui" }, update.Affected.ToArray());
        CollectionAssert.AreEqual(new[] { "docs" }, update.Unaffected.ToArray());
        CollectionAssert.AreEqual(new[] { "core", "api", "docs", "ui" }, update.Order.ToArray());
    }
}
