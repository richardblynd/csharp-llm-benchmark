using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void indexes_basic_documents()
    {
        var index = new global::InvertedIndex();
        index.AddDocument("doc-1", "alpha beta");
        index.AddDocument("doc-2", "beta gamma");

        CollectionAssert.AreEqual(new[] { "doc-1", "doc-2" }, index.Search("beta").ToArray());
    }

    [TestMethod]
    public void normalizes_case_and_punctuation()
    {
        var index = new global::InvertedIndex();
        index.AddDocument("a", "Hello, WORLD!");
        index.AddDocument("b", "world-class hello?");

        CollectionAssert.AreEqual(new[] { "a", "b" }, index.Search("hello").ToArray());
        CollectionAssert.AreEqual(new[] { "a", "b" }, index.Search("WORLD").ToArray());
    }

    [TestMethod]
    public void avoids_duplicate_document_ids_per_term()
    {
        var index = new global::InvertedIndex();
        index.AddDocument("doc", "repeat repeat repeat");

        CollectionAssert.AreEqual(new[] { "doc" }, index.Search("repeat").ToArray());
    }

    [TestMethod]
    public void searches_multiple_terms_by_intersection()
    {
        var index = new global::InvertedIndex();
        index.AddDocument("a", "red green blue");
        index.AddDocument("b", "red blue");
        index.AddDocument("c", "red green");

        CollectionAssert.AreEqual(new[] { "a" }, index.SearchAll(new[] { "red", "green", "blue" }).ToArray());
    }

    [TestMethod]
    public void returns_empty_for_missing_terms()
    {
        var index = new global::InvertedIndex();
        index.AddDocument("a", "known");

        Assert.AreEqual(0, index.Search("missing").Count);
    }
}
