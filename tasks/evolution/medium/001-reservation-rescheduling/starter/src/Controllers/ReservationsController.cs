using Microsoft.AspNetCore.Mvc;
using Reservations.Domain;
using Reservations.Models;

namespace Reservations.Controllers;

[ApiController]
public sealed partial class ReservationsController : ControllerBase
{
    private readonly ReservationStore store;

    public ReservationsController(ReservationStore store)
    {
        this.store = store;
    }

    [HttpPost("/reservations")]
    public IActionResult Create([FromBody] ReservationDto? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.Id)
            || string.IsNullOrWhiteSpace(request.RoomId) || request.End <= request.Start)
        {
            return BadRequest();
        }

        var result = store.Create(request);
        return result == CreateResult.Created
            ? CreatedAtAction(nameof(Get), new { id = request.Id }, request)
            : Conflict();
    }

    [HttpGet("/reservations/{id}")]
    public IActionResult Get(string id)
    {
        var reservation = store.Find(id);
        return reservation is null ? NotFound() : Ok(reservation);
    }

    [HttpGet("/rooms/{roomId}/reservations")]
    public IActionResult List(string roomId) => Ok(store.List(roomId));
}
