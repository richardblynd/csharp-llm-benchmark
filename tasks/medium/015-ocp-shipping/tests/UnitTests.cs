using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    private sealed class PickupStrategy : global::IShippingStrategy
    {
        public string Method => "pickup";
        public decimal Calculate(global::ShippingRequest request) => 0m;
    }

    [TestMethod]
    public void calculates_known_shipping_methods()
    {
        var calculator = new global::ShippingCalculator(new global::IShippingStrategy[]
        {
            new global::StandardShippingStrategy(),
            new global::ExpressShippingStrategy()
        });
        var request = new global::ShippingRequest(2m, 100m);

        Assert.AreEqual(9.5m, calculator.Calculate("standard", request));
        Assert.AreEqual(21m, calculator.Calculate("express", request));
    }

    [TestMethod]
    public void uses_shipping_strategy_abstraction()
    {
        Assert.IsTrue(typeof(global::IShippingStrategy).IsInterface);
        var constructor = typeof(global::ShippingCalculator).GetConstructors().Single();
        Assert.IsTrue(typeof(IEnumerable<global::IShippingStrategy>).IsAssignableFrom(constructor.GetParameters()[0].ParameterType));
    }

    [TestMethod]
    public void accepts_new_strategy_without_changing_service()
    {
        var calculator = new global::ShippingCalculator(new global::IShippingStrategy[] { new PickupStrategy() });

        Assert.AreEqual(0m, calculator.Calculate("pickup", new global::ShippingRequest(10m, 500m)));
    }

    [TestMethod]
    public void handles_unknown_method_clearly()
    {
        var calculator = new global::ShippingCalculator(new global::IShippingStrategy[] { new global::StandardShippingStrategy() });

        Assert.ThrowsException<InvalidOperationException>(() => calculator.Calculate("drone", new global::ShippingRequest(1m, 1m)));
    }
}
