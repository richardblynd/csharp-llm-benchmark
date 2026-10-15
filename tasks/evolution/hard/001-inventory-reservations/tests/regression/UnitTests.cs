using System.Data;
using Microsoft.Data.Sqlite;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Inventory;

[TestClass]
public sealed class RegressionTests
{
    private sealed class Clock : TimeProvider
    {
        public DateTimeOffset Now = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);
        public override DateTimeOffset GetUtcNow() => Now;
    }

    [TestMethod]
    public async Task old_initialization_products_and_normalization_are_preserved()
    {
        using var service = new InventoryService();
        await service.InitializeAsync();
        await service.AddProductAsync(" p ", " Widget ", 10);
        Assert.AreEqual(new ProductStock("p", "Widget", 10), await service.GetProductAsync(" p "));
        Assert.IsNull(await service.GetProductAsync("P"));
        await service.InitializeAsync();
        Assert.AreEqual(10, (await service.GetProductAsync("p"))!.Quantity);
        Assert.AreEqual(0, (await service.GetMovementsAsync("missing")).Count);
        var error = await Assert.ThrowsExceptionAsync<InventoryException>(() => service.AddProductAsync("p", "Duplicate", 1));
        Assert.AreEqual("p", error.ProductId);
    }

    [TestMethod]
    public async Task old_adjustments_history_and_inclusive_filters_are_preserved()
    {
        var clock = new Clock();
        using var service = new InventoryService(timeProvider: clock);
        await service.InitializeAsync();
        await service.AddProductAsync("p", "Widget", 10);
        var first = clock.Now;
        clock.Now = first.AddHours(1);
        await service.AdjustStockAsync("p", -3, " sold ");
        clock.Now = first.AddHours(2);
        await service.AdjustStockAsync("p", 2, "restocked");
        var movements = await service.GetMovementsAsync("p");
        CollectionAssert.AreEqual(new[] { 10, -3, 2 }, movements.Select(item => item.Delta).ToArray());
        CollectionAssert.AreEqual(new[] { 10, 7, 9 }, movements.Select(item => item.QuantityAfter).ToArray());
        CollectionAssert.AreEqual(new[] { first, first.AddHours(1), first.AddHours(2) }, movements.Select(item => item.OccurredAt).ToArray());
        Assert.AreEqual("Initial stock", movements[0].Reason);
        Assert.AreEqual("sold", movements[1].Reason);
        CollectionAssert.AreEqual(movements.OrderBy(item => item.Id).ToArray(), movements.ToArray());
        Assert.AreEqual(1, (await service.GetMovementsAsync("p", first.AddHours(1), first.AddHours(1))).Count);
        await Assert.ThrowsExceptionAsync<InventoryException>(() => service.AdjustStockAsync("p", -10, "invalid"));
        Assert.AreEqual(9, (await service.GetProductAsync("p"))!.Quantity);
        Assert.AreEqual(3, (await service.GetMovementsAsync("p")).Count);
    }

    [TestMethod]
    public async Task old_transfers_update_both_products_atomically()
    {
        using var service = new InventoryService();
        await service.InitializeAsync();
        await service.AddProductAsync("a", "A", 10);
        await service.AddProductAsync("b", "B", 2);
        await service.TransferAsync("a", "b", 4, " shipment ");
        Assert.AreEqual(6, (await service.GetProductAsync("a"))!.Quantity);
        Assert.AreEqual(6, (await service.GetProductAsync("b"))!.Quantity);
        var source = (await service.GetMovementsAsync("a")).Last();
        var target = (await service.GetMovementsAsync("b")).Last();
        Assert.AreEqual(-4, source.Delta); Assert.AreEqual(4, target.Delta);
        Assert.AreEqual(6, source.QuantityAfter); Assert.AreEqual(6, target.QuantityAfter);
        Assert.AreEqual("shipment", source.Reason); Assert.AreEqual("shipment", target.Reason);
    }

    [TestMethod]
    public async Task old_transfer_failures_roll_back_balance_and_history()
    {
        using var service = new InventoryService();
        await service.InitializeAsync();
        await service.AddProductAsync("a", "A", 10);
        await service.AddProductAsync("b", "B", int.MaxValue);
        await service.AddProductAsync("c", "C", 0);
        await Assert.ThrowsExceptionAsync<InventoryException>(() => service.TransferAsync("a", "absent", 3, "missing"));
        await Assert.ThrowsExceptionAsync<InventoryException>(() => service.TransferAsync("a", "c", 11, "excess"));
        await Assert.ThrowsExceptionAsync<OverflowException>(() => service.TransferAsync("a", "b", 1, "overflow"));
        Assert.AreEqual(10, (await service.GetProductAsync("a"))!.Quantity);
        Assert.AreEqual(int.MaxValue, (await service.GetProductAsync("b"))!.Quantity);
        Assert.AreEqual(1, (await service.GetMovementsAsync("a")).Count);
        Assert.AreEqual(1, (await service.GetMovementsAsync("b")).Count);
    }

    [TestMethod]
    public async Task old_validation_and_cancellation_are_preserved()
    {
        using var service = new InventoryService();
        await service.InitializeAsync();
        await Assert.ThrowsExceptionAsync<ArgumentException>(() => service.AddProductAsync(" ", "Widget", 1));
        await Assert.ThrowsExceptionAsync<ArgumentException>(() => service.AddProductAsync("p", " ", 1));
        await Assert.ThrowsExceptionAsync<ArgumentOutOfRangeException>(() => service.AddProductAsync("p", "Widget", -1));
        await service.AddProductAsync("p", "Widget", 4);
        await Assert.ThrowsExceptionAsync<ArgumentOutOfRangeException>(() => service.TransferAsync("p", "other", 0, "transfer"));
        await Assert.ThrowsExceptionAsync<ArgumentException>(() => service.TransferAsync("p", "p", 1, "transfer"));
        await Assert.ThrowsExceptionAsync<ArgumentException>(() => service.AdjustStockAsync("p", 1, " "));
        using var cancelled = new CancellationTokenSource(); cancelled.Cancel();
        try { await service.AdjustStockAsync("p", 2, "cancelled", cancelled.Token); Assert.Fail(); } catch (OperationCanceledException) { }
        Assert.AreEqual(4, (await service.GetProductAsync("p"))!.Quantity);
        Assert.AreEqual(1, (await service.GetMovementsAsync("p")).Count);
    }

    [TestMethod]
    public async Task old_connection_ownership_and_schema_reuse_are_preserved()
    {
        using var connection = new SqliteConnection("Data Source=:memory:");
        using (var first = new InventoryService(connection))
        {
            await first.InitializeAsync();
            await first.AddProductAsync("p", "Widget", 2);
            first.Dispose(); first.Dispose();
        }
        Assert.AreEqual(ConnectionState.Open, connection.State);
        using var next = new InventoryService(connection);
        await next.InitializeAsync();
        Assert.AreEqual(2, (await next.GetProductAsync("p"))!.Quantity);
        Assert.AreEqual(1, (await next.GetMovementsAsync("p")).Count);
    }

    [TestMethod]
    public async Task old_database_failures_roll_back_transactions()
    {
        using var connection = new SqliteConnection("Data Source=:memory:");
        using var service = new InventoryService(connection);
        await service.InitializeAsync();
        await service.AddProductAsync("a", "A", 10);
        await service.AddProductAsync("b", "B", 0);
        using var trigger = connection.CreateCommand();
        trigger.CommandText = "CREATE TRIGGER reject_target BEFORE UPDATE ON products WHEN NEW.id='b' BEGIN SELECT RAISE(ABORT,'forced'); END;";
        trigger.ExecuteNonQuery();
        await Assert.ThrowsExceptionAsync<SqliteException>(() => service.TransferAsync("a", "b", 3, "rejected"));
        Assert.AreEqual(10, (await service.GetProductAsync("a"))!.Quantity);
        Assert.AreEqual(0, (await service.GetProductAsync("b"))!.Quantity);
        Assert.AreEqual(1, (await service.GetMovementsAsync("a")).Count);
        Assert.AreEqual(1, (await service.GetMovementsAsync("b")).Count);
    }
}

