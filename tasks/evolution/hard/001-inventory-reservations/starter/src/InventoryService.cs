using System.Data;
using System.Globalization;
using Microsoft.Data.Sqlite;

namespace Inventory;

public sealed partial class InventoryService : IDisposable
{
    private readonly SqliteConnection connection;
    private readonly bool ownsConnection;
    private readonly TimeProvider clock;
    private readonly SemaphoreSlim gate = new(1, 1);
    private bool disposed;

    public InventoryService(SqliteConnection? connection = null, TimeProvider? timeProvider = null)
    {
        this.connection = connection ?? new SqliteConnection("Data Source=:memory:");
        ownsConnection = connection is null;
        clock = timeProvider ?? TimeProvider.System;
    }

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        await gate.WaitAsync(cancellationToken);
        try
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            if (connection.State != ConnectionState.Open) await connection.OpenAsync(cancellationToken);
            using var transaction = connection.BeginTransaction();
            InitializeSchema(transaction);
            cancellationToken.ThrowIfCancellationRequested();
            transaction.Commit();
        }
        finally { gate.Release(); }
    }

    public async Task AddProductAsync(string productId, string name, int initialQuantity, CancellationToken cancellationToken = default)
    {
        productId = Text(productId); name = Text(name);
        if (initialQuantity < 0) throw new ArgumentOutOfRangeException(nameof(initialQuantity));
        await WriteAsync(transaction => {
            if (FindStock(productId, transaction) is not null) throw new InventoryException(productId, "Product already exists.");
            Execute(transaction, "INSERT INTO products(id, name, quantity) VALUES($id, $name, $quantity)",
                ("$id", productId), ("$name", name), ("$quantity", initialQuantity));
            AddMovement(productId, initialQuantity, initialQuantity, "Initial stock", transaction);
            return 0;
        }, cancellationToken);
    }

    public Task<ProductStock?> GetProductAsync(string productId, CancellationToken cancellationToken = default)
    {
        productId = Text(productId);
        return ReadAsync(() => FindStock(productId), cancellationToken);
    }

    public async Task AdjustStockAsync(string productId, int delta, string reason, CancellationToken cancellationToken = default)
    {
        productId = Text(productId); reason = Text(reason);
        await WriteAsync(transaction => {
            var product = RequiredStock(productId, transaction);
            var next = checked(product.Quantity + delta);
            CheckQuantity(productId, next, transaction);
            Execute(transaction, "UPDATE products SET quantity=$quantity WHERE id=$id", ("$quantity", next), ("$id", productId));
            AddMovement(productId, delta, next, reason, transaction);
            return 0;
        }, cancellationToken);
    }

    public async Task TransferAsync(string fromProductId, string toProductId, int quantity, string reason, CancellationToken cancellationToken = default)
    {
        fromProductId = Text(fromProductId); toProductId = Text(toProductId); reason = Text(reason);
        if (quantity <= 0) throw new ArgumentOutOfRangeException(nameof(quantity));
        if (fromProductId == toProductId) throw new ArgumentException("Products must differ.");
        await WriteAsync(transaction => {
            var source = RequiredStock(fromProductId, transaction);
            var target = RequiredStock(toProductId, transaction);
            var remaining = checked(source.Quantity - quantity);
            var increased = checked(target.Quantity + quantity);
            CheckQuantity(fromProductId, remaining, transaction);
            Execute(transaction, "UPDATE products SET quantity=$quantity WHERE id=$id", ("$quantity", remaining), ("$id", fromProductId));
            AddMovement(fromProductId, -quantity, remaining, reason, transaction);
            Execute(transaction, "UPDATE products SET quantity=$quantity WHERE id=$id", ("$quantity", increased), ("$id", toProductId));
            AddMovement(toProductId, quantity, increased, reason, transaction);
            return 0;
        }, cancellationToken);
    }

    public Task<IReadOnlyList<InventoryMovement>> GetMovementsAsync(string productId, DateTimeOffset? from = null,
        DateTimeOffset? to = null, CancellationToken cancellationToken = default)
    {
        productId = Text(productId);
        return ReadAsync<IReadOnlyList<InventoryMovement>>(() => {
            using var command = Command(null, "SELECT id, delta, quantity_after, occurred_at, reason FROM movements WHERE product_id=$id ORDER BY id", ("$id", productId));
            using var reader = command.ExecuteReader();
            var result = new List<InventoryMovement>();
            while (reader.Read())
            {
                var at = DateTimeOffset.Parse(reader.GetString(3), CultureInfo.InvariantCulture);
                if ((from is null || at >= from) && (to is null || at <= to))
                    result.Add(new InventoryMovement(reader.GetInt64(0), productId, reader.GetInt32(1), reader.GetInt32(2), at, reader.GetString(4)));
            }
            return result.AsReadOnly();
        }, cancellationToken);
    }

    private ProductStock? FindStock(string productId, SqliteTransaction? transaction = null)
    {
        using var command = Command(transaction, "SELECT name, quantity FROM products WHERE id=$id", ("$id", productId));
        using var reader = command.ExecuteReader();
        return reader.Read() ? new ProductStock(productId, reader.GetString(0), reader.GetInt32(1)) : null;
    }

    private ProductStock RequiredStock(string productId, SqliteTransaction? transaction = null)
        => FindStock(productId, transaction) ?? throw new InventoryException(productId, "Product does not exist.");

    private void AddMovement(string productId, int delta, int after, string reason, SqliteTransaction transaction)
    {
        Execute(transaction, "INSERT INTO movements(product_id, delta, quantity_after, occurred_at, reason) VALUES($id,$delta,$after,$at,$reason)",
            ("$id", productId), ("$delta", delta), ("$after", after),
            ("$at", clock.GetUtcNow().ToString("O", CultureInfo.InvariantCulture)), ("$reason", reason));
    }

    private SqliteCommand Command(SqliteTransaction? transaction, string sql, params (string Name, object? Value)[] parameters)
    {
        var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = sql;
        foreach (var parameter in parameters) command.Parameters.AddWithValue(parameter.Name, parameter.Value ?? DBNull.Value);
        return command;
    }

    private void Execute(SqliteTransaction? transaction, string sql, params (string Name, object? Value)[] parameters)
    {
        using var command = Command(transaction, sql, parameters);
        command.ExecuteNonQuery();
    }

    private async Task<T> ReadAsync<T>(Func<T> read, CancellationToken cancellationToken)
    {
        await gate.WaitAsync(cancellationToken);
        try { ObjectDisposedException.ThrowIf(disposed, this); cancellationToken.ThrowIfCancellationRequested(); return read(); }
        finally { gate.Release(); }
    }

    private async Task<T> WriteAsync<T>(Func<SqliteTransaction, T> write, CancellationToken cancellationToken)
    {
        await gate.WaitAsync(cancellationToken);
        try
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            using var transaction = connection.BeginTransaction();
            var result = write(transaction);
            cancellationToken.ThrowIfCancellationRequested();
            transaction.Commit();
            return result;
        }
        finally { gate.Release(); }
    }

    private static string Text(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) throw new ArgumentException("Value must not be blank.");
        return value.Trim();
    }

    public void Dispose()
    {
        gate.Wait();
        try { if (!disposed) { if (ownsConnection) connection.Dispose(); disposed = true; } }
        finally { gate.Release(); }
    }
}

