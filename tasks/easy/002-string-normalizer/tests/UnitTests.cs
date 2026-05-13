using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void trims_outer_whitespace()
    {
        Assert.AreEqual("hello", global::Solution.Execute("  Hello  "));
    }

    [TestMethod]
    public void collapses_internal_whitespace()
    {
        Assert.AreEqual("hello world from c#", global::Solution.Execute("Hello\t  World\nfrom   C#"));
    }

    [TestMethod]
    public void lowercases_invariant_text()
    {
        Assert.AreEqual("mixed case", global::Solution.Execute("  MIXED Case  "));
    }
}
