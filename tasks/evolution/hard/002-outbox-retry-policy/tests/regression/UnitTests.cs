using Microsoft.VisualStudio.TestTools.UnitTesting;
using Outbox;

[TestClass]
public sealed class RegressionTests
{
    private sealed class Publisher(Func<OutboxEvent, CancellationToken, Task> send) : IEventPublisher
    {
        public Task PublishAsync(OutboxEvent item, CancellationToken cancellationToken) => send(item, cancellationToken);
    }

    [TestMethod]
    public void old_enqueue_is_idempotent_normalized_and_validated()
    {
        var store = new OutboxStore();
        var first = store.Enqueue(" c1 ", " kind ", " body ");
        Assert.AreEqual("c1", first.CommandId);
        Assert.AreEqual("kind", first.Type);
        Assert.AreEqual("body", first.Payload);
        Assert.AreEqual("evt-0001", first.EventId);
        Assert.AreEqual("Pending", first.Status);
        Assert.AreEqual(0, first.Attempts);
        Assert.AreEqual(first, store.Enqueue("c1", "other", "changed"));
        Assert.AreEqual(1, store.GetPending().Count);
        Assert.AreNotEqual(first.EventId, store.Enqueue("C1", "kind", "body").EventId);
        Assert.IsNull(store.GetEvent("absent"));
        foreach (var values in new[] { (" ", "kind", "body"), ("id", "", "body"), ("id", "kind", " ") })
            Assert.ThrowsException<ArgumentException>(() => store.Enqueue(values.Item1, values.Item2, values.Item3));
    }

    [TestMethod]
    public async Task old_successful_events_publish_once_in_order()
    {
        var store = new OutboxStore();
        var a = store.Enqueue("a", "kind", "body");
        var b = store.Enqueue("b", "kind", "body");
        var publisher = new RecordingEventPublisher();
        var worker = new OutboxWorker(store, publisher);
        Assert.AreEqual(2, await worker.PublishPendingAsync());
        CollectionAssert.AreEqual(new[] { a.EventId, b.EventId }, publisher.Events.Select(e => e.EventId).ToArray());
        Assert.AreEqual("Published", store.GetEvent(a.EventId)!.Status);
        Assert.AreEqual(1, store.GetEvent(a.EventId)!.Attempts);
        Assert.AreEqual(0, await worker.PublishPendingAsync());
        Assert.AreEqual(2, publisher.Events.Count);
        Assert.AreEqual(0, store.GetPending().Count);
    }

    [TestMethod]
    public async Task old_failures_retry_immediately_without_a_limit()
    {
        var store = new OutboxStore();
        var item = store.Enqueue("c", "kind", "body");
        var worker = new OutboxWorker(store, new Publisher((_, _) => throw new InvalidOperationException("offline")));
        for (var attempt = 1; attempt <= 12; attempt++)
        {
            Assert.AreEqual(0, await worker.PublishPendingAsync());
            Assert.AreEqual("Pending", store.GetEvent(item.EventId)!.Status);
            Assert.AreEqual(attempt, store.GetEvent(item.EventId)!.Attempts);
        }
        Assert.AreEqual(1, await new OutboxWorker(store, new RecordingEventPublisher()).PublishPendingAsync());
        Assert.AreEqual(13, store.GetEvent(item.EventId)!.Attempts);
    }

    [TestMethod]
    public async Task old_cancellation_stops_before_and_between_events()
    {
        var store = new OutboxStore();
        var a = store.Enqueue("a", "kind", "body");
        var b = store.Enqueue("b", "kind", "body");
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        try { await new OutboxWorker(store, new RecordingEventPublisher()).PublishPendingAsync(cancellation.Token); Assert.Fail(); }
        catch (OperationCanceledException) { }
        Assert.AreEqual(0, store.GetEvent(a.EventId)!.Attempts);
        using var between = new CancellationTokenSource();
        var worker = new OutboxWorker(store, new Publisher((_, _) => { between.Cancel(); return Task.CompletedTask; }));
        try { await worker.PublishPendingAsync(between.Token); Assert.Fail(); }
        catch (OperationCanceledException) { }
        Assert.AreEqual("Published", store.GetEvent(a.EventId)!.Status);
        Assert.AreEqual(0, store.GetEvent(b.EventId)!.Attempts);
    }

    [TestMethod]
    public async Task old_workers_share_exclusive_event_claims()
    {
        var store = new OutboxStore();
        var item = store.Enqueue("c", "kind", "body");
        var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var count = 0;
        var publisher = new Publisher(async (_, _) => { Interlocked.Increment(ref count); entered.SetResult(true); await release.Task; });
        var first = new OutboxWorker(store, publisher).PublishPendingAsync();
        await entered.Task;
        try
        {
            Assert.AreEqual(0, await new OutboxWorker(store, publisher).PublishPendingAsync());
            Assert.AreEqual("Pending", store.GetEvent(item.EventId)!.Status);
            Assert.AreEqual(1, count);
        }
        finally { release.SetResult(true); }
        Assert.AreEqual(1, await first);
        Assert.AreEqual(1, count);
    }

    [TestMethod]
    public async Task old_publishers_and_stores_remain_independent()
    {
        var store = new OutboxStore();
        store.Enqueue("a", "kind", "body");
        store.Enqueue("b", "kind", "body");
        var calls = new List<string>();
        var worker = new OutboxWorker(store, new Publisher((item, _) => {
            calls.Add(item.CommandId);
            if (item.CommandId == "a")
            {
                store.Enqueue("later", "kind", "body");
                throw new OperationCanceledException("publisher-only cancellation");
            }
            return Task.CompletedTask;
        }));
        Assert.AreEqual(1, await worker.PublishPendingAsync());
        CollectionAssert.AreEqual(new[] { "a", "b" }, calls);
        Assert.AreEqual(2, store.GetPending().Count);
        Assert.AreEqual(0, store.GetPending().Single(item => item.CommandId == "later").Attempts);
        Assert.AreEqual(0, new OutboxStore().GetPending().Count);
        Assert.ThrowsException<ArgumentNullException>(() => new OutboxWorker(null!, new RecordingEventPublisher()));
        Assert.ThrowsException<ArgumentNullException>(() => new OutboxWorker(store, null!));
    }

    [TestMethod]
    public void old_snapshots_cannot_change_store_state()
    {
        var store = new OutboxStore();
        var item = store.Enqueue("a", "kind", "body");
        var snapshot = store.GetPending();
        if (snapshot is OutboxEvent[] array) array[0] = item with { Status = "Published" };
        Assert.AreEqual("Pending", store.GetEvent(item.EventId)!.Status);
        Assert.AreEqual(1, store.GetPending().Count);
        store.Enqueue("b", "kind", "body");
        Assert.AreEqual(1, snapshot.Count);
    }
}

