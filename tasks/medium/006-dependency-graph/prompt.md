Write a public class named `DependencyGraph`.

Required public API:

```csharp
public void AddItem(string item)
public void AddDependency(string item, string dependsOn)
public IReadOnlyList<string> GetExecutionOrder()
```

Rules:
- Do not include a namespace.
- Do not use external libraries.
- All code, public identifiers, exception messages and comments must be written in English.
- `AddDependency("app", "lib")` means `lib` must appear before `app`.
- Throw an argument exception if a dependency references an item that has not been added.
- Throw `InvalidOperationException` from `GetExecutionOrder` when the graph contains a cycle.
- When more than one item is ready, choose the ordinally smallest item to keep output deterministic.
- Empty graphs return an empty list.
