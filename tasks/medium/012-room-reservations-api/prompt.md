Create the generated file `Controllers/ReservationsController.cs` for an ASP.NET Core API.

Required public surface:
- A controller for reservations.
- A public `ReservationStore` service registered by the template.
- A public `ReservationDto` model or record with `Id`, `RoomId`, `Start` and `End`.

Routes:
- `POST /reservations` creates a reservation.
- `GET /rooms/{roomId}/reservations` lists reservations for one room.

Suggested shape:

```csharp
public sealed record ReservationDto(string Id, string RoomId, DateTime Start, DateTime End);
```

Rules:
- Do not include a namespace.
- Do not use external libraries.
- All code, public identifiers, exception messages and comments must be written in English.
- Reservation JSON fields are `id`, `roomId`, `start` and `end`.
- Reject blank ids or room ids, and reject intervals where `end <= start`, with `400`.
- Reject overlapping reservations in the same room with `409`.
- Adjacent reservations are allowed.
- The same time range is allowed in different rooms.
- Room reservation lists must be sorted by `start`, then by `id` ordinally.
- Keep data in memory for the lifetime of the app instance.
