using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void counts_repeated_words()
    {
        var result = global::Solution.CountWords("apple apple banana");
        Assert.AreEqual(2, result["apple"]);
        Assert.AreEqual(1, result["banana"]);
    }

    [TestMethod]
    public void ignores_punctuation()
    {
        var result = global::Solution.CountWords("one, two. one!");
        Assert.AreEqual(2, result["one"]);
        Assert.AreEqual(1, result["two"]);
    }

    [TestMethod]
    public void lowercases_keys()
    {
        var result = global::Solution.CountWords("Cat cAt CAT");
        Assert.AreEqual(3, result["cat"]);
        Assert.IsFalse(result.ContainsKey("CAT"));
    }

    [TestMethod]
    public void returns_empty_dictionary_for_blank_text()
    {
        Assert.AreEqual(0, global::Solution.CountWords(" \t\n ").Count);
    }

    [TestMethod]
    public void sums_values_per_category()
    {
        var items = new[]
        {
            new global::Item { Category = "Food", Amount = 10m },
            new global::Item { Category = "Books", Amount = 8m },
            new global::Item { Category = "Food", Amount = 2.5m }
        };
        var result = global::Solution.AggregateByCategory(items);
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
        Assert.AreEqual(7m, global::Solution.AggregateByCategory(items)["Tools"]);
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
        var result = global::Solution.AggregateByCategory(items);
        Assert.AreEqual(1, result.Count);
        Assert.AreEqual(1m, result["Valid"]);
    }

    [TestMethod]
    public void returns_empty_dictionary_for_empty_input()
    {
        Assert.AreEqual(0, global::Solution.AggregateByCategory(Array.Empty<global::Item>()).Count);
    }
}
