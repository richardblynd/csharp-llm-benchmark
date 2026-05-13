Write a public `StatisticsResult` class and a public class named `Solution`.

`StatisticsResult` must expose these public properties:

```csharp
public int Count { get; set; }
public double Average { get; set; }
public double Min { get; set; }
public double Max { get; set; }
```

`Solution` must expose this method:

```csharp
public static StatisticsResult Execute(IReadOnlyList<double> values)
```

Return count, arithmetic average, minimum, and maximum for `values`.

Rules:
- If `values` is empty, return zero for all properties.
- Do not include a namespace.
- Do not use external libraries.
