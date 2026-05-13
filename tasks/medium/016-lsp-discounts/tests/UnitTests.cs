using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    private sealed class HalfRule : global::IDiscountRule
    {
        public decimal CalculateDiscount(decimal price) => price / 2m;
    }

    [TestMethod]
    public void applies_concrete_rules_correctly()
    {
        Assert.AreEqual(10m, new global::PercentageDiscountRule(0.10m).CalculateDiscount(100m));
        Assert.AreEqual(5m, new global::FixedAmountDiscountRule(5m).CalculateDiscount(100m));
        Assert.AreEqual(0m, new global::NoDiscountRule().CalculateDiscount(100m));
    }

    [TestMethod]
    public void maintains_common_contract_invariants()
    {
        global::IDiscountRule[] rules =
        {
            new global::PercentageDiscountRule(1.5m),
            new global::FixedAmountDiscountRule(500m),
            new global::NoDiscountRule()
        };

        foreach (var rule in rules)
        {
            var discount = rule.CalculateDiscount(100m);
            Assert.IsTrue(discount >= 0m);
            Assert.IsTrue(discount <= 100m);
        }
    }

    [TestMethod]
    public void allows_rule_substitution_in_consumer()
    {
        var service = new global::DiscountService(new HalfRule());

        Assert.AreEqual(50m, service.GetFinalPrice(100m));
    }

    [TestMethod]
    public void handles_boundary_inputs_consistently()
    {
        var service = new global::DiscountService(new global::FixedAmountDiscountRule(10m));

        Assert.AreEqual(0m, service.GetFinalPrice(0m));
        Assert.ThrowsException<ArgumentOutOfRangeException>(() => service.GetFinalPrice(-1m));
    }
}
