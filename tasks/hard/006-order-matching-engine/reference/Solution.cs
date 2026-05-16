using System;
using System.Collections.Generic;
using System.Linq;

public enum OrderSide { Buy, Sell }
public enum OrderEventType { Accepted, Trade, Cancelled }

public sealed record OrderRequest(string OrderId, OrderSide Side, decimal Price, int Quantity);
public sealed record RestingOrder(string OrderId, OrderSide Side, decimal Price, int RemainingQuantity);
public sealed record OrderTrade(string BuyOrderId, string SellOrderId, decimal Price, int Quantity);
public sealed record OrderEvent(OrderEventType Type, string OrderId, string? CounterpartyOrderId, decimal Price, int Quantity);
public sealed record OrderBookSnapshot(IReadOnlyList<RestingOrder> Bids, IReadOnlyList<RestingOrder> Asks);

public sealed class OrderMatchingEngine
{
    private sealed class OpenOrder
    {
        public OpenOrder(string id, OrderSide side, decimal price, int remaining, long sequence)
        {
            Id = id;
            Side = side;
            Price = price;
            Remaining = remaining;
            Sequence = sequence;
        }

        public string Id { get; }
        public OrderSide Side { get; }
        public decimal Price { get; }
        public int Remaining { get; set; }
        public long Sequence { get; }
    }

    private readonly object gate = new();
    private readonly List<OpenOrder> bids = new();
    private readonly List<OpenOrder> asks = new();
    private readonly List<OrderEvent> events = new();
    private long sequence;

    public IReadOnlyList<OrderEvent> Events
    {
        get
        {
            lock (gate)
            {
                return events.ToArray();
            }
        }
    }

    public IReadOnlyList<OrderEvent> Place(OrderRequest request)
    {
        Validate(request);
        lock (gate)
        {
            var id = request.OrderId.Trim();
            if (bids.Concat(asks).Any(order => string.Equals(order.Id, id, StringComparison.Ordinal)))
            {
                throw new ArgumentException("An open order with the same id already exists.", nameof(request));
            }

            var produced = new List<OrderEvent> { new(OrderEventType.Accepted, id, null, request.Price, request.Quantity) };
            var incoming = new OpenOrder(id, request.Side, request.Price, request.Quantity, ++sequence);
            Match(incoming, produced);
            if (incoming.Remaining > 0)
            {
                (incoming.Side == OrderSide.Buy ? bids : asks).Add(incoming);
            }

            events.AddRange(produced);
            return produced.ToArray();
        }
    }

    public bool Cancel(string orderId)
    {
        if (string.IsNullOrWhiteSpace(orderId))
        {
            throw new ArgumentException("Order id is required.", nameof(orderId));
        }

        lock (gate)
        {
            var id = orderId.Trim();
            var order = bids.Concat(asks).FirstOrDefault(item => string.Equals(item.Id, id, StringComparison.Ordinal));
            if (order is null)
            {
                return false;
            }

            (order.Side == OrderSide.Buy ? bids : asks).Remove(order);
            events.Add(new OrderEvent(OrderEventType.Cancelled, id, null, order.Price, order.Remaining));
            return true;
        }
    }

    public OrderBookSnapshot Snapshot()
    {
        lock (gate)
        {
            return new OrderBookSnapshot(
                bids.OrderByDescending(order => order.Price).ThenBy(order => order.Sequence).Select(ToResting).ToArray(),
                asks.OrderBy(order => order.Price).ThenBy(order => order.Sequence).Select(ToResting).ToArray());
        }
    }

    private void Match(OpenOrder incoming, List<OrderEvent> produced)
    {
        var opposite = incoming.Side == OrderSide.Buy ? asks : bids;
        while (incoming.Remaining > 0)
        {
            var match = incoming.Side == OrderSide.Buy
                ? opposite.Where(order => order.Price <= incoming.Price).OrderBy(order => order.Price).ThenBy(order => order.Sequence).FirstOrDefault()
                : opposite.Where(order => order.Price >= incoming.Price).OrderByDescending(order => order.Price).ThenBy(order => order.Sequence).FirstOrDefault();
            if (match is null)
            {
                break;
            }

            var quantity = Math.Min(incoming.Remaining, match.Remaining);
            incoming.Remaining -= quantity;
            match.Remaining -= quantity;
            var buyId = incoming.Side == OrderSide.Buy ? incoming.Id : match.Id;
            var sellId = incoming.Side == OrderSide.Sell ? incoming.Id : match.Id;
            produced.Add(new OrderEvent(OrderEventType.Trade, incoming.Id, match.Id, match.Price, quantity));
            if (match.Remaining == 0)
            {
                opposite.Remove(match);
            }
        }
    }

    private static RestingOrder ToResting(OpenOrder order)
    {
        return new RestingOrder(order.Id, order.Side, order.Price, order.Remaining);
    }

    private static void Validate(OrderRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (string.IsNullOrWhiteSpace(request.OrderId))
        {
            throw new ArgumentException("Order id is required.", nameof(request));
        }

        if (request.Price <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(request), "Price must be greater than zero.");
        }

        if (request.Quantity <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(request), "Quantity must be greater than zero.");
        }
    }
}
