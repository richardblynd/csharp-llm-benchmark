Implement a record importer following the Dependency Inversion Principle.

Required public API:

```csharp
public sealed class ImportRecord
{
    public ImportRecord(string id, string value)
    public string Id { get; }
    public string Value { get; }
}

public sealed class ImportResult
{
    public int ImportedCount { get; }
    public int InvalidCount { get; }
    public IReadOnlyList<string> Errors { get; }
}

public interface IRecordReader
{
    IReadOnlyList<ImportRecord> Read();
}

public interface IRecordValidator
{
    string? Validate(ImportRecord record);
}

public interface IRecordRepository
{
    void Save(ImportRecord record);
}

public sealed class RecordImporter
{
    public RecordImporter(IRecordReader reader, IRecordValidator validator, IRecordRepository repository)
    public ImportResult Import()
}
```

Rules:
- Do not include a namespace.
- Do not use external libraries.
- All code, public identifiers, exception messages and comments must be written in English.
- `RecordImporter` must depend on abstractions for reading, validation and persistence.
- It must read all records, validate each record, save only valid records and continue after invalid records.
- `ImportResult` must expose imported count, invalid count and validation error messages.
- The flow must be testable with in-memory fake implementations.
