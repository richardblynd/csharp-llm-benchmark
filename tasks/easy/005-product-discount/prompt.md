Write a public `Product` class and a public class named `Solution`.

`Product` must expose these public properties:

```csharp
public string Name { get; set; }
public decimal Price { get; set; }
public decimal DiscountPercentage { get; set; }
```

`Solution` must expose this method:

```csharp
public static decimal Execute(Product product)
```

Return the final price after applying `DiscountPercentage` to `Price`. Round the
result to two decimal places using `MidpointRounding.AwayFromZero`. A discount of
`100` returns `0`.

Rules:
- Do not include a namespace.
- Do not use external libraries.
