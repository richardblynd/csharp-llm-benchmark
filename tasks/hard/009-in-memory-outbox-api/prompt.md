Write an in-memory outbox API and background worker.

The generated file must be `Controllers/CommandsController.cs`.
The template already contains `Program.cs` and registers controllers, `OutboxStore`,
`IEventPublisher`, `RecordingEventPublisher` and `OutboxWorker` through dependency
injection. Do not declare a `Program` class, do not add top-level application
startup code, and do not create a second web application.

Required public surface:

```csharp
public sealed record CommandRequest(string CommandId, string Type, string Payload);
public sealed record CommandStatus(string CommandId, string Status, string EventId, string EventStatus);
public sealed record OutboxEvent(string EventId, string CommandId, string Type, string Payload, string Status, int Attempts);

public interface IEventPublisher
{
    Task PublishAsync(OutboxEvent item, CancellationToken cancellationToken);
}

public sealed class OutboxStore { }
public sealed class OutboxWorker : BackgroundService
{
    public Task<int> PublishPendingAsync(CancellationToken cancellationToken = default)
}
public sealed class RecordingEventPublisher : IEventPublisher { }
```

Required HTTP endpoints:
- `POST /commands` accepts `CommandRequest`, validates it, stores the command and one outbox event atomically, and returns `201 Created` with `CommandStatus`.
- `GET /commands/{commandId}` returns the command status or `404`.
- `GET /outbox/{eventId}` returns the outbox event or `404`.

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- Command ids, types and payloads must be non-empty after trimming.
- A command is stored with status `Accepted`; a new event starts with status `Pending`.
- Repeating the same command id should return the existing command status without creating a second event.
- Event ids must be deterministic and stable within a process, such as `evt-0001`.
- `OutboxWorker.PublishPendingAsync` publishes pending events through the injected `IEventPublisher`.
- After a successful publish, the event status becomes `Published` and must never be published again.
- If publishing fails, the event remains pending, its attempt count is preserved, and a later call can retry it.
- The worker must respect cancellation before publishing each event.
- `RecordingEventPublisher` is the default publisher and records published events in memory.
- The publisher must be replaceable in tests through dependency injection.
- The store and worker must be safe under concurrent access.
