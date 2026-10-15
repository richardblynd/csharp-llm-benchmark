using Microsoft.Data.Sqlite;

namespace Inventory;

public sealed partial class InventoryService
{
    private void InitializeSchema(SqliteTransaction transaction)
    {
        Execute(transaction, @"
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY COLLATE BINARY, name TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity >= 0));
CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT NOT NULL,
    delta INTEGER NOT NULL, quantity_after INTEGER NOT NULL, occurred_at TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reservations (
    id TEXT PRIMARY KEY COLLATE BINARY, product_id TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity > 0),
    released INTEGER NOT NULL DEFAULT 0);
");
    }
}

