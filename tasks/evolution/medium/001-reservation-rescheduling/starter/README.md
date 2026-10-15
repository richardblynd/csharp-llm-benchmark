# Reservations

Working ASP.NET Core .NET 8 API with a singleton, in-memory reservation store
scoped to the lifetime of each application instance. Build with
`dotnet build Reservations.csproj --configuration Release`.

Existing public HTTP contracts:
- `POST /reservations` takes `id`, `roomId`, `start`, `end`. On success it returns
  201, a Location header `/reservations/{id}` and the created reservation DTO.
- Null body, blank id/roomId and intervals with end <= start return 400.
- Duplicate ids return 409. Ids are globally unique within an application.
- Overlapping reservations in the same room return 409. Two intervals overlap
  if each starts before the other ends. Adjacent intervals are allowed.
- Reservations in different rooms are independent, even at identical times.
- `GET /reservations/{id}` returns the stored DTO with 200 or 404 when absent.
- `GET /rooms/{roomId}/reservations` returns 200 with that room's reservations
  ordered by start, then by id using ordinal comparison. An empty room returns [].
- JSON uses the lowercase/camelCase fields `id`, `roomId`, `start`, `end`.
- Ids and roomIds are compared ordinally and stored without normalization.
- Creation, reads and lists are protected by the store's synchronization lock.

The controller handles HTTP validation and delegates to the domain store.
Models are immutable records. Tests and external dependencies are not required
to run this application.
