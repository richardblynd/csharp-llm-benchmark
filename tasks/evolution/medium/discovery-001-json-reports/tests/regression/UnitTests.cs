using Reports;
using Microsoft.VisualStudio.TestTools.UnitTesting;
[TestClass] public class RegressionTests
{
    [TestMethod] public void old_text_output_and_empty_output_are_preserved()
    {var s=new ReportService();Assert.AreEqual("a: 1.5\nb: -2",s.Export("TEXT",new[]{new ReportRow("a",1.5m),new ReportRow("b",-2)}));Assert.AreEqual("",s.Export("text",Array.Empty<ReportRow>()));}
    [TestMethod] public void old_csv_quoting_and_empty_output_are_preserved()
    {var s=new ReportService();Assert.AreEqual("name,value\n\"a\"\"b\",2.5",s.Export("csv",new[]{new ReportRow("a\"b",2.5m)}));Assert.AreEqual("name,value\n",s.Export("csv",Array.Empty<ReportRow>()));}
    [TestMethod] public void old_null_and_unknown_format_validation_is_preserved()
    {var s=new ReportService();Assert.ThrowsException<ArgumentNullException>(()=>s.Export(null!,Array.Empty<ReportRow>()));Assert.ThrowsException<ArgumentNullException>(()=>s.Export("text",null!));Assert.ThrowsException<ArgumentException>(()=>s.Export("missing",Array.Empty<ReportRow>()));}
    [TestMethod] public void old_constructor_validation_is_preserved()
    {Assert.ThrowsException<ArgumentNullException>(()=>new ReportService((IReportFormatter[])null!));Assert.ThrowsException<ArgumentNullException>(()=>new ReportService(new IReportFormatter[]{null!}));Assert.ThrowsException<ArgumentException>(()=>new ReportService(new TextFormatter(),new TextFormatter()));}
    [TestMethod] public void old_custom_formatters_are_snapshotted_and_used()
    {var formats=new IReportFormatter[]{new Custom()};var s=new ReportService(formats);formats[0]=new TextFormatter();Assert.AreEqual("custom:2",s.Export("CUSTOM",new[]{new ReportRow("a",1),new ReportRow("b",2)}));}
    private sealed class Custom:IReportFormatter{public string Format=>"custom";public string Render(IReadOnlyList<ReportRow> rows)=>"custom:"+rows.Count;}
}
