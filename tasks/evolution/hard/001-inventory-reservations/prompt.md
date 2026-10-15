Add durable stock reservations to the existing SQLite inventory service.
Keep every existing API and its behavior when no stock is reserved.

Add public record StockReservation(string ReservationId, string ProductId, int Quantity, bool Released)
and these InventoryService methods, all with CancellationToken cancellationToken = default:
- Task<StockReservation> ReserveAsync(string reservationId, string productId, int quantity, ...)
- Task<bool> ReleaseReservationAsync(string reservationId, ...)
- Task<StockReservation?> GetReservationAsync(string reservationId, ...)
- Task<int> GetAvailableStockAsync(string productId, ...)

Contracts:
- Persist reservations in the same SQLite database. InitializeAsync must also create the
  required schema idempotently and retain all existing products, movements and reservations.
  Records survive service recreation and opening a second connection to the same database.
  Preserve the existing database table/column contracts described in the README.
- Total Quantity remains the physical stock. Available stock is total Quantity minus the
  quantities of active reservations. Reservation/release operations do not add stock movements.
- Reserve requires positive quantity, normalized nonblank ids and an existing product.
  Reject invalid quantities with ArgumentOutOfRangeException and blank ids with ArgumentException.
  Unknown products and insufficient available stock throw InventoryException for that product.
- Reservation ids are global, ordinal and case-sensitive. Repeating an id with the SAME
  normalized product id and quantity returns its existing reservation without reserving again.
  This also applies to released reservations, which must stay released.
  Reusing an id with different product/quantity throws InventoryException without any changes.
- Release returns true exactly once for an active reservation, marks it Released and restores
  availability. A repeated release or unknown id returns false. Blank ids remain invalid.
- GetReservation returns the persisted record or null; GetAvailableStock throws InventoryException
  for unknown products. All returned records are immutable snapshots.
- Existing AdjustStockAsync and TransferAsync must not reduce total stock below its active
  reserved quantity. Such operations throw InventoryException and roll back balances and history.
  Adding stock, spending unreserved stock and receiving a transfer remain supported.
- All failures and caller cancellation preserve reservations, balances and movement history.
- Reservation capacity checks and writes must be atomic, including concurrent calls through
  separate service instances and separate connections to the SAME SQLite file.
  Two contenders cannot both reserve more than the available quantity.
  Availability reads must reflect a consistent database state across connections.
- Preserve connection ownership, disposal, history ordering, timestamp injection and old validation.
  Use the existing Microsoft.Data.Sqlite package. Do not use an external service or an in-memory
  replacement for persisted reservation data. Project files are immutable.
- Write English code and messages.

