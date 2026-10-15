namespace Reservations.Models;

public sealed record RescheduleRequest(string RoomId, DateTime Start, DateTime End);
