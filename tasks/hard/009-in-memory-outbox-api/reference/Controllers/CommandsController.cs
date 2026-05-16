using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Hosting;

[ApiController]
public sealed class CommandsController : ControllerBase
{
    private readonly OutboxStore store;

    public CommandsController(OutboxStore store)
    {
        this.store = store;
    }

    [HttpPost("/commands")]
    public IActionResult Create([FromBody] CommandRequest? request)
    {
        var validation = Validate(request);
        if (validation is not null)
        {
            return BadRequest(new { error = validation });
        }

        var status = store.Enqueue(request!);
        return CreatedAtAction(nameof(GetCommand), new { commandId = status.CommandId }, status);
    }

    [HttpGet("/commands/{commandId}")]
    public IActionResult GetCommand(string commandId)
    {
        var status = store.FindCommand(commandId);
        return status is null ? NotFound() : Ok(status);
    }

    [HttpGet("/outbox/{eventId}")]
    public IActionResult GetEvent(string eventId)
    {
        var item = store.FindEvent(eventId);
        return item is null ? NotFound() : Ok(item);
    }

    private static string? Validate(CommandRequest? request)
    {
        if (request is null)
        {
            return "Request body is required.";
        }

        if (string.IsNullOrWhiteSpace(request.CommandId))
        {
            return "Command id is required.";
        }

        if (string.IsNullOrWhiteSpace(request.Type))
        {
            return "Command type is required.";
        }

        if (string.IsNullOrWhiteSpace(request.Payload))
        {
            return "Payload is required.";
        }

        return null;
    }
}

public sealed record CommandRequest(string CommandId, string Type, string Payload);
public sealed record CommandStatus(string CommandId, string Status, string EventId, string EventStatus);
public sealed record OutboxEvent(string EventId, string CommandId, string Type, string Payload, string Status, int Attempts);

public interface IEventPublisher
{
    Task PublishAsync(OutboxEvent item, CancellationToken cancellationToken);
}

public sealed class OutboxStore
{
    private readonly object gate = new();
    private readonly Dictionary<string, CommandStatus> commands = new(StringComparer.Ordinal);
    private readonly Dictionary<string, OutboxEvent> events = new(StringComparer.Ordinal);
    private int nextEventId;

    public CommandStatus Enqueue(CommandRequest request)
    {
        var commandId = request.CommandId.Trim();
        lock (gate)
        {
            if (commands.TryGetValue(commandId, out var existing))
            {
                return RefreshStatus(existing);
            }

            var eventId = $"evt-{++nextEventId:0000}";
            var item = new OutboxEvent(eventId, commandId, request.Type.Trim(), request.Payload.Trim(), "Pending", 0);
            events[eventId] = item;
            var status = new CommandStatus(commandId, "Accepted", eventId, item.Status);
            commands[commandId] = status;
            return status;
        }
    }

    public CommandStatus? FindCommand(string commandId)
    {
        if (string.IsNullOrWhiteSpace(commandId))
        {
            return null;
        }

        lock (gate)
        {
            return commands.TryGetValue(commandId.Trim(), out var status) ? RefreshStatus(status) : null;
        }
    }

    public OutboxEvent? FindEvent(string eventId)
    {
        if (string.IsNullOrWhiteSpace(eventId))
        {
            return null;
        }

        lock (gate)
        {
            return events.GetValueOrDefault(eventId.Trim());
        }
    }

    public IReadOnlyList<OutboxEvent> PendingEvents()
    {
        lock (gate)
        {
            return events.Values
                .Where(item => item.Status == "Pending")
                .OrderBy(item => item.EventId, StringComparer.Ordinal)
                .ToArray();
        }
    }

    public OutboxEvent? BeginPublish(string eventId)
    {
        lock (gate)
        {
            if (!events.TryGetValue(eventId, out var item) || item.Status == "Published")
            {
                return null;
            }

            var updated = item with { Attempts = item.Attempts + 1 };
            events[eventId] = updated;
            return updated;
        }
    }

    public void MarkPublished(string eventId)
    {
        lock (gate)
        {
            if (events.TryGetValue(eventId, out var item))
            {
                events[eventId] = item with { Status = "Published" };
            }
        }
    }

    public void MarkPending(string eventId)
    {
        lock (gate)
        {
            if (events.TryGetValue(eventId, out var item) && item.Status != "Published")
            {
                events[eventId] = item with { Status = "Pending" };
            }
        }
    }

    private CommandStatus RefreshStatus(CommandStatus status)
    {
        var eventStatus = events.TryGetValue(status.EventId, out var item) ? item.Status : status.EventStatus;
        return status with { EventStatus = eventStatus };
    }
}

public sealed class OutboxWorker : BackgroundService
{
    private readonly OutboxStore store;
    private readonly IEventPublisher publisher;

    public OutboxWorker(OutboxStore store, IEventPublisher publisher)
    {
        this.store = store;
        this.publisher = publisher;
    }

    public async Task<int> PublishPendingAsync(CancellationToken cancellationToken = default)
    {
        var published = 0;
        foreach (var pending in store.PendingEvents())
        {
            cancellationToken.ThrowIfCancellationRequested();
            var item = store.BeginPublish(pending.EventId);
            if (item is null)
            {
                continue;
            }

            try
            {
                await publisher.PublishAsync(item, cancellationToken);
                store.MarkPublished(item.EventId);
                published++;
            }
            catch
            {
                store.MarkPending(item.EventId);
            }
        }

        return published;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            await PublishPendingAsync(stoppingToken);
            await Task.Delay(TimeSpan.FromMilliseconds(100), stoppingToken);
        }
    }
}

public sealed class RecordingEventPublisher : IEventPublisher
{
    private readonly object gate = new();
    private readonly List<OutboxEvent> published = new();

    public IReadOnlyList<OutboxEvent> Published
    {
        get
        {
            lock (gate)
            {
                return published.ToArray();
            }
        }
    }

    public Task PublishAsync(OutboxEvent item, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        lock (gate)
        {
            published.Add(item);
        }

        return Task.CompletedTask;
    }
}
