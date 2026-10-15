namespace Inventory;

public sealed record ProductStock(string ProductId, string Name, int Quantity);
public sealed record InventoryMovement(long Id, string ProductId, int Delta, int QuantityAfter, DateTimeOffset OccurredAt, string Reason);

public sealed class InventoryException(string productId, string message) : Exception(message)
{
    public string ProductId { get; } = productId;
}

