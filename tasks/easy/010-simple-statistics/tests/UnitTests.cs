using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void returns_count_average_min_and_max()
    {
        var result = global::Solution.Execute(new[] { 2.0, 4.0, 6.0, 8.0 });
        Assert.AreEqual(4, result.Count);
        Assert.AreEqual(5.0, result.Average, 0.000001);
        Assert.AreEqual(2.0, result.Min, 0.000001);
        Assert.AreEqual(8.0, result.Max, 0.000001);
    }

    [TestMethod]
    public void handles_single_value()
    {
        var result = global::Solution.Execute(new[] { 12.5 });
        Assert.AreEqual(1, result.Count);
        Assert.AreEqual(12.5, result.Average, 0.000001);
        Assert.AreEqual(12.5, result.Min, 0.000001);
        Assert.AreEqual(12.5, result.Max, 0.000001);
    }

    [TestMethod]
    public void handles_negative_values()
    {
        var result = global::Solution.Execute(new[] { -10.0, 5.0, -1.0 });
        Assert.AreEqual(-2.0, result.Average, 0.000001);
        Assert.AreEqual(-10.0, result.Min, 0.000001);
        Assert.AreEqual(5.0, result.Max, 0.000001);
    }

    [TestMethod]
    public void returns_zeroes_for_empty_input()
    {
        var result = global::Solution.Execute(Array.Empty<double>());
        Assert.AreEqual(0, result.Count);
        Assert.AreEqual(0.0, result.Average, 0.000001);
        Assert.AreEqual(0.0, result.Min, 0.000001);
        Assert.AreEqual(0.0, result.Max, 0.000001);
    }
}
