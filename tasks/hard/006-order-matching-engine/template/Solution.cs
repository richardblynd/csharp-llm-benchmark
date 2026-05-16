using System;
using System.Collections.Generic;

public enum OrderSide { Buy, Sell }
public enum OrderEventType { Accepted, Trade, Cancelled }

public sealed record OrderRequest(string OrderId, OrderSide Side, decimal Price, int Quantity);
public sealed record RestingOrder(string OrderId, OrderSide Side, decimal Price, int RemainingQuantity);
public sealed record OrderTrade(string BuyOrderId, string SellOrderId, decimal Price, int Quantity);
public sealed record OrderEvent(OrderEventType Type, string OrderId, string? CounterpartyOrderId, decimal Price, int Quantity);
public sealed record OrderBookSnapshot(IReadOnlyList<RestingOrder> Bids, IReadOnlyList<RestingOrder> Asks);

public sealed class OrderMatchingEngine
{
    public IReadOnlyList<OrderEvent> Events => throw new NotImplementedException();
    public IReadOnlyList<OrderEvent> Place(OrderRequest request) => throw new NotImplementedException();
    public bool Cancel(string orderId) => throw new NotImplementedException();
    public OrderBookSnapshot Snapshot() => throw new NotImplementedException();
}
