using Microsoft.Data.Sqlite;

namespace Inventory;

public sealed partial class InventoryService
{
    public Task<StockReservation> ReserveAsync(string reservationId, string productId, int quantity,
        CancellationToken cancellationToken = default)
    {
        reservationId = Text(reservationId); productId = Text(productId);
        if (quantity <= 0) throw new ArgumentOutOfRangeException(nameof(quantity));
        return WriteAsync(transaction => {
            var existing = FindReservation(reservationId, transaction);
            if (existing is not null)
            {
                if (existing.ProductId == productId && existing.Quantity == quantity) return existing;
                throw new InventoryException(productId, "Reservation id has different details.");
            }
            var product = RequiredStock(productId, transaction);
            if (quantity > product.Quantity - ReservedQuantity(productId, transaction))
                throw new InventoryException(productId, "Insufficient available stock.");
            Execute(transaction, "INSERT INTO reservations(id, product_id, quantity, released) VALUES($id,$product,$quantity,0)",
                ("$id", reservationId), ("$product", productId), ("$quantity", quantity));
            return new StockReservation(reservationId, productId, quantity, false);
        }, cancellationToken);
    }

    public Task<bool> ReleaseReservationAsync(string reservationId, CancellationToken cancellationToken = default)
    {
        reservationId = Text(reservationId);
        return WriteAsync(transaction => {
            var existing = FindReservation(reservationId, transaction);
            if (existing is null || existing.Released) return false;
            Execute(transaction, "UPDATE reservations SET released=1 WHERE id=$id", ("$id", reservationId));
            return true;
        }, cancellationToken);
    }

    public Task<StockReservation?> GetReservationAsync(string reservationId, CancellationToken cancellationToken = default)
    {
        reservationId = Text(reservationId);
        return ReadAsync(() => FindReservation(reservationId), cancellationToken);
    }

    public Task<int> GetAvailableStockAsync(string productId, CancellationToken cancellationToken = default)
    {
        productId = Text(productId);
        return ReadAsync(() => {
            using var command = Command(null, @"SELECT p.quantity - COALESCE(
                (SELECT SUM(r.quantity) FROM reservations r WHERE r.product_id=p.id AND r.released=0),0)
                FROM products p WHERE p.id=$id", ("$id", productId));
            var value = command.ExecuteScalar();
            if (value is null) throw new InventoryException(productId, "Product does not exist.");
            return checked(Convert.ToInt32(value));
        }, cancellationToken);
    }

    private int ReservedQuantity(string productId, SqliteTransaction? transaction = null)
    {
        using var command = Command(transaction,
            "SELECT COALESCE(SUM(quantity),0) FROM reservations WHERE product_id=$id AND released=0", ("$id", productId));
        return checked(Convert.ToInt32(command.ExecuteScalar()));
    }

    private StockReservation? FindReservation(string id, SqliteTransaction? transaction = null)
    {
        using var command = Command(transaction, "SELECT product_id, quantity, released FROM reservations WHERE id=$id", ("$id", id));
        using var reader = command.ExecuteReader();
        return reader.Read() ? new StockReservation(id, reader.GetString(0), reader.GetInt32(1), reader.GetInt32(2) != 0) : null;
    }
}

