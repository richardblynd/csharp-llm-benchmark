Write an in-memory order matching engine.

Required public API:

```csharp
public enum OrderSide { Buy, Sell }
public enum OrderEventType { Accepted, Trade, Cancelled }

public sealed record OrderRequest(string OrderId, OrderSide Side, decimal Price, int Quantity);
public sealed record RestingOrder(string OrderId, OrderSide Side, decimal Price, int RemainingQuantity);
public sealed record OrderTrade(string BuyOrderId, string SellOrderId, decimal Price, int Quantity);
public sealed record OrderEvent(OrderEventType Type, string OrderId, string? CounterpartyOrderId, decimal Price, int Quantity);
public sealed record OrderBookSnapshot(IReadOnlyList<RestingOrder> Bids, IReadOnlyList<RestingOrder> Asks);

public sealed class OrderMatchingEngine
{
    public IReadOnlyList<OrderEvent> Events { get; }
    public IReadOnlyList<OrderEvent> Place(OrderRequest request)
    public bool Cancel(string orderId)
    public OrderBookSnapshot Snapshot()
}
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- `OrderId` must be non-empty after trimming, `Price` must be greater than zero and `Quantity` must be greater than zero.
- Duplicate open order ids are invalid.
- Buy orders match the cheapest open sell orders whose price is less than or equal to the buy price.
- Sell orders match the most expensive open buy orders whose price is greater than or equal to the sell price.
- Within the same price level, older resting orders have priority.
- The trade price is always the resting order price.
- If an incoming order is not fully filled, the remaining quantity rests on the book.
- `Place` returns the events produced by that single call and appends the same events to `Events`.
- Emit one `Accepted` event for every valid order, then one `Trade` event per fill, in match order.
- `Cancel` removes only an open resting order and appends one `Cancelled` event when it succeeds.
- `Snapshot` returns bids sorted by descending price then time, and asks sorted by ascending price then time.
- The engine must be safe under concurrent calls.
