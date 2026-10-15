namespace Reservations.Models;

public sealed record ReservationDto(string Id, string RoomId, DateTime Start, DateTime End);
