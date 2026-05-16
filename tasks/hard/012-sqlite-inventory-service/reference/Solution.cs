using System;
using System.Collections.Generic;
using System.Data;
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
    private readonly SqliteConnection connection;
    private readonly bool ownsConnection;
    private readonly TimeProvider timeProvider;
    private bool disposed;

    public InventoryService(SqliteConnection? connection = null, TimeProvider? timeProvider = null)
    {
        ownsConnection = connection is null;
        this.connection = connection ?? new SqliteConnection("Data Source=:memory:");
        this.timeProvider = timeProvider ?? TimeProvider.System;
        if (this.connection.State != ConnectionState.Open)
        {
            this.connection.Open();
        }
    }

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        await using var command = connection.CreateCommand();
        command.CommandText = """
            CREATE TABLE IF NOT EXISTS Products (
                ProductId TEXT PRIMARY KEY NOT NULL,
                Name TEXT NOT NULL,
                Quantity INTEGER NOT NULL CHECK (Quantity >= 0)
            );
            CREATE TABLE IF NOT EXISTS Movements (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                ProductId TEXT NOT NULL,
                Delta INTEGER NOT NULL,
                QuantityAfter INTEGER NOT NULL,
                OccurredAt TEXT NOT NULL,
                Reason TEXT NOT NULL
            );
            """;
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    public async Task AddProductAsync(string productId, string name, int initialQuantity, CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        var id = Normalize(productId, nameof(productId));
        var productName = Normalize(name, nameof(name));
        if (initialQuantity < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(initialQuantity));
        }

        await using var transaction = (SqliteTransaction)await connection.BeginTransactionAsync(cancellationToken);
        await ExecuteAsync(
            "INSERT INTO Products (ProductId, Name, Quantity) VALUES ($id, $name, $quantity)",
            transaction,
            cancellationToken,
            ("$id", id),
            ("$name", productName),
            ("$quantity", initialQuantity));
        await InsertMovementAsync(id, initialQuantity, initialQuantity, "Initial stock", transaction, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }

    public async Task<ProductStock?> GetProductAsync(string productId, CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        var id = Normalize(productId, nameof(productId));
        await using var command = connection.CreateCommand();
        command.CommandText = "SELECT ProductId, Name, Quantity FROM Products WHERE ProductId = $id";
        command.Parameters.AddWithValue("$id", id);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        return await reader.ReadAsync(cancellationToken)
            ? new ProductStock(reader.GetString(0), reader.GetString(1), reader.GetInt32(2))
            : null;
    }

    public async Task AdjustStockAsync(string productId, int delta, string reason, CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        var id = Normalize(productId, nameof(productId));
        var movementReason = Normalize(reason, nameof(reason));
        await using var transaction = (SqliteTransaction)await connection.BeginTransactionAsync(cancellationToken);
        try
        {
            await AdjustStockInsideTransactionAsync(id, delta, movementReason, transaction, cancellationToken);
            await transaction.CommitAsync(cancellationToken);
        }
        catch
        {
            await transaction.RollbackAsync(cancellationToken);
            throw;
        }
    }

    public async Task TransferAsync(string fromProductId, string toProductId, int quantity, string reason, CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        if (quantity <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(quantity));
        }

        var from = Normalize(fromProductId, nameof(fromProductId));
        var to = Normalize(toProductId, nameof(toProductId));
        var movementReason = Normalize(reason, nameof(reason));
        await using var transaction = (SqliteTransaction)await connection.BeginTransactionAsync(cancellationToken);
        try
        {
            await AdjustStockInsideTransactionAsync(from, -quantity, movementReason, transaction, cancellationToken);
            await AdjustStockInsideTransactionAsync(to, quantity, movementReason, transaction, cancellationToken);
            await transaction.CommitAsync(cancellationToken);
        }
        catch
        {
            await transaction.RollbackAsync(cancellationToken);
            throw;
        }
    }

    public async Task<IReadOnlyList<InventoryMovement>> GetMovementsAsync(string productId, DateTimeOffset? from = null, DateTimeOffset? to = null, CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        var id = Normalize(productId, nameof(productId));
        await using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT Id, ProductId, Delta, QuantityAfter, OccurredAt, Reason
            FROM Movements
            WHERE ProductId = $id
              AND ($from IS NULL OR OccurredAt >= $from)
              AND ($to IS NULL OR OccurredAt <= $to)
            ORDER BY Id
            """;
        command.Parameters.AddWithValue("$id", id);
        command.Parameters.AddWithValue("$from", from?.UtcDateTime.ToString("O") ?? (object)DBNull.Value);
        command.Parameters.AddWithValue("$to", to?.UtcDateTime.ToString("O") ?? (object)DBNull.Value);
        var result = new List<InventoryMovement>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new InventoryMovement(
                reader.GetInt64(0),
                reader.GetString(1),
                reader.GetInt32(2),
                reader.GetInt32(3),
                DateTimeOffset.Parse(reader.GetString(4)),
                reader.GetString(5)));
        }

        return result;
    }

    public void Dispose()
    {
        if (disposed)
        {
            return;
        }

        if (ownsConnection)
        {
            connection.Dispose();
        }

        disposed = true;
    }

    private async Task AdjustStockInsideTransactionAsync(string productId, int delta, string reason, SqliteTransaction transaction, CancellationToken cancellationToken)
    {
        var current = await GetQuantityAsync(productId, transaction, cancellationToken);
        var next = current + delta;
        if (next < 0)
        {
            throw new InventoryException(productId, "Stock cannot become negative.");
        }

        await ExecuteAsync(
            "UPDATE Products SET Quantity = $quantity WHERE ProductId = $id",
            transaction,
            cancellationToken,
            ("$quantity", next),
            ("$id", productId));
        await InsertMovementAsync(productId, delta, next, reason, transaction, cancellationToken);
    }

    private async Task<int> GetQuantityAsync(string productId, SqliteTransaction transaction, CancellationToken cancellationToken)
    {
        await using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = "SELECT Quantity FROM Products WHERE ProductId = $id";
        command.Parameters.AddWithValue("$id", productId);
        var value = await command.ExecuteScalarAsync(cancellationToken);
        if (value is null)
        {
            throw new InventoryException(productId, "Product was not found.");
        }

        return Convert.ToInt32(value);
    }

    private async Task InsertMovementAsync(string productId, int delta, int quantityAfter, string reason, SqliteTransaction transaction, CancellationToken cancellationToken)
    {
        await ExecuteAsync(
            "INSERT INTO Movements (ProductId, Delta, QuantityAfter, OccurredAt, Reason) VALUES ($id, $delta, $quantityAfter, $occurredAt, $reason)",
            transaction,
            cancellationToken,
            ("$id", productId),
            ("$delta", delta),
            ("$quantityAfter", quantityAfter),
            ("$occurredAt", timeProvider.GetUtcNow().UtcDateTime.ToString("O")),
            ("$reason", reason));
    }

    private async Task ExecuteAsync(string sql, SqliteTransaction transaction, CancellationToken cancellationToken, params (string Name, object Value)[] parameters)
    {
        await using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = sql;
        foreach (var (name, value) in parameters)
        {
            command.Parameters.AddWithValue(name, value);
        }

        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private void ThrowIfDisposed()
    {
        ObjectDisposedException.ThrowIf(disposed, this);
    }

    private static string Normalize(string value, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException("Value is required.", parameterName);
        }

        return value.Trim();
    }
}
