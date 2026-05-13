using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void sums_positive_numbers()
    {
        Assert.AreEqual(15, global::Solution.Execute(new[] { 1, 2, 3, 4, 5 }));
    }

    [TestMethod]
    public void sums_negative_numbers()
    {
        Assert.AreEqual(-12, global::Solution.Execute(new[] { -2, -4, -6 }));
    }

    [TestMethod]
    public void returns_zero_for_empty_list()
    {
        Assert.AreEqual(0, global::Solution.Execute(Array.Empty<int>()));
    }
}
