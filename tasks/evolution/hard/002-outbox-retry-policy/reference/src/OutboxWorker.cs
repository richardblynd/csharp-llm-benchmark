namespace Outbox;

public sealed class OutboxWorker
{
    private readonly OutboxStore store;
    private readonly IEventPublisher publisher;
    private readonly TimeProvider clock;
    private readonly RetryPolicy? policy;

    public OutboxWorker(OutboxStore store, IEventPublisher publisher, TimeProvider? timeProvider = null, RetryPolicy? retryPolicy = null)
    {
        this.store = store ?? throw new ArgumentNullException(nameof(store));
        this.publisher = publisher ?? throw new ArgumentNullException(nameof(publisher));
        clock = timeProvider ?? TimeProvider.System;
        if (retryPolicy is not null && (retryPolicy.MaxAttempts <= 0
            || retryPolicy.InitialDelay < TimeSpan.Zero || retryPolicy.MaxDelay < retryPolicy.InitialDelay))
            throw new ArgumentOutOfRangeException(nameof(retryPolicy));
        policy = retryPolicy;
    }

    public async Task<int> PublishPendingAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var published = 0;
        foreach (var pending in store.GetPending())
        {
            cancellationToken.ThrowIfCancellationRequested();
            var attempt = store.TryClaim(pending.EventId, clock.GetUtcNow());
            if (attempt is null) continue;
            try
            {
                cancellationToken.ThrowIfCancellationRequested();
                await publisher.PublishAsync(attempt, cancellationToken);
                store.Complete(attempt.EventId, "Published", null, null);
                published++;
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                store.ReturnCancelled(attempt.EventId);
                throw;
            }
            catch (Exception error)
            {
                var exhausted = policy is not null && attempt.Attempts >= policy.MaxAttempts;
                var next = policy is null || exhausted ? (DateTimeOffset?)null : DueAt(attempt.Attempts);
                store.Complete(attempt.EventId, exhausted ? "DeadLetter" : "Pending", next, error.Message);
            }
        }
        return published;
    }
    private DateTimeOffset DueAt(int attempts)
    {
        var delayTicks = policy!.InitialDelay.Ticks;
        var capTicks = policy.MaxDelay.Ticks;
        if (delayTicks > 0)
            for (var k = 1; k < attempts && delayTicks < capTicks; k++)
                delayTicks = delayTicks > capTicks / 2 ? capTicks : delayTicks * 2;
        var now = clock.GetUtcNow();
        return now.AddTicks(Math.Min(delayTicks, (DateTimeOffset.MaxValue - now).Ticks));
    }
}

