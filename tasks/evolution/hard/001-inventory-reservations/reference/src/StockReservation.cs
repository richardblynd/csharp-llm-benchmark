namespace Inventory;

public sealed record StockReservation(string ReservationId, string ProductId, int Quantity, bool Released);

