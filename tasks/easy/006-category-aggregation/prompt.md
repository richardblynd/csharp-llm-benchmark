Write a public `Item` class and a public class named `Solution`.

`Item` must expose these public properties:

```csharp
public string Category { get; set; }
public decimal Amount { get; set; }
```

`Solution` must expose this method:

```csharp
public static Dictionary<string, decimal> Execute(IEnumerable<Item> items)
```

Return the sum of `Amount` values for each category.

Rules:
- Trim category names before grouping.
- Ignore items whose category is null, empty, or whitespace.
- Preserve category casing after trimming.
- Do not include a namespace.
- Do not use external libraries.
