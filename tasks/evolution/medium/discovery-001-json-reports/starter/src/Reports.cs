using System.Globalization;
namespace Reports;
public sealed record ReportRow(string Name, decimal Value);
public interface IReportFormatter { string Format { get; } string Render(IReadOnlyList<ReportRow> rows); }
public sealed class TextFormatter : IReportFormatter
{
    public string Format => "text";
    public string Render(IReadOnlyList<ReportRow> rows) => string.Join("\n",rows.Select(r => r.Name + ": " + r.Value.ToString(CultureInfo.InvariantCulture)));
}
public sealed class CsvFormatter : IReportFormatter
{
    public string Format => "csv";
    public string Render(IReadOnlyList<ReportRow> rows) => "name,value\n" + string.Join("\n",rows.Select(r => "\"" + r.Name.Replace("\"","\"\"") + "\"," + r.Value.ToString(CultureInfo.InvariantCulture)));
}
public sealed class ReportService
{
    private readonly Dictionary<string,IReportFormatter> formatters;
    public ReportService() : this(new TextFormatter(),new CsvFormatter()) { }
    public ReportService(params IReportFormatter[] formatters)
    {
        ArgumentNullException.ThrowIfNull(formatters);
        this.formatters = new(StringComparer.OrdinalIgnoreCase);
        foreach(var formatter in formatters)
        { ArgumentNullException.ThrowIfNull(formatter); this.formatters.Add(formatter.Format,formatter); }
    }
    public string Export(string format,IEnumerable<ReportRow> rows)
    {
        ArgumentNullException.ThrowIfNull(format);ArgumentNullException.ThrowIfNull(rows);
        if(!formatters.TryGetValue(format,out var formatter)) throw new ArgumentException("Unknown format.",nameof(format));
        return formatter.Render(rows.ToArray());
    }
}
