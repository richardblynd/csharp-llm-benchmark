Write a public class named `Solution` with this method:

```csharp
public static string Execute(int totalMinutes)
```

Convert `totalMinutes` into a duration string formatted as `H:MM`, where `H` is
the total number of whole hours and `MM` is minutes padded to two digits.

Rules:
- `0` returns `0:00`.
- Negative values must throw `ArgumentOutOfRangeException`.
