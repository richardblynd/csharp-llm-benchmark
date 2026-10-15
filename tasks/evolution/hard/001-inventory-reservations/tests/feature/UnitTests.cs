using Microsoft.Data.Sqlite;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Inventory;

[TestClass]
public sealed class FeatureTests
{
    private static async Task<InventoryService> New(int quantity = 10)
    {
        var service = new InventoryService();
        await service.InitializeAsync();
        await service.AddProductAsync("p", "Widget", quantity);
        return service;
    }

    [TestMethod]
    public async Task reservations_track_available_stock_without_changing_total()
    {
        using var service = await New();
        Assert.AreEqual(10, await service.GetAvailableStockAsync("p"));
        var first = await service.ReserveAsync(" r1 ", " p ", 3);
        Assert.AreEqual("r1", first.ReservationId); Assert.AreEqual("p", first.ProductId);
        Assert.AreEqual(3, first.Quantity); Assert.IsFalse(first.Released);
        await service.ReserveAsync("r2", "p", 4);
        Assert.AreEqual(3, await service.GetAvailableStockAsync("p"));
        Assert.AreEqual(10, (await service.GetProductAsync("p"))!.Quantity);
        Assert.AreEqual(first, await service.GetReservationAsync("r1"));
    }

    [TestMethod]
    public async Task reservation_ids_are_idempotent_and_immutable()
    {
        using var service = await New();
        var first = await service.ReserveAsync("r", "p", 4);
        Assert.AreEqual(first, await service.ReserveAsync(" r ", " p ", 4));
        await Assert.ThrowsExceptionAsync<InventoryException>(() => service.ReserveAsync("r", "p", 5));
        await service.AddProductAsync("q", "Other", 8);
        await Assert.ThrowsExceptionAsync<InventoryException>(() => service.ReserveAsync("r", "q", 4));
        Assert.AreEqual(6, await service.GetAvailableStockAsync("p"));
        Assert.AreEqual(8, await service.GetAvailableStockAsync("q"));
        await service.ReleaseReservationAsync("r");
        var released = await service.ReserveAsync("r", "p", 4);
        Assert.IsTrue(released.Released);
        Assert.AreEqual(10, await service.GetAvailableStockAsync("p"));
        await service.ReserveAsync("R", "p", 2);
        Assert.AreEqual(8, await service.GetAvailableStockAsync("p"));
    }

    [TestMethod]
    public async Task releases_are_idempotent_and_restore_availability()
    {
        using var service = await New();
        var snapshot = await service.ReserveAsync("r", "p", 6);
        Assert.IsFalse(await service.ReleaseReservationAsync("absent"));
        Assert.AreEqual(4, await service.GetAvailableStockAsync("p"));
        Assert.IsTrue(await service.ReleaseReservationAsync(" r "));
        Assert.IsFalse(await service.ReleaseReservationAsync("r"));
        Assert.IsTrue((await service.GetReservationAsync("r"))!.Released);
        Assert.IsFalse(snapshot.Released);
        Assert.AreEqual(10, await service.GetAvailableStockAsync("p"));
        await service.ReserveAsync("new", "p", 10);
        Assert.AreEqual(0, await service.GetAvailableStockAsync("p"));
    }

