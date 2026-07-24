Model office devices following the Interface Segregation Principle.

Required public API:

```csharp
public interface IPrinter
{
    string Print(string document);
}

public interface IScanner
{
    string Scan(string document);
}

public interface IFaxSender
{
    string SendFax(string document, string number);
}

public sealed class BasicPrinter
public sealed class MultifunctionPrinter

public sealed class PrintService
{
    public PrintService(IPrinter printer)
    public string Print(string document)
}

public sealed class ScanService
{
    public ScanService(IScanner scanner)
    public string Scan(string document)
}
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- Keep printing, scanning and faxing in separate interfaces.
- `BasicPrinter` must implement only printing.
- `MultifunctionPrinter` must implement printing, scanning and fax sending.
- `PrintService` must depend only on `IPrinter`.
- `ScanService` must depend only on `IScanner`.
- `BasicPrinter.Print("hello")` should return `printed: hello`.
- Do not add a broad interface that forces unsupported operations.
