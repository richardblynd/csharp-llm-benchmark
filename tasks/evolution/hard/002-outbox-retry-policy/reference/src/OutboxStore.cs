namespace Outbox;

public sealed class OutboxStore
{
    private readonly object gate = new();
    private readonly Dictionary<string, OutboxEvent> events = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> commands = new(StringComparer.Ordinal);
    private readonly HashSet<string> claimed = new(StringComparer.Ordinal);
    private readonly List<string> order = new();
    private long nextId;

    public OutboxEvent Enqueue(string commandId, string type, string payload)
    {
        commandId = Text(commandId);
        type = Text(type);
        payload = Text(payload);
        lock (gate)
        {
            if (commands.TryGetValue(commandId, out var existingId)) return events[existingId];
            var id = $"evt-{++nextId:D4}";
            var item = new OutboxEvent(id, commandId, type, payload, "Pending", 0);
            events.Add(id, item);
            commands.Add(commandId, id);
            order.Add(id);
            return item;
        }
    }

    public OutboxEvent? GetEvent(string eventId)
    {
        eventId = Text(eventId);
        lock (gate) return events.GetValueOrDefault(eventId);
    }

    public IReadOnlyList<OutboxEvent> GetPending()
    {
        lock (gate) return order.Select(id => events[id]).Where(item => item.Status == "Pending").ToArray();
    }

    internal OutboxEvent? TryClaim(string eventId, DateTimeOffset now)
    {
        lock (gate)
        {
            var item = events[eventId];
            if (item.Status != "Pending" || claimed.Contains(eventId)
                || (item.NextAttemptAt is not null && now < item.NextAttemptAt)) return null;
            claimed.Add(eventId);
            item = item with { Attempts = checked(item.Attempts + 1) };
            events[eventId] = item;
            return item;
        }
    }

    internal void Complete(string eventId, string status, DateTimeOffset? nextAttemptAt, string? error)
    {
        lock (gate)
        {
            events[eventId] = events[eventId] with { Status = status, NextAttemptAt = nextAttemptAt, LastError = error };
            claimed.Remove(eventId);
        }
    }

    internal void ReturnCancelled(string eventId)
    {
        lock (gate)
        {
            if (!claimed.Remove(eventId)) return;
            events[eventId] = events[eventId] with { Attempts = events[eventId].Attempts - 1 };
        }
    }

    private static string Text(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) throw new ArgumentException("Value must not be blank.");
        return value.Trim();
    }
}

