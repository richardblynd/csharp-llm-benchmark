using System.Text.Json;
namespace Reports;
public sealed class JsonFormatter : IReportFormatter
{
    public string Format => "json";
    public string Render(IReadOnlyList<ReportRow> rows) => JsonSerializer.Serialize(rows.Select(r => new { name=r.Name,value=r.Value }));
}
