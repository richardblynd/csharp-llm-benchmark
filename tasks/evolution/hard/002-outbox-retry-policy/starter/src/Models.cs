namespace Outbox;

public sealed record OutboxEvent(
    string EventId, string CommandId, string Type, string Payload, string Status, int Attempts);

