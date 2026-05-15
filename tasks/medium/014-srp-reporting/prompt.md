Implement a small reporting module that follows the Single Responsibility Principle.

Required public API:

```csharp
public sealed class SalesRecord
{
    public SalesRecord(string id, decimal amount)
    public string Id { get; }
    public decimal Amount { get; }
}

public sealed class ReportSummary
{
    public ReportSummary(int count, decimal total, decimal average)
    public int Count { get; }
    public decimal Total { get; }
    public decimal Average { get; }
}

public sealed class ReportCalculator
{
    public ReportSummary Calculate(IEnumerable<SalesRecord> records)
}

public interface IReportFormatter
{
    string Format(ReportSummary summary);
}

public sealed class PlainTextReportFormatter
public interface IReportSink
{
    void Write(string content);
}

public sealed class ReportService
{
    public ReportService(ReportCalculator calculator, IReportFormatter formatter, IReportSink sink)
    public void GenerateAndWrite(IEnumerable<SalesRecord> records)
}
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- `ReportCalculator` calculates count, total and average from sales records.
- `PlainTextReportFormatter` formats a summary as text that includes `Count: {count}`, `Total: {total}` and `Average: {average}`.
- `IReportSink` receives already formatted text.
- `ReportService` composes calculator, formatter and sink to generate and write a report.
- Keep calculation, formatting and output as separate responsibilities.
