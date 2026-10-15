# Inventory
Working .NET 8 SQLite inventory library. Microsoft.Data.Sqlite 8.0.0 is already
referenced. Build: dotnet build Inventory.csproj --configuration Release.

Use InventoryService(connection = null, timeProvider = null), then InitializeAsync.
Without a supplied connection, the service owns a private in-memory database.
With a supplied connection, it opens it if necessary and leaves it open at disposal.
Repeated initialization preserves rows. Products and movement history are stored in SQLite.

Existing public API:
- AddProductAsync(productId, name, initialQuantity, cancellationToken = default)
  inserts the product and one movement whose reason is Initial stock.
- GetProductAsync(productId, cancellationToken = default) returns ProductStock or null.
- AdjustStockAsync(productId, delta, reason, cancellationToken = default) changes stock
  and records its delta, resulting quantity, injected-clock timestamp and reason.
- TransferAsync(fromProductId, toProductId, quantity, reason, cancellationToken = default)
  subtracts/adds stock and records one movement for each product in one transaction.
- GetMovementsAsync(productId, from = null, to = null, cancellationToken = default)
  returns movements in ascending Id order. Time bounds are inclusive; missing ids return [].
- ProductStock contains ProductId, Name, Quantity. InventoryMovement contains Id,
  ProductId, Delta, QuantityAfter, OccurredAt, Reason.

Identifiers, names and reasons are trimmed, must not be blank, and compare ordinally.
Initial quantities cannot be negative (ArgumentOutOfRangeException). Transfers require
positive quantity and distinct ids (ArgumentOutOfRangeException / ArgumentException).
Duplicate or missing products and insufficient stock throw InventoryException with ProductId.
Checked quantity overflow fails without changing rows. Adjustments and transfers are atomic,
including when a database statement fails: balances and history roll back together.
The existing products(id, name, quantity) and movements(id, product_id, delta,
quantity_after, occurred_at, reason) tables are part of the database integration
contract. Preserve their names and columns; callers may install triggers through
their supplied connection.
All calls accept cancellation; a pre-cancelled token causes no database changes.
Operations on a service are serialized, reads return snapshots, and Dispose is idempotent.

