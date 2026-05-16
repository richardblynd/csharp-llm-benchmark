Write a SQLite in-memory inventory service.

The public project already references `Microsoft.Data.Sqlite`; use that package directly and do not add any other packages.

Required public API:

```csharp
public sealed record ProductStock(string ProductId, string Name, int Quantity);
public sealed record InventoryMovement(long Id, string ProductId, int Delta, int QuantityAfter, DateTimeOffset OccurredAt, string Reason);

public sealed class InventoryException : Exception
{
    public string ProductId { get; }
}

public sealed class InventoryService : IDisposable
{
    public InventoryService(SqliteConnection? connection = null, TimeProvider? timeProvider = null)
    public Task InitializeAsync(CancellationToken cancellationToken = default)
    public Task AddProductAsync(string productId, string name, int initialQuantity, CancellationToken cancellationToken = default)
    public Task<ProductStock?> GetProductAsync(string productId, CancellationToken cancellationToken = default)
    public Task AdjustStockAsync(string productId, int delta, string reason, CancellationToken cancellationToken = default)
    public Task TransferAsync(string fromProductId, string toProductId, int quantity, string reason, CancellationToken cancellationToken = default)
    public Task<IReadOnlyList<InventoryMovement>> GetMovementsAsync(string productId, DateTimeOffset? from = null, DateTimeOffset? to = null, CancellationToken cancellationToken = default)
}
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- The service must create its schema in `InitializeAsync`.
- When no connection is provided, create and open a `Data Source=:memory:` connection and dispose it when the service is disposed.
- When a connection is provided, use it but do not dispose or close it.
- Product ids and names must be non-empty after trimming.
- Quantities cannot be negative.
- Adding a product inserts the product and records an initial inventory movement with reason `Initial stock`.
- Stock adjustments and transfers must run inside SQLite transactions.
- Adjustments that would make stock negative must throw `InventoryException` and leave stock and movements unchanged.
- Transfers subtract from one product and add to another in one transaction. If any step fails, all changes must roll back.
- Movements must be returned by ascending `Id`.
- Period filters are inclusive for `from` and `to`.
- Use the injected `TimeProvider` for movement timestamps.
