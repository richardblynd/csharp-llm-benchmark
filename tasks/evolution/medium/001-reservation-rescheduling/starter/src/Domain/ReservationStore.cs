using Reservations.Models;

namespace Reservations.Domain;

public sealed partial class ReservationStore
{
    private readonly object gate = new();
    private readonly Dictionary<string, ReservationDto> reservations = new(StringComparer.Ordinal);

    public CreateResult Create(ReservationDto reservation)
    {
        lock (gate)
        {
            if (reservations.ContainsKey(reservation.Id))
            {
                return CreateResult.DuplicateId;
            }

            if (HasConflict(reservation))
            {
                return CreateResult.Conflict;
            }

            reservations.Add(reservation.Id, reservation);
            return CreateResult.Created;
        }
    }

    public ReservationDto? Find(string id)
    {
        lock (gate)
        {
            return reservations.GetValueOrDefault(id);
        }
    }

    public IReadOnlyList<ReservationDto> List(string roomId)
    {
        lock (gate)
        {
            return reservations.Values.Where(item => item.RoomId == roomId)
                .OrderBy(item => item.Start).ThenBy(item => item.Id, StringComparer.Ordinal).ToArray();
        }
    }

    private bool HasConflict(ReservationDto candidate, string? ignoredId = null)
    {
        return reservations.Values.Any(item => item.Id != ignoredId && item.RoomId == candidate.RoomId
            && item.Start < candidate.End && candidate.Start < item.End);
    }
}
