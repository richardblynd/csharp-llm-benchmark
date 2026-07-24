using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void returns_sum_of_all_numbers()
    {
        var result = global::Solution.Execute(new[] { 1, 2, 3, 4 });
        Assert.AreEqual(10, result.Sum);
    }

    [TestMethod]
    public void sums_negative_numbers()
    {
        var result = global::Solution.Execute(new[] { -1, -2, 3 });
        Assert.AreEqual(0, result.Sum);
    }

    [TestMethod]
    public void keeps_only_even_numbers()
    {
        var result = global::Solution.Execute(new[] { 1, 2, 3, 4, 5, 6 });
        CollectionAssert.AreEqual(new[] { 2, 4, 6 }, result.Evens.ToArray());
    }

    [TestMethod]
    public void preserves_original_order_in_evens()
    {
        var result = global::Solution.Execute(new[] { 8, 1, 4, 3, 6 });
        CollectionAssert.AreEqual(new[] { 8, 4, 6 }, result.Evens.ToArray());
    }

    [TestMethod]
    public void treats_zero_as_even()
    {
        var result = global::Solution.Execute(new[] { -1, 0, 3 });
        Assert.IsTrue(result.Evens.Contains(0));
    }

    [TestMethod]
    public void returns_zero_and_empty_for_empty_list()
    {
        var result = global::Solution.Execute(Array.Empty<int>());
        Assert.AreEqual(0, result.Sum);
        Assert.AreEqual(0, result.Evens.Count);
    }
}
