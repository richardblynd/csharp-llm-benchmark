Write an incremental dependency planner.

Required public API:

```csharp
public sealed record PlannedItem(string Id, int Priority = 0, string? Group = null);

public sealed record PlanUpdate(
    IReadOnlyList<string> Order,
    IReadOnlyList<string> Affected,
    IReadOnlyList<string> Unaffected);

public sealed class MissingDependencyException : Exception
{
    public string ItemId { get; }
    public string DependencyId { get; }
}

public sealed class DependencyCycleException : Exception
{
    public IReadOnlyList<string> Path { get; }
}

public sealed class DependencyPlanner
{
    public void AddItem(string id, int priority = 0, string? group = null)
    public bool RemoveItem(string id)
    public void AddDependency(string itemId, string dependencyId)
    public bool RemoveDependency(string itemId, string dependencyId)
    public IReadOnlyList<string> BuildPlan()
    public PlanUpdate BuildPlanForChanges(IReadOnlyCollection<string> changedItemIds)
}
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- Item ids must be non-empty after trimming.
- `BuildPlan` returns item ids in dependency order: dependencies appear before the items that depend on them.
- Among ready items with no ordering constraint, use higher `Priority` first, then ordinal id order.
- `AddDependency(itemId, dependencyId)` means `itemId` cannot run until `dependencyId` has run.
- Dependencies may be registered before the dependency item exists, but `BuildPlan` must throw `MissingDependencyException` if a dependency is still missing.
- Cycles must be rejected with `DependencyCycleException` and a diagnostic path that includes the repeated item.
- Removing an item must also remove its outgoing and incoming dependency edges.
- `BuildPlanForChanges` returns the full current order plus affected and unaffected item ids. Affected ids are the changed ids that exist in the planner plus all transitive dependents, returned in plan order.
