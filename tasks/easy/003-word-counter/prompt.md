Write a public class named `Solution` with this method:

```csharp
public static Dictionary<string, int> Execute(string text)
```

Count words in `text` and return a dictionary from normalized word to count.

Rules:
- A word is a consecutive run of letters or digits.
- Matching is case-insensitive; dictionary keys must be lowercase invariant.
- Punctuation and whitespace are separators.
- Do not include a namespace.
- Do not use external libraries.
