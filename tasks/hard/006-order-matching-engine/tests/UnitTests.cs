using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public void adds_limit_orders_to_book()
    {
        var engine = new global::OrderMatchingEngine();

        engine.Place(new global::OrderRequest("b1", global::OrderSide.Buy, 99m, 10));
        engine.Place(new global::OrderRequest("s1", global::OrderSide.Sell, 101m, 7));
        var snapshot = engine.Snapshot();

        Assert.AreEqual("b1", snapshot.Bids.Single().OrderId);
        Assert.AreEqual(10, snapshot.Bids.Single().RemainingQuantity);
        Assert.AreEqual("s1", snapshot.Asks.Single().OrderId);
        Assert.AreEqual(7, snapshot.Asks.Single().RemainingQuantity);
    }

    [TestMethod]
    public void matches_buy_and_sell_by_price()
    {
        var engine = new global::OrderMatchingEngine();

        engine.Place(new global::OrderRequest("ask", global::OrderSide.Sell, 100m, 4));
        var events = engine.Place(new global::OrderRequest("buy", global::OrderSide.Buy, 105m, 4));
        var trade = events.Single(item => item.Type == global::OrderEventType.Trade);

        Assert.AreEqual("buy", trade.OrderId);
        Assert.AreEqual("ask", trade.CounterpartyOrderId);
        Assert.AreEqual(100m, trade.Price);
        Assert.AreEqual(4, trade.Quantity);
        Assert.AreEqual(0, engine.Snapshot().Bids.Count + engine.Snapshot().Asks.Count);
    }

    [TestMethod]
    public void respects_price_time_priority()
    {
        var engine = new global::OrderMatchingEngine();
        engine.Place(new global::OrderRequest("bid-low", global::OrderSide.Buy, 99m, 5));
        engine.Place(new global::OrderRequest("bid-newer", global::OrderSide.Buy, 101m, 5));
        engine.Place(new global::OrderRequest("bid-older", global::OrderSide.Buy, 101m, 5));

        var trades = engine.Place(new global::OrderRequest("sell", global::OrderSide.Sell, 95m, 12))
            .Where(item => item.Type == global::OrderEventType.Trade)
            .Select(item => item.CounterpartyOrderId)
            .ToArray();

        CollectionAssert.AreEqual(new[] { "bid-newer", "bid-older", "bid-low" }, trades);
    }

    [TestMethod]
    public void supports_partial_fills()
    {
        var engine = new global::OrderMatchingEngine();
        engine.Place(new global::OrderRequest("ask", global::OrderSide.Sell, 10m, 10));

        engine.Place(new global::OrderRequest("buy", global::OrderSide.Buy, 10m, 6));
        var snapshot = engine.Snapshot();

        Assert.AreEqual("ask", snapshot.Asks.Single().OrderId);
        Assert.AreEqual(4, snapshot.Asks.Single().RemainingQuantity);
    }

    [TestMethod]
    public void cancels_open_order_without_erasing_history()
    {
        var engine = new global::OrderMatchingEngine();
        engine.Place(new global::OrderRequest("ask", global::OrderSide.Sell, 10m, 10));

        Assert.IsTrue(engine.Cancel("ask"));
        Assert.IsFalse(engine.Cancel("ask"));

        Assert.AreEqual(0, engine.Snapshot().Asks.Count);
        Assert.AreEqual(global::OrderEventType.Accepted, engine.Events[0].Type);
        Assert.AreEqual(global::OrderEventType.Cancelled, engine.Events[1].Type);
    }

    [TestMethod]
    public void emits_events_in_deterministic_order()
    {
        var engine = new global::OrderMatchingEngine();
        engine.Place(new global::OrderRequest("a1", global::OrderSide.Sell, 10m, 2));
        engine.Place(new global::OrderRequest("a2", global::OrderSide.Sell, 11m, 2));

        var events = engine.Place(new global::OrderRequest("b1", global::OrderSide.Buy, 11m, 5));

        Assert.AreEqual(global::OrderEventType.Accepted, events[0].Type);
        Assert.AreEqual("b1", events[0].OrderId);
        Assert.AreEqual("a1", events[1].CounterpartyOrderId);
        Assert.AreEqual("a2", events[2].CounterpartyOrderId);
        Assert.AreEqual("b1", engine.Snapshot().Bids.Single().OrderId);
        Assert.AreEqual(1, engine.Snapshot().Bids.Single().RemainingQuantity);
    }

    [TestMethod]
    public async Task maintains_invariants_under_controlled_concurrency()
    {
        var engine = new global::OrderMatchingEngine();
        var tasks = Enumerable.Range(0, 40).Select(i => Task.Run(() =>
        {
            var side = i % 2 == 0 ? global::OrderSide.Buy : global::OrderSide.Sell;
            var price = side == global::OrderSide.Buy ? 100m : 101m;
            engine.Place(new global::OrderRequest($"order-{i:00}", side, price, 1));
        }));

        await Task.WhenAll(tasks);
        var snapshot = engine.Snapshot();

        Assert.AreEqual(40, snapshot.Bids.Count + snapshot.Asks.Count);
        Assert.AreEqual(40, engine.Events.Count(item => item.Type == global::OrderEventType.Accepted));
        Assert.IsTrue(snapshot.Bids.All(item => item.Price == 100m));
        Assert.IsTrue(snapshot.Asks.All(item => item.Price == 101m));
    }
}
