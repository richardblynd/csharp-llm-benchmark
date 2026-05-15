Write a public class named `InvertedIndex`.

Required public API:

```csharp
public void AddDocument(string documentId, string text)
public IReadOnlyList<string> Search(string term)
public IReadOnlyList<string> SearchAll(IEnumerable<string> terms)
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- Terms are case-insensitive.
- Treat letters and digits as term characters. Treat punctuation and whitespace as separators.
- A document id may appear at most once in the result for a term, even when the term appears many times in the document.
- Return document ids sorted ordinally.
- `SearchAll` returns the intersection of documents containing every normalized term.
- Null document ids, null text, null terms and blank document ids are invalid and should throw an argument exception.
