using Microsoft.Data.Sqlite;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public async Task creates_schema_and_inserts_initial_product()
    {
        using var service = new global::InventoryService();
        await service.InitializeAsync();

        await service.AddProductAsync("sku-1", "Coffee", 10);
        var product = await service.GetProductAsync("sku-1");

        Assert.AreEqual(new global::ProductStock("sku-1", "Coffee", 10), product);
    }

    [TestMethod]
    public async Task adjusts_stock_inside_transactions()
    {
        using var service = new global::InventoryService();
        await service.InitializeAsync();
        await service.AddProductAsync("sku-2", "Tea", 5);

        await service.AdjustStockAsync("sku-2", 7, "Restock");
        await service.AdjustStockAsync("sku-2", -3, "Sale");

        Assert.AreEqual(9, (await service.GetProductAsync("sku-2"))!.Quantity);
    }

    [TestMethod]
    public async Task prevents_negative_stock()
    {
        using var service = new global::InventoryService();
        await service.InitializeAsync();
        await service.AddProductAsync("sku-3", "Flour", 4);

        var exception = await Assert.ThrowsExceptionAsync<global::InventoryException>(() => service.AdjustStockAsync("sku-3", -5, "Oversell"));
        var movements = await service.GetMovementsAsync("sku-3");

        Assert.AreEqual("sku-3", exception.ProductId);
        Assert.AreEqual(4, (await service.GetProductAsync("sku-3"))!.Quantity);
        Assert.AreEqual(1, movements.Count);
    }

    [TestMethod]
    public async Task records_movements_in_order()
    {
        var clock = new ManualTimeProvider(DateTimeOffset.Parse("2026-01-01T00:00:00Z"));
        using var service = new global::InventoryService(timeProvider: clock);
        await service.InitializeAsync();

        await service.AddProductAsync("sku-4", "Sugar", 1);
        clock.Advance(TimeSpan.FromMinutes(1));
        await service.AdjustStockAsync("sku-4", 4, "Restock");
        clock.Advance(TimeSpan.FromMinutes(1));
        await service.AdjustStockAsync("sku-4", -2, "Sale");

        var movements = await service.GetMovementsAsync("sku-4");

        CollectionAssert.AreEqual(new[] { 1, 5, 3 }, movements.Select(item => item.QuantityAfter).ToArray());
        CollectionAssert.AreEqual(new[] { "Initial stock", "Restock", "Sale" }, movements.Select(item => item.Reason).ToArray());
        Assert.IsTrue(movements[0].Id < movements[1].Id && movements[1].Id < movements[2].Id);
    }

    [TestMethod]
    public async Task rolls_back_when_composite_operation_fails()
    {
        using var service = new global::InventoryService();
        await service.InitializeAsync();
        await service.AddProductAsync("from", "Source", 5);

        await Assert.ThrowsExceptionAsync<global::InventoryException>(() => service.TransferAsync("from", "missing", 3, "Move"));

        Assert.AreEqual(5, (await service.GetProductAsync("from"))!.Quantity);
        Assert.AreEqual(1, (await service.GetMovementsAsync("from")).Count);
    }

    [TestMethod]
    public async Task queries_products_and_movements_by_period()
    {
        var start = DateTimeOffset.Parse("2026-01-02T00:00:00Z");
        var clock = new ManualTimeProvider(start);
        using var service = new global::InventoryService(timeProvider: clock);
        await service.InitializeAsync();
        await service.AddProductAsync("sku-5", "Beans", 2);
        clock.Advance(TimeSpan.FromHours(1));
        await service.AdjustStockAsync("sku-5", 5, "Restock");
        clock.Advance(TimeSpan.FromHours(1));
        await service.AdjustStockAsync("sku-5", -1, "Sale");

        var movements = await service.GetMovementsAsync("sku-5", start.AddMinutes(30), start.AddMinutes(90));

        Assert.AreEqual(1, movements.Count);
        Assert.AreEqual("Restock", movements.Single().Reason);
    }

    [TestMethod]
    public async Task disposes_resources_without_invalidating_external_connection()
    {
        using var connection = new SqliteConnection("Data Source=:memory:");
        await connection.OpenAsync();

        using (var service = new global::InventoryService(connection))
        {
            await service.InitializeAsync();
            await service.AddProductAsync("sku-6", "Rice", 3);
        }

        using var command = connection.CreateCommand();
        command.CommandText = "SELECT Quantity FROM Products WHERE ProductId = 'sku-6'";
        var quantity = (long)(await command.ExecuteScalarAsync())!;

        Assert.AreEqual(3L, quantity);
        Assert.AreEqual(System.Data.ConnectionState.Open, connection.State);
    }

    private sealed class ManualTimeProvider : TimeProvider
    {
        private DateTimeOffset now;

        public ManualTimeProvider(DateTimeOffset now)
        {
            this.now = now;
        }

        public override DateTimeOffset GetUtcNow() => now;

        public void Advance(TimeSpan duration)
        {
            now = now.Add(duration);
        }
    }
}
