using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Data.Sqlite;

public sealed record ProductStock(string ProductId, string Name, int Quantity);
public sealed record InventoryMovement(long Id, string ProductId, int Delta, int QuantityAfter, DateTimeOffset OccurredAt, string Reason);

public sealed class InventoryException : Exception
{
    public InventoryException(string productId, string message) : base(message)
    {
        ProductId = productId;
    }

    public string ProductId { get; }
}

public sealed class InventoryService : IDisposable
{
    public InventoryService(SqliteConnection? connection = null, TimeProvider? timeProvider = null) => throw new NotImplementedException();
    public Task InitializeAsync(CancellationToken cancellationToken = default) => throw new NotImplementedException();
    public Task AddProductAsync(string productId, string name, int initialQuantity, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    public Task<ProductStock?> GetProductAsync(string productId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    public Task AdjustStockAsync(string productId, int delta, string reason, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    public Task TransferAsync(string fromProductId, string toProductId, int quantity, string reason, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    public Task<IReadOnlyList<InventoryMovement>> GetMovementsAsync(string productId, DateTimeOffset? from = null, DateTimeOffset? to = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    public void Dispose() => throw new NotImplementedException();
}