    [TestMethod]
    public async Task failed_reservations_leave_all_state_unchanged()
    {
        using var service = await New(5);
        await service.ReserveAsync("r", "p", 4);
        var before = (await service.GetMovementsAsync("p")).ToArray();
        var error = await Assert.ThrowsExceptionAsync<InventoryException>(() => service.ReserveAsync("excess", "p", 2));
        Assert.AreEqual("p", error.ProductId);
        await Assert.ThrowsExceptionAsync<InventoryException>(() => service.ReserveAsync("unknown", "absent", 1));
        await Assert.ThrowsExceptionAsync<ArgumentOutOfRangeException>(() => service.ReserveAsync("zero", "p", 0));
        await Assert.ThrowsExceptionAsync<ArgumentOutOfRangeException>(() => service.ReserveAsync("negative", "p", -1));
        await Assert.ThrowsExceptionAsync<ArgumentException>(() => service.ReserveAsync(" ", "p", 1));
        await Assert.ThrowsExceptionAsync<ArgumentException>(() => service.ReserveAsync("blank", " ", 1));
        await Assert.ThrowsExceptionAsync<ArgumentException>(() => service.ReleaseReservationAsync(" "));
        Assert.IsNull(await service.GetReservationAsync("excess"));
        Assert.IsNull(await service.GetReservationAsync("unknown"));
        Assert.IsNull(await service.GetReservationAsync("negative"));
        Assert.AreEqual(1, await service.GetAvailableStockAsync("p"));
        Assert.AreEqual(5, (await service.GetProductAsync("p"))!.Quantity);
        CollectionAssert.AreEqual(before, (await service.GetMovementsAsync("p")).ToArray());
        await Assert.ThrowsExceptionAsync<InventoryException>(() => service.GetAvailableStockAsync("absent"));
    }

    [TestMethod]
    public async Task old_adjustments_cannot_consume_reserved_stock()
    {
        using var service = await New();
        await service.ReserveAsync("r", "p", 7);
        await service.AdjustStockAsync("p", -3, "spend available");
        Assert.AreEqual(0, await service.GetAvailableStockAsync("p"));
        var before = (await service.GetMovementsAsync("p")).ToArray();
        await Assert.ThrowsExceptionAsync<InventoryException>(() => service.AdjustStockAsync("p", -1, "spend reserved"));
        Assert.AreEqual(7, (await service.GetProductAsync("p"))!.Quantity);
        CollectionAssert.AreEqual(before, (await service.GetMovementsAsync("p")).ToArray());
        await service.AdjustStockAsync("p", 2, "restock");
        Assert.AreEqual(2, await service.GetAvailableStockAsync("p"));
    }

    [TestMethod]
    public async Task old_transfers_cannot_consume_reserved_stock()
    {
        using var service = await New();
        await service.AddProductAsync("q", "Other", 0);
        await service.ReserveAsync("r", "p", 8);
        await service.TransferAsync("p", "q", 2, "available");
        var before = (await service.GetMovementsAsync("p")).ToArray();
        await Assert.ThrowsExceptionAsync<InventoryException>(() => service.TransferAsync("p", "q", 1, "reserved"));
        Assert.AreEqual(8, (await service.GetProductAsync("p"))!.Quantity);
        Assert.AreEqual(2, (await service.GetProductAsync("q"))!.Quantity);
        CollectionAssert.AreEqual(before, (await service.GetMovementsAsync("p")).ToArray());
        await service.TransferAsync("q", "p", 1, "receive");
        Assert.AreEqual(1, await service.GetAvailableStockAsync("p"));
        Assert.AreEqual(1, (await service.GetProductAsync("q"))!.Quantity);
    }

    [TestMethod]
    public async Task reservations_persist_across_service_instances()
    {
        var file = Path.Combine(Path.GetTempPath(), $"inventory-{Guid.NewGuid():N}.sqlite");
        try
        {
            using var firstConnection = new SqliteConnection($"Data Source={file};Pooling=False");
            using var first = new InventoryService(firstConnection);
            await first.InitializeAsync(); await first.AddProductAsync("p", "Widget", 10);
            await first.ReserveAsync("r", "p", 6);
            using var secondConnection = new SqliteConnection($"Data Source={file};Pooling=False");
            using var second = new InventoryService(secondConnection);
            await second.InitializeAsync();
            Assert.AreEqual(4, await second.GetAvailableStockAsync("p"));
            Assert.AreEqual(6, (await second.GetReservationAsync("r"))!.Quantity);
            Assert.IsTrue(await second.ReleaseReservationAsync("r"));
            Assert.AreEqual(10, await first.GetAvailableStockAsync("p"));
            first.Dispose();
            using var recreated = new InventoryService(firstConnection);
            await recreated.InitializeAsync();
            Assert.IsTrue((await recreated.GetReservationAsync("r"))!.Released);
            Assert.AreEqual(1, (await recreated.GetMovementsAsync("p")).Count);
        }
        finally { File.Delete(file); }
    }

