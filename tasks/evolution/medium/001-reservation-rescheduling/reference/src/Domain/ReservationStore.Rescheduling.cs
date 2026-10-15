using Reservations.Models;

namespace Reservations.Domain;

public sealed partial class ReservationStore
{
    public RescheduleResult Reschedule(string id, string roomId, DateTime start, DateTime end,
                                       out ReservationDto? updated)
    {
        lock (gate)
        {
            updated = null;
            if (!reservations.TryGetValue(id, out var original))
            {
                return RescheduleResult.NotFound;
            }

            var candidate = original with { RoomId = roomId, Start = start, End = end };
            if (HasConflict(candidate, id))
            {
                return RescheduleResult.Conflict;
            }

            reservations[id] = candidate;
            updated = candidate;
            return RescheduleResult.Updated;
        }
    }
}
