using Reports;
using System.Globalization;
using System.Text.Json;
using Microsoft.VisualStudio.TestTools.UnitTesting;
[TestClass] public class FeatureTests
{
    [TestMethod] public void json_is_integrated_in_the_default_service()
    {using var d=JsonDocument.Parse(new ReportService().Export("JsOn",new[]{new ReportRow("a",2.5m)}));var row=d.RootElement[0];Assert.AreEqual("a",row.GetProperty("name").GetString());Assert.AreEqual(2.5m,row.GetProperty("value").GetDecimal());Assert.AreEqual(2,row.EnumerateObject().Count());}
    [TestMethod] public void json_formatter_implements_the_existing_contract()
    {IReportFormatter f=new JsonFormatter();Assert.AreEqual("json",f.Format);using var d=JsonDocument.Parse(new ReportService(f).Export("json",Array.Empty<ReportRow>()));Assert.AreEqual(0,d.RootElement.GetArrayLength());}
    [TestMethod] public void json_preserves_order_duplicates_and_escaping()
    {var name=string.Concat("quotes",(char)34,(char)92,(char)10,(char)9,(char)231,(char)27700);using var d=JsonDocument.Parse(new ReportService().Export("json",new[]{new ReportRow(name,-4),new ReportRow(name,8)}));Assert.AreEqual(2,d.RootElement.GetArrayLength());Assert.AreEqual(name,d.RootElement[0].GetProperty("name").GetString());Assert.AreEqual(-4m,d.RootElement[0].GetProperty("value").GetDecimal());Assert.AreEqual(8m,d.RootElement[1].GetProperty("value").GetDecimal());}
    [TestMethod] public void json_numbers_are_independent_of_culture()
    {var old=CultureInfo.CurrentCulture;try{CultureInfo.CurrentCulture=CultureInfo.GetCultureInfo("pt-BR");using var d=JsonDocument.Parse(new ReportService().Export("json",new[]{new ReportRow("x",1234.56m)}));Assert.AreEqual(JsonValueKind.Number,d.RootElement[0].GetProperty("value").ValueKind);Assert.AreEqual(1234.56m,d.RootElement[0].GetProperty("value").GetDecimal());}finally{CultureInfo.CurrentCulture=old;}}
    [TestMethod] public void json_registration_does_not_bypass_custom_selection()
    {var s=new ReportService(new TextFormatter());Assert.ThrowsException<ArgumentException>(()=>s.Export("json",Array.Empty<ReportRow>()));var rows=new[]{new ReportRow("x",1)};var json=new ReportService().Export("json",rows);Assert.AreEqual("x",rows[0].Name);Assert.IsTrue(json.Length>0);}
}
