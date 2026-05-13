using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    private sealed class HalfDiscount : global::IDiscountPolicy
    {
        public decimal CalculateDiscount(global::Order order, decimal subtotal) => subtotal / 2m;
    }

    private sealed class WeightShipping : global::IShippingPolicy
    {
        public decimal CalculateShipping(global::Order order) => order.Items.Sum(i => i.Quantity) * 2m;
    }

    private sealed class ReceiptWriter : global::IReceiptWriter
    {
        public readonly List<global::Receipt> Receipts = new();
        public void Write(global::Receipt receipt) => Receipts.Add(receipt);
    }

    private sealed class Repository : global::IOrderRepository
    {
        public readonly List<global::Order> Orders = new();
        public void Save(global::Order order) => Orders.Add(order);
    }

    [TestMethod]
    public void separates_main_responsibilities()
    {
        Assert.IsTrue(typeof(global::IDiscountPolicy).IsInterface);
        Assert.IsTrue(typeof(global::IShippingPolicy).IsInterface);
        Assert.IsTrue(typeof(global::IReceiptWriter).IsInterface);
        Assert.IsTrue(typeof(global::IOrderRepository).IsInterface);
    }

    [TestMethod]
    public void extends_discount_and_shipping_without_changing_processor()
    {
        var writer = new ReceiptWriter();
        var repository = new Repository();
        var processor = new global::OrderProcessor(new HalfDiscount(), new WeightShipping(), writer, repository);
        var order = new global::Order("o1", new[] { new global::OrderItem("sku", 10m, 3) });

        var receipt = processor.Process(order);

        Assert.AreEqual(30m, receipt.Subtotal);
        Assert.AreEqual(15m, receipt.Discount);
        Assert.AreEqual(6m, receipt.Shipping);
        Assert.AreEqual(21m, receipt.Total);
    }

    [TestMethod]
    public void keeps_pricing_rules_substitutable()
    {
        global::IDiscountPolicy[] policies =
        {
            new global::NoOrderDiscount(),
            new global::PercentageOrderDiscount(0.25m),
            new global::PercentageOrderDiscount(2m)
        };
        var order = new global::Order("o1", new[] { new global::OrderItem("sku", 10m, 1) });

        foreach (var policy in policies)
        {
            var discount = policy.CalculateDiscount(order, 10m);
            Assert.IsTrue(discount >= 0m);
            Assert.IsTrue(discount <= 10m);
        }
    }

    [TestMethod]
    public void uses_small_interfaces_for_receipt_and_persistence()
    {
        Assert.AreEqual(1, typeof(global::IReceiptWriter).GetMethods().Length);
        Assert.AreEqual(1, typeof(global::IOrderRepository).GetMethods().Length);
    }

    [TestMethod]
    public void depends_on_testable_abstractions()
    {
        var writer = new ReceiptWriter();
        var repository = new Repository();
        var processor = new global::OrderProcessor(new global::NoOrderDiscount(), new global::FlatRateShipping(5m), writer, repository);
        var order = new global::Order("o1", new[] { new global::OrderItem("sku", 10m, 2) });

        var receipt = processor.Process(order);

        Assert.AreEqual(1, writer.Receipts.Count);
        Assert.AreEqual(1, repository.Orders.Count);
        Assert.AreEqual(receipt.Total, writer.Receipts[0].Total);
    }
}
