Implement a small order processing module that applies all SOLID principles together.

Required public API:

```csharp
public sealed class OrderItem
{
    public OrderItem(string sku, decimal unitPrice, int quantity)
    public string Sku { get; }
    public decimal UnitPrice { get; }
    public int Quantity { get; }
}

public sealed class Order
{
    public Order(string id, IEnumerable<OrderItem> items)
    public string Id { get; }
    public IReadOnlyList<OrderItem> Items { get; }
}

public sealed class Receipt
{
    public decimal Subtotal { get; }
    public decimal Discount { get; }
    public decimal Shipping { get; }
    public decimal Total { get; }
}

public interface IDiscountPolicy
{
    decimal CalculateDiscount(Order order, decimal subtotal);
}

public interface IShippingPolicy
{
    decimal CalculateShipping(Order order);
}

public interface IReceiptWriter
{
    void Write(Receipt receipt);
}

public interface IOrderRepository
{
    void Save(Order order);
}

public sealed class NoOrderDiscount
public sealed class PercentageOrderDiscount
{
    public PercentageOrderDiscount(decimal percentage)
}

public sealed class FlatRateShipping
{
    public FlatRateShipping(decimal amount)
}

public sealed class OrderProcessor
{
    public OrderProcessor(IDiscountPolicy discountPolicy, IShippingPolicy shippingPolicy, IReceiptWriter receiptWriter, IOrderRepository repository)
    public Receipt Process(Order order)
}
```

Rules:
- Do not include a namespace.
- Do not use external libraries.
- All code, public identifiers, exception messages and comments must be written in English.
- Separate pricing, discount, shipping, receipt writing and persistence responsibilities.
- `OrderProcessor` must depend on abstractions, not concrete implementations.
- New discount and shipping policies supplied by tests must work without changing `OrderProcessor`.
- Discount policies must never produce negative discounts or discounts larger than the subtotal for valid orders.
- `IReceiptWriter` and `IOrderRepository` must be small interfaces.
- Processing an order must calculate subtotal, discount, shipping, total, write a receipt and save the order.
