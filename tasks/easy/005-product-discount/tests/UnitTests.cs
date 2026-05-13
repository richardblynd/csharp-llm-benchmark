using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void applies_percentage_discount()
    {
        var product = new global::Product { Name = "Book", Price = 100m, DiscountPercentage = 15m };
        Assert.AreEqual(85m, global::Solution.Execute(product));
    }

    [TestMethod]
    public void rounds_to_two_decimal_places()
    {
        var product = new global::Product { Name = "Pen", Price = 10m, DiscountPercentage = 33.333m };
        Assert.AreEqual(6.67m, global::Solution.Execute(product));
    }

    [TestMethod]
    public void handles_zero_discount()
    {
        var product = new global::Product { Name = "Bag", Price = 42.50m, DiscountPercentage = 0m };
        Assert.AreEqual(42.50m, global::Solution.Execute(product));
    }

    [TestMethod]
    public void caps_full_discount_at_zero()
    {
        var product = new global::Product { Name = "Gift", Price = 12.99m, DiscountPercentage = 100m };
        Assert.AreEqual(0m, global::Solution.Execute(product));
    }
}
