namespace Outbox;

public sealed class OutboxWorker
{
    private readonly OutboxStore store;
    private readonly IEventPublisher publisher;
    private readonly TimeProvider clock;

    public OutboxWorker(OutboxStore store, IEventPublisher publisher, TimeProvider? timeProvider = null)
    {
        this.store = store ?? throw new ArgumentNullException(nameof(store));
        this.publisher = publisher ?? throw new ArgumentNullException(nameof(publisher));
        clock = timeProvider ?? TimeProvider.System;
    }

    public async Task<int> PublishPendingAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var published = 0;
        foreach (var pending in store.GetPending())
        {
            cancellationToken.ThrowIfCancellationRequested();
            var attempt = store.TryClaim(pending.EventId);
            if (attempt is null) continue;
            try
            {
                cancellationToken.ThrowIfCancellationRequested();
                await publisher.PublishAsync(attempt, cancellationToken);
                store.Complete(attempt.EventId, true);
                published++;
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                store.ReturnCancelled(attempt.EventId);
                throw;
            }
            catch (Exception)
            {
                store.Complete(attempt.EventId, false);
            }
        }
        return published;
    }
}

