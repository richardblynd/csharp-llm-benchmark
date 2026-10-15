using Microsoft.Data.Sqlite;

namespace Inventory;

public sealed partial class InventoryService
{
    private void CheckQuantity(string productId, int quantity, SqliteTransaction transaction)
    {
        if (quantity < 0) throw new InventoryException(productId, "Insufficient stock.");
    }
}

