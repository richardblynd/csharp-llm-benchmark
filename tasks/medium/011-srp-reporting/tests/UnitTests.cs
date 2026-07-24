using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    private sealed class MemorySink : global::IReportSink
    {
        public readonly List<string> Writes = new();
        public void Write(string content) => Writes.Add(content);
    }

    [TestMethod]
    public void calculates_report_data_correctly()
    {
        var summary = new global::ReportCalculator().Calculate(new[]
        {
            new global::SalesRecord("a", 10m),
            new global::SalesRecord("b", 20m)
        });

        Assert.AreEqual(2, summary.Count);
        Assert.AreEqual(30m, summary.Total);
        Assert.AreEqual(15m, summary.Average);
    }

    [TestMethod]
    public void formats_output_without_mixing_calculation()
    {
        var text = new global::PlainTextReportFormatter().Format(new global::ReportSummary(2, 30m, 15m));

        StringAssert.Contains(text, "Count: 2");
        StringAssert.Contains(text, "Total: 30");
        StringAssert.Contains(text, "Average: 15");
    }

    [TestMethod]
    public void isolates_output_destination_with_contract()
    {
        Assert.IsTrue(typeof(global::IReportSink).IsInterface);
        var constructor = typeof(global::ReportService).GetConstructors().Single();

        Assert.IsTrue(constructor.GetParameters().Any(p => p.ParameterType == typeof(global::IReportSink)));
    }

    [TestMethod]
    public void allows_each_responsibility_to_be_tested_separately()
    {
        var sink = new MemorySink();
        var service = new global::ReportService(new global::ReportCalculator(), new global::PlainTextReportFormatter(), sink);

        service.GenerateAndWrite(new[] { new global::SalesRecord("x", 5m) });

        Assert.AreEqual(1, sink.Writes.Count);
        StringAssert.Contains(sink.Writes[0], "Total: 5");
    }
}
