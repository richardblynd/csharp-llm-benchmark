using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void sums_values_per_category()
    {
        var items = new[]
        {
            new global::Item { Category = "Food", Amount = 10m },
            new global::Item { Category = "Books", Amount = 8m },
            new global::Item { Category = "Food", Amount = 2.5m }
        };
        var result = global::Solution.Execute(items);
        Assert.AreEqual(12.5m, result["Food"]);
        Assert.AreEqual(8m, result["Books"]);
    }

    [TestMethod]
    public void trims_category_names()
    {
        var items = new[]
        {
            new global::Item { Category = "  Tools", Amount = 3m },
            new global::Item { Category = "Tools  ", Amount = 4m }
        };
        Assert.AreEqual(7m, global::Solution.Execute(items)["Tools"]);
    }

    [TestMethod]
    public void ignores_blank_categories()
    {
        var items = new[]
        {
            new global::Item { Category = " ", Amount = 99m },
            new global::Item { Category = "", Amount = 99m },
            new global::Item { Category = "Valid", Amount = 1m }
        };
        var result = global::Solution.Execute(items);
        Assert.AreEqual(1, result.Count);
        Assert.AreEqual(1m, result["Valid"]);
    }

    [TestMethod]
    public void returns_empty_dictionary_for_empty_input()
    {
        Assert.AreEqual(0, global::Solution.Execute(Array.Empty<global::Item>()).Count);
    }
}
