Write a public static class named `IbanValidator`.

Required public API:

```csharp
public static bool IsValid(string? iban)
public static string Format(string iban)
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- `IsValid` removes spaces, uppercases letters, validates that the normalized value has 15 to 34 alphanumeric characters, moves the first four characters to the end, converts A-Z to 10-35 and checks that the resulting decimal number has remainder 1 when divided by 97.
- Compute mod-97 incrementally so very long valid IBANs do not overflow numeric types.
- `Format` returns the normalized IBAN grouped in blocks of four characters separated by a single space.
- `Format` throws `ArgumentException` if the IBAN is invalid.
- Null, empty or whitespace-only values are invalid.
