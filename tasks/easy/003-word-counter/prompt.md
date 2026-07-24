Write a public `Item` class and a public class named `Solution`.

`Item` must expose these public properties:

```csharp
public string Category { get; set; }
public decimal Amount { get; set; }
```

`Solution` must expose two methods:

**Word Counter:**

```csharp
public static Dictionary<string, int> CountWords(string text)
```

Count words in `text` and return a dictionary from normalized word to count.

Rules:
- A word is a consecutive run of letters or digits.
- Matching is case-insensitive; dictionary keys must be lowercase invariant.
- Punctuation and whitespace are separators.

**Category Aggregation:**

```csharp
public static Dictionary<string, decimal> AggregateByCategory(IEnumerable<Item> items)
```

Return the sum of `Amount` values for each category.

Rules:
- Trim category names before grouping.
- Ignore items whose category is null, empty, or whitespace.
- Preserve category casing after trimming.

Also include this stub method so the file follows the benchmark contract:

```csharp
public static bool Execute() => true;
```
