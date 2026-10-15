using Microsoft.AspNetCore.Mvc;
using Reservations.Domain;
using Reservations.Models;

namespace Reservations.Controllers;

public sealed partial class ReservationsController
{
    [HttpPut("/reservations/{id}/schedule")]
    public IActionResult Reschedule(string id, [FromBody] RescheduleRequest? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.RoomId) || request.End <= request.Start)
        {
            return BadRequest();
        }

        var result = store.Reschedule(id, request.RoomId, request.Start, request.End, out var updated);
        return result switch
        {
            RescheduleResult.Updated => Ok(updated),
            RescheduleResult.NotFound => NotFound(),
            _ => Conflict()
        };
    }
}
