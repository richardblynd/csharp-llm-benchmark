The in-memory API provides POST /todos with {id,title}, GET /todos, GET /todos/{id} and
DELETE /todos/{id}. Positive ids and nonblank titles are required (400); titles are trimmed.
Duplicate ids return 409. Creation returns 201, Location /todos/{id}, and an incomplete Todo.
GET all orders by ascending id; GET missing returns 404; delete returns 204 or 404.
Each application has its own store. Reads are immutable snapshots. Store operations use
one lock, so concurrent creates cannot duplicate an id. No packages may be added.

Build: dotnet build Todos.csproj --configuration Release
