using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void counts_repeated_words()
    {
        var result = global::Solution.Execute("apple apple banana");
        Assert.AreEqual(2, result["apple"]);
        Assert.AreEqual(1, result["banana"]);
    }

    [TestMethod]
    public void ignores_punctuation()
    {
        var result = global::Solution.Execute("one, two. one!");
        Assert.AreEqual(2, result["one"]);
        Assert.AreEqual(1, result["two"]);
    }

    [TestMethod]
    public void lowercases_keys()
    {
        var result = global::Solution.Execute("Cat cAt CAT");
        Assert.AreEqual(3, result["cat"]);
        Assert.IsFalse(result.ContainsKey("CAT"));
    }

    [TestMethod]
    public void returns_empty_dictionary_for_blank_text()
    {
        Assert.AreEqual(0, global::Solution.Execute(" \t\n ").Count);
    }
}
