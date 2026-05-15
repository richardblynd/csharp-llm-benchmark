Write a public class named `CalendarScheduler` and a public immutable record or class named `CalendarEvent`.

Required public API:

```csharp
public sealed class CalendarEvent
{
    public string Id { get; }
    public DateTime Start { get; }
    public DateTime End { get; }
}

public bool AddEvent(string id, DateTime start, DateTime end)
public IReadOnlyList<CalendarEvent> ListEvents()
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- `AddEvent` returns `true` and stores the event when it does not overlap an existing event.
- `AddEvent` returns `false` when the interval overlaps any existing event.
- Adjacent events are allowed: an event ending at 10:00 and another starting at 10:00 do not overlap.
- Throw an argument exception if `id` is null/blank or `end` is less than or equal to `start`.
- `ListEvents` returns events sorted by `Start`, then by `Id` ordinally.
