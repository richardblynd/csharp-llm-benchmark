using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void formats_less_than_one_hour()
    {
        Assert.AreEqual("0:45", global::Solution.Execute(45));
    }

    [TestMethod]
    public void formats_multiple_hours()
    {
        Assert.AreEqual("27:15", global::Solution.Execute(1635));
    }

    [TestMethod]
    public void pads_minutes_with_zero()
    {
        Assert.AreEqual("2:05", global::Solution.Execute(125));
    }

    [TestMethod]
    public void rejects_negative_minutes()
    {
        Assert.ThrowsException<ArgumentOutOfRangeException>(() => global::Solution.Execute(-1));
    }
}
