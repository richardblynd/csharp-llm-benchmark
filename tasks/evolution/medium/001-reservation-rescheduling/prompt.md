Add atomic rescheduling to the existing working reservations HTTP API.

Inspect the project and its README. Preserve every existing route, response
contract, validation rule and per-application in-memory state isolation.

Add `PUT /reservations/{id}/schedule` accepting this JSON body:

```json
{
  "roomId": "room-b",
  "start": "2026-01-01T14:00:00",
  "end": "2026-01-01T15:00:00"
}
```

Rules:
- Validate the body first: null body, blank roomId or end <= start returns 400.
- A valid request for an unknown reservation id returns 404.
- A successful change returns 200 with the updated reservation DTO, keeping
  its original id. Both its time interval and room may change.
- The interval must not overlap another reservation in the target room.
  On conflict, return 409 and preserve the original reservation exactly.
- Exclude the reservation being changed from its own conflict check. A request
  for the existing room and interval is a successful no-op. Adjacent intervals
  are permitted.
- Successful changes must free the old slot and occupy the new slot. Existing
  GET routes must immediately reflect the updated reservation and room lists.
- Validation, missing-id and conflict failures must not remove or alter any
  reservation or leave an additional reservation behind.
- Rescheduling is atomic and shares conflict protection with POST creation:
  concurrent overlapping creates or reschedules in the same room cannot both
  succeed. Concurrent readers must never observe a reservation temporarily
  removed during a change.
- Keep the existing namespace conventions, DI registration and in-memory store.
  Do not add dependencies or require an external service or database.
- Write code, identifiers and messages in English. You may add or edit sources
  anywhere within the permitted paths; project files are immutable.
