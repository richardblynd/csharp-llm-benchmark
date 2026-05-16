using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void executes_known_strategies_in_configured_order()
    {
        var engine = new global::PricingEngine(new global::IPricingStrategy[]
        {
            new global::ShippingStrategy("shipping", 5m, 1m),
            new global::PercentageDiscountStrategy("discount", 10m),
            new global::RegionalTaxStrategy("tax", "US", 5m)
        });

        var result = engine.Calculate(new global::PricingContext(100m, "standard", "US", 2m), new[] { "discount", "tax", "shipping" });

        Assert.AreEqual(101.50m, result.Total);
        CollectionAssert.AreEqual(new[] { "discount", "tax", "shipping" }, result.Steps.Select(step => step.StrategyName).ToArray());
    }

    [TestMethod]
    public void registers_custom_strategy_without_changing_engine()
    {
        var engine = new global::PricingEngine(new global::IPricingStrategy[]
        {
            new CustomerRebateStrategy(),
            new global::FixedFeeStrategy("handling", 3m)
        });

        var result = engine.Calculate(new global::PricingContext(50m, "vip", "BR", 1m));

        Assert.AreEqual(43m, result.Total);
        CollectionAssert.Contains(result.Steps.Select(step => step.StrategyName).ToArray(), "customer-rebate");
    }

    [TestMethod]
    public void detects_duplicate_or_conflicting_strategies()
    {
        Assert.ThrowsException<global::PricingConfigurationException>(() => new global::PricingEngine(new global::IPricingStrategy[]
        {
            new global::FixedFeeStrategy("fee", 1m),
            new global::FixedFeeStrategy("fee", 2m)
        }));

        var engine = new global::PricingEngine(new global::IPricingStrategy[]
        {
            new global::FixedFeeStrategy("manual-price", 1m, conflictsWith: new[] { "discount" }),
            new global::PercentageDiscountStrategy("discount", 10m)
        });

        Assert.ThrowsException<global::PricingConfigurationException>(() => engine.Calculate(new global::PricingContext(20m, "standard", "US", 1m)));
    }

    [TestMethod]
    public void prevents_negative_prices()
    {
        var engine = new global::PricingEngine(new global::IPricingStrategy[]
        {
            new global::PercentageDiscountStrategy("too-large", 150m)
        });

        var result = engine.Calculate(new global::PricingContext(10m, "standard", "US", 0m));

        Assert.AreEqual(0m, result.Total);
        Assert.AreEqual(0m, result.Steps.Single().AmountAfter);
    }

    [TestMethod]
    public void uses_small_substitutable_contracts()
    {
        global::IPricingStrategy strategy = new CustomerRebateStrategy();

        Assert.AreEqual("customer-rebate", strategy.Name);
        Assert.AreEqual(0m, strategy.Apply(10m, new global::PricingContext(10m, "vip", "US", 0m)));
        Assert.AreEqual(10m, strategy.Apply(10m, new global::PricingContext(10m, "standard", "US", 0m)));
    }

    [TestMethod]
    public void returns_explainable_calculation_trace()
    {
        var engine = new global::PricingEngine(new global::IPricingStrategy[]
        {
            new global::FixedFeeStrategy("handling", 2m, order: 2),
            new global::PercentageDiscountStrategy("discount", 10m, order: 1)
        });

        var result = engine.Calculate(new global::PricingContext(100m, "standard", "US", 0m));

        Assert.AreEqual(2, result.Steps.Count);
        Assert.AreEqual(100m, result.Steps[0].AmountBefore);
        Assert.AreEqual(90m, result.Steps[0].AmountAfter);
        Assert.AreEqual(92m, result.Steps[1].AmountAfter);
        Assert.IsFalse(string.IsNullOrWhiteSpace(result.Steps[0].Description));
    }

    private sealed class CustomerRebateStrategy : global::IPricingStrategy
    {
        public string Name => "customer-rebate";
        public int Order => 0;
        public IReadOnlyCollection<string> ConflictsWith => Array.Empty<string>();
        public decimal Apply(decimal currentAmount, global::PricingContext context) => context.CustomerType == "vip" ? currentAmount - 10m : currentAmount;
        public string Describe(decimal amountBefore, decimal amountAfter, global::PricingContext context) => "Applies a VIP rebate.";
    }
}
