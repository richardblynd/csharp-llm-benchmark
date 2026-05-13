Write a public `Person` class and a public class named `Solution`.

`Person` must expose these public properties:

```csharp
public string FirstName { get; set; }
public string LastName { get; set; }
public int Age { get; set; }
```

`Solution` must expose this method:

```csharp
public static List<Person> Execute(IEnumerable<Person> people)
```

Return a new list sorted by `LastName` ascending, then `FirstName` ascending, then
`Age` descending.

Rules:
- Use ordinal string comparison.
- Do not mutate the input collection.
- Do not include a namespace.
- Do not use external libraries.
