namespace Outbox;

public interface IEventPublisher
{
    Task PublishAsync(OutboxEvent item, CancellationToken cancellationToken);
}

public sealed class RecordingEventPublisher : IEventPublisher
{
    private readonly object gate = new();
    private readonly List<OutboxEvent> events = new();
    public IReadOnlyList<OutboxEvent> Events { get { lock (gate) return events.ToArray(); } }

    public Task PublishAsync(OutboxEvent item, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        lock (gate) events.Add(item);
        return Task.CompletedTask;
    }
}

