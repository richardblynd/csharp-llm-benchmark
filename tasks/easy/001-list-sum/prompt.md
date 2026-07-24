Write a public `ListOperationsResult` class and a public class named `Solution`.

`ListOperationsResult` must expose these public properties:

```csharp
public int Sum { get; set; }
public IReadOnlyList<int> Evens { get; set; }
```

`Solution` must expose this method:

```csharp
public static ListOperationsResult Execute(IReadOnlyList<int> numbers)
```

Return a result containing both the sum of all integers and the filtered list of even numbers.

Rules:
- Treat an empty list as a sum of `0` with an empty evens collection.
- Zero is considered even.
- Preserve the original order in the evens list.
