using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void keeps_only_even_numbers()
    {
        CollectionAssert.AreEqual(new[] { 2, 4, 0 }, global::Solution.Execute(new[] { 1, 2, 3, 4, 5, 0 }).ToArray());
    }

    [TestMethod]
    public void preserves_original_order()
    {
        CollectionAssert.AreEqual(new[] { 8, 2, -4 }, global::Solution.Execute(new[] { 8, 3, 2, -4 }).ToArray());
    }

    [TestMethod]
    public void returns_empty_when_no_even_numbers()
    {
        Assert.AreEqual(0, global::Solution.Execute(new[] { 1, 3, 5 }).Count);
    }
}
