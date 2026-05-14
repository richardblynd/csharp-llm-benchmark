using System;
using System.Collections.Generic;
using System.Linq;

public sealed record PlannedItem(string Id, int Priority = 0, string? Group = null);

public sealed record PlanUpdate(
    IReadOnlyList<string> Order,
    IReadOnlyList<string> Affected,
    IReadOnlyList<string> Unaffected);

public sealed class MissingDependencyException : Exception
{
    public MissingDependencyException(string itemId, string dependencyId)
        : base($"Item '{itemId}' depends on missing item '{dependencyId}'.")
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
        : base("The dependency graph contains a cycle.")
    {
        Path = path;
    }

    public IReadOnlyList<string> Path { get; }
}

public sealed class DependencyPlanner
{
    private readonly Dictionary<string, PlannedItem> items = new(StringComparer.Ordinal);
    private readonly Dictionary<string, HashSet<string>> dependencies = new(StringComparer.Ordinal);

    public void AddItem(string id, int priority = 0, string? group = null)
    {
        var normalized = NormalizeId(id, nameof(id));
        items[normalized] = new PlannedItem(normalized, priority, group);
        dependencies.TryAdd(normalized, new HashSet<string>(StringComparer.Ordinal));
    }

    public bool RemoveItem(string id)
    {
        var normalized = NormalizeId(id, nameof(id));
        var removed = items.Remove(normalized);
        dependencies.Remove(normalized);
        foreach (var set in dependencies.Values)
        {
            set.Remove(normalized);
        }

        return removed;
    }

    public void AddDependency(string itemId, string dependencyId)
    {
        var item = NormalizeId(itemId, nameof(itemId));
        var dependency = NormalizeId(dependencyId, nameof(dependencyId));
        if (item == dependency)
        {
            throw new ArgumentException("An item cannot depend on itself.", nameof(dependencyId));
        }

        if (!dependencies.TryGetValue(item, out var set))
        {
            set = new HashSet<string>(StringComparer.Ordinal);
            dependencies[item] = set;
        }

        set.Add(dependency);
    }

    public bool RemoveDependency(string itemId, string dependencyId)
    {
        var item = NormalizeId(itemId, nameof(itemId));
        var dependency = NormalizeId(dependencyId, nameof(dependencyId));
        return dependencies.TryGetValue(item, out var set) && set.Remove(dependency);
    }

    public IReadOnlyList<string> BuildPlan()
    {
        ValidateMissingDependencies();

        var remainingDependencies = items.Keys.ToDictionary(
            id => id,
            id => dependencies.TryGetValue(id, out var set)
                ? new HashSet<string>(set, StringComparer.Ordinal)
                : new HashSet<string>(StringComparer.Ordinal),
            StringComparer.Ordinal);
        var dependents = BuildDependents();
        var result = new List<string>();
        var ready = new HashSet<string>(remainingDependencies.Where(pair => pair.Value.Count == 0).Select(pair => pair.Key), StringComparer.Ordinal);

        while (ready.Count > 0)
        {
            var next = ready
                .OrderByDescending(id => items[id].Priority)
                .ThenBy(id => id, StringComparer.Ordinal)
                .First();
            ready.Remove(next);
            result.Add(next);

            if (!dependents.TryGetValue(next, out var children))
            {
                continue;
            }

            foreach (var child in children)
            {
                if (!remainingDependencies.TryGetValue(child, out var childDependencies))
                {
                    continue;
                }

                childDependencies.Remove(next);
                if (childDependencies.Count == 0)
                {
                    ready.Add(child);
                }
            }
        }

        if (result.Count != items.Count)
        {
            throw new DependencyCycleException(FindCyclePath());
        }

        return result;
    }

    public PlanUpdate BuildPlanForChanges(IReadOnlyCollection<string> changedItemIds)
    {
        ArgumentNullException.ThrowIfNull(changedItemIds);
        var order = BuildPlan();
        var dependents = BuildDependents();
        var affected = new HashSet<string>(StringComparer.Ordinal);
        var queue = new Queue<string>();

        foreach (var id in changedItemIds.Select(id => NormalizeId(id, nameof(changedItemIds))).Where(items.ContainsKey))
        {
            if (affected.Add(id))
            {
                queue.Enqueue(id);
            }
        }

        while (queue.Count > 0)
        {
            var current = queue.Dequeue();
            if (!dependents.TryGetValue(current, out var children))
            {
                continue;
            }

            foreach (var child in children)
            {
                if (affected.Add(child))
                {
                    queue.Enqueue(child);
                }
            }
        }

        var orderedAffected = order.Where(affected.Contains).ToArray();
        var unaffected = order.Where(id => !affected.Contains(id)).ToArray();
        return new PlanUpdate(order, orderedAffected, unaffected);
    }

    private void ValidateMissingDependencies()
    {
        foreach (var (item, set) in dependencies)
        {
            if (!items.ContainsKey(item))
            {
                throw new MissingDependencyException(item, item);
            }

            foreach (var dependency in set)
            {
                if (!items.ContainsKey(dependency))
                {
                    throw new MissingDependencyException(item, dependency);
                }
            }
        }
    }

    private Dictionary<string, HashSet<string>> BuildDependents()
    {
        var dependents = items.Keys.ToDictionary(id => id, _ => new HashSet<string>(StringComparer.Ordinal), StringComparer.Ordinal);
        foreach (var (item, set) in dependencies)
        {
            foreach (var dependency in set)
            {
                if (dependents.TryGetValue(dependency, out var children))
                {
                    children.Add(item);
                }
            }
        }

        return dependents;
    }

    private IReadOnlyList<string> FindCyclePath()
    {
        var visiting = new HashSet<string>(StringComparer.Ordinal);
        var visited = new HashSet<string>(StringComparer.Ordinal);
        var stack = new List<string>();

        foreach (var id in items.Keys.OrderBy(id => id, StringComparer.Ordinal))
        {
            var path = Visit(id, visiting, visited, stack);
            if (path.Count > 0)
            {
                return path;
            }
        }

        return Array.Empty<string>();
    }

    private IReadOnlyList<string> Visit(string id, HashSet<string> visiting, HashSet<string> visited, List<string> stack)
    {
        if (visited.Contains(id))
        {
            return Array.Empty<string>();
        }

        if (visiting.Contains(id))
        {
            var start = stack.IndexOf(id);
            var cycle = stack.Skip(start).ToList();
            cycle.Add(id);
            return cycle;
        }

        visiting.Add(id);
        stack.Add(id);
        foreach (var dependency in dependencies.GetValueOrDefault(id, new HashSet<string>(StringComparer.Ordinal)).OrderBy(value => value, StringComparer.Ordinal))
        {
            var path = Visit(dependency, visiting, visited, stack);
            if (path.Count > 0)
            {
                return path;
            }
        }

        stack.RemoveAt(stack.Count - 1);
        visiting.Remove(id);
        visited.Add(id);
        return Array.Empty<string>();
    }

    private static string NormalizeId(string id, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(id))
        {
            throw new ArgumentException("Item ids must be non-empty.", parameterName);
        }

        return id.Trim();
    }
}
