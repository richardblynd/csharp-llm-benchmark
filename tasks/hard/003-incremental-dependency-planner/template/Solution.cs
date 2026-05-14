using System;
using System.Collections.Generic;

public sealed record PlannedItem(string Id, int Priority = 0, string? Group = null);

public sealed record PlanUpdate(
    IReadOnlyList<string> Order,
    IReadOnlyList<string> Affected,
    IReadOnlyList<string> Unaffected);

public sealed class MissingDependencyException : Exception
{
    public MissingDependencyException(string itemId, string dependencyId)
    {
        ItemId = itemId;
        DependencyId = dependencyId;
    }

    public string ItemId { get; }
    public string DependencyId { get; }
}

public sealed class DependencyCycleException : Exception
{
    public DependencyCycleException(IReadOnlyList<string> path)
    {
        Path = path;
    }

    public IReadOnlyList<string> Path { get; }
}

public sealed class DependencyPlanner
{
    public void AddItem(string id, int priority = 0, string? group = null) => throw new NotImplementedException();
    public bool RemoveItem(string id) => throw new NotImplementedException();
    public void AddDependency(string itemId, string dependencyId) => throw new NotImplementedException();
    public bool RemoveDependency(string itemId, string dependencyId) => throw new NotImplementedException();
    public IReadOnlyList<string> BuildPlan() => throw new NotImplementedException();
    public PlanUpdate BuildPlanForChanges(IReadOnlyCollection<string> changedItemIds) => throw new NotImplementedException();
}