    [TestMethod]
    public async Task concurrent_connections_cannot_overreserve()
    {
        var file = Path.Combine(Path.GetTempPath(), $"inventory-race-{Guid.NewGuid():N}.sqlite");
        try
        {
            using var connectionA = new SqliteConnection($"Data Source={file};Pooling=False;Default Timeout=5");
            using var connectionB = new SqliteConnection($"Data Source={file};Pooling=False;Default Timeout=5");
            using var a = new InventoryService(connectionA); using var b = new InventoryService(connectionB);
            await a.InitializeAsync(); await b.InitializeAsync();
            await a.AddProductAsync("p", "Widget", 10);
            var start = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var contenders = Enumerable.Range(0, 8).Select(i => Task.Run(async () => {
                await start.Task;
                try { await (i % 2 == 0 ? a : b).ReserveAsync($"r{i}", "p", 7); return true; }
                catch (InventoryException) { return false; }
            })).ToArray();
            start.SetResult(true);
            var outcomes = await Task.WhenAll(contenders);
            Assert.AreEqual(1, outcomes.Count(success => success));
            Assert.AreEqual(3, await a.GetAvailableStockAsync("p"));
            Assert.AreEqual(3, await b.GetAvailableStockAsync("p"));
            Assert.AreEqual(10, (await a.GetProductAsync("p"))!.Quantity);
            var winner = $"r{Array.FindIndex(outcomes, success => success)}";
            var releaseStart = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var releases = Enumerable.Range(0, 8).Select(i => Task.Run(async () => {
                await releaseStart.Task;
                return await (i % 2 == 0 ? a : b).ReleaseReservationAsync(winner);
            })).ToArray();
            releaseStart.SetResult(true);
            Assert.AreEqual(1, (await Task.WhenAll(releases)).Count(released => released));
            Assert.AreEqual(10, await a.GetAvailableStockAsync("p"));
            Assert.AreEqual(10, await b.GetAvailableStockAsync("p"));
        }
        finally { File.Delete(file); }
    }

    [TestMethod]
    public async Task cancelled_reservation_operations_leave_state_unchanged()
    {
        using var service = await New();
        await service.ReserveAsync("r", "p", 4);
        using var cancelled = new CancellationTokenSource(); cancelled.Cancel();
        foreach (var operation in new Func<Task>[] {
            () => service.ReserveAsync("cancelled", "p", 2, cancelled.Token),
            () => service.ReleaseReservationAsync("r", cancelled.Token) })
        {
            try { await operation(); Assert.Fail(); } catch (OperationCanceledException) { }
        }
        Assert.IsNull(await service.GetReservationAsync("cancelled"));
        Assert.IsFalse((await service.GetReservationAsync("r"))!.Released);
        Assert.AreEqual(6, await service.GetAvailableStockAsync("p"));
        Assert.AreEqual(1, (await service.GetMovementsAsync("p")).Count);
    }

    [TestMethod]
    public async Task reservation_operations_preserve_movement_history()
    {
        using var service = await New();
        var before = (await service.GetMovementsAsync("p")).ToArray();
        await service.ReserveAsync("r1", "p", 3);
        await service.ReserveAsync("r2", "p", 5);
        await service.ReleaseReservationAsync("r1");
        CollectionAssert.AreEqual(before, (await service.GetMovementsAsync("p")).ToArray());
        await service.AdjustStockAsync("p", -2, "available");
        var after = await service.GetMovementsAsync("p");
        Assert.AreEqual(2, after.Count);
        Assert.AreEqual(-2, after.Last().Delta);
        Assert.AreEqual(8, after.Last().QuantityAfter);
        Assert.AreEqual(3, await service.GetAvailableStockAsync("p"));
    }
}

