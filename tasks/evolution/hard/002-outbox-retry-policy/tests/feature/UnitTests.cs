using Microsoft.VisualStudio.TestTools.UnitTesting;
using Outbox;

[TestClass]
public sealed class FeatureTests
{
    private sealed class Clock : TimeProvider
    {
        public DateTimeOffset Now = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);
        public override DateTimeOffset GetUtcNow() => Now;
        public void Advance(TimeSpan amount) => Now = Now.Add(amount);
    }
    private sealed class Publisher(Func<OutboxEvent, CancellationToken, Task> send) : IEventPublisher
    {
        public Task PublishAsync(OutboxEvent item, CancellationToken cancellationToken) => send(item, cancellationToken);
    }
    private static OutboxEvent Add(OutboxStore store, string id = "c") => store.Enqueue(id, "kind", "body");
    private static IEventPublisher Failing() => new Publisher((_, _) => throw new InvalidOperationException("offline"));

    [TestMethod]
    public async Task retry_delays_double_and_obey_the_cap()
    {
        var store = new OutboxStore(); var item = Add(store); var clock = new Clock();
        var worker = new OutboxWorker(store, Failing(), clock, new RetryPolicy(10, TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(5)));
        foreach (var seconds in new[] { 2, 4, 5, 5 })
        {
            var before = clock.Now;
            Assert.AreEqual(0, await worker.PublishPendingAsync());
            var saved = store.GetEvent(item.EventId)!;
            Assert.AreEqual((DateTimeOffset?)before.AddSeconds(seconds), saved.NextAttemptAt);
            Assert.AreEqual("offline", saved.LastError);
            var attempts = saved.Attempts;
            clock.Advance(TimeSpan.FromSeconds(seconds).Subtract(TimeSpan.FromTicks(1)));
            Assert.AreEqual(0, await worker.PublishPendingAsync());
            Assert.AreEqual(attempts, store.GetEvent(item.EventId)!.Attempts);
            clock.Advance(TimeSpan.FromTicks(1));
        }
    }

    [TestMethod]
    public async Task exhausted_events_move_to_dead_letter()
    {
        var store = new OutboxStore(); var item = Add(store); var clock = new Clock();
        var worker = new OutboxWorker(store, Failing(), clock, new RetryPolicy(2, TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(4)));
        await worker.PublishPendingAsync();
        clock.Advance(TimeSpan.FromSeconds(1));
        await worker.PublishPendingAsync();
        var saved = store.GetEvent(item.EventId)!;
        Assert.AreEqual("DeadLetter", saved.Status);
        Assert.AreEqual(2, saved.Attempts);
        Assert.IsNull(saved.NextAttemptAt);
        Assert.AreEqual("offline", saved.LastError);
        Assert.AreEqual(0, store.GetPending().Count);
        clock.Advance(TimeSpan.FromDays(10));
        Assert.AreEqual(0, await new OutboxWorker(store, new RecordingEventPublisher(), clock).PublishPendingAsync());
        Assert.AreEqual(2, store.GetEvent(item.EventId)!.Attempts);
    }

    [TestMethod]
    public async Task successful_retry_clears_failure_metadata()
    {
        var store = new OutboxStore(); var item = Add(store); var clock = new Clock(); var calls = 0;
        var publisher = new Publisher((_, _) => { if (++calls == 1) throw new Exception("first"); return Task.CompletedTask; });
        var worker = new OutboxWorker(store, publisher, clock, new RetryPolicy(3, TimeSpan.FromSeconds(3), TimeSpan.FromSeconds(10)));
        await worker.PublishPendingAsync();
        Assert.AreEqual(0, await worker.PublishPendingAsync());
        clock.Advance(TimeSpan.FromSeconds(3));
        Assert.AreEqual(1, await worker.PublishPendingAsync());
        var saved = store.GetEvent(item.EventId)!;
        Assert.AreEqual("Published", saved.Status);
        Assert.AreEqual(2, saved.Attempts);
        Assert.IsNull(saved.LastError);
        Assert.IsNull(saved.NextAttemptAt);
        Assert.AreEqual(0, await worker.PublishPendingAsync());
        Assert.AreEqual(2, calls);
    }

    [TestMethod]
    public async Task retry_policy_validation_preserves_default_behavior()
    {
        var store = new OutboxStore(); var item = Add(store); var clock = new Clock();
        foreach (var policy in new[] {
            new RetryPolicy(0, TimeSpan.Zero, TimeSpan.Zero), new RetryPolicy(-1, TimeSpan.Zero, TimeSpan.Zero),
            new RetryPolicy(1, TimeSpan.FromTicks(-1), TimeSpan.Zero),
            new RetryPolicy(1, TimeSpan.Zero, TimeSpan.FromTicks(-1)),
            new RetryPolicy(1, TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(1)) })
            Assert.ThrowsException<ArgumentOutOfRangeException>(() => new OutboxWorker(store, Failing(), clock, policy));
        var worker = new OutboxWorker(store, Failing(), clock);
        for (var i = 0; i < 8; i++) await worker.PublishPendingAsync();
        Assert.AreEqual(8, store.GetEvent(item.EventId)!.Attempts);
        Assert.AreEqual("Pending", store.GetEvent(item.EventId)!.Status);
        Assert.IsNull(store.GetEvent(item.EventId)!.NextAttemptAt);
        var compatible = new OutboxEvent("id", "cmd", "type", "payload", "Pending", 0);
        Assert.IsNull(compatible.NextAttemptAt);
        Assert.IsNull(compatible.LastError);
    }

    [TestMethod]
    public async Task concurrent_workers_respect_leases_and_schedules()
    {
        var store = new OutboxStore(); var item = Add(store); var clock = new Clock();
        var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var calls = 0;
        var publisher = new Publisher(async (_, _) => { Interlocked.Increment(ref calls); entered.SetResult(true); await release.Task; throw new Exception("busy"); });
        var policy = new RetryPolicy(3, TimeSpan.FromMinutes(1), TimeSpan.FromMinutes(2));
        var active = new OutboxWorker(store, publisher, clock, policy).PublishPendingAsync();
        await entered.Task;
        try
        {
            Assert.AreEqual(0, await new OutboxWorker(store, publisher, clock, policy).PublishPendingAsync());
            Assert.AreEqual(1, calls);
            Assert.AreEqual(1, store.GetEvent(item.EventId)!.Attempts);
        }
        finally { release.SetResult(true); }
        Assert.AreEqual(0, await active);
        Assert.AreEqual(0, await new OutboxWorker(store, new RecordingEventPublisher(), clock, policy).PublishPendingAsync());
        Assert.AreEqual(1, store.GetEvent(item.EventId)!.Attempts);
        clock.Advance(TimeSpan.FromMinutes(1));
        Assert.AreEqual(1, await new OutboxWorker(store, new RecordingEventPublisher(), clock, policy).PublishPendingAsync());
    }

    [TestMethod]
    public async Task cancelled_publication_does_not_consume_retry_budget()
    {
        var store = new OutboxStore(); var item = Add(store); var clock = new Clock();
        var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var never = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var policy = new RetryPolicy(1, TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(10));
        using var cancel = new CancellationTokenSource();
        var publisher = new Publisher(async (_, token) => { entered.SetResult(true); await never.Task.WaitAsync(token); });
        var active = new OutboxWorker(store, publisher, clock, policy).PublishPendingAsync(cancel.Token);
        await entered.Task;
        cancel.Cancel();
        try { await active; Assert.Fail(); } catch (OperationCanceledException) { }
        var saved = store.GetEvent(item.EventId)!;
        Assert.AreEqual("Pending", saved.Status);
        Assert.AreEqual(0, saved.Attempts);
        Assert.IsNull(saved.NextAttemptAt);
        Assert.IsNull(saved.LastError);
        Assert.AreEqual(1, await new OutboxWorker(store, new RecordingEventPublisher(), clock, policy).PublishPendingAsync());
    }

    [TestMethod]
    public async Task zero_delay_still_obeys_attempt_limits()
    {
        var store = new OutboxStore(); var item = Add(store); var clock = new Clock(); var calls = 0;
        var publisher = new Publisher((_, _) => { calls++; throw new Exception("zero"); });
        var worker = new OutboxWorker(store, publisher, clock, new RetryPolicy(2, TimeSpan.Zero, TimeSpan.Zero));
        await worker.PublishPendingAsync();
        Assert.AreEqual(1, calls);
        Assert.AreEqual((DateTimeOffset?)clock.Now, store.GetEvent(item.EventId)!.NextAttemptAt);
        await worker.PublishPendingAsync();
        Assert.AreEqual(2, calls);
        Assert.AreEqual("DeadLetter", store.GetEvent(item.EventId)!.Status);
        await worker.PublishPendingAsync();
        Assert.AreEqual(2, calls);
    }

    [TestMethod]
    public async Task retry_time_uses_completion_clock_and_saturates()
    {
        var store = new OutboxStore(); var item = Add(store); var clock = new Clock();
        var publisher = new Publisher((_, _) => { clock.Advance(TimeSpan.FromHours(1)); throw new Exception("slow"); });
        var worker = new OutboxWorker(store, publisher, clock, new RetryPolicy(3, TimeSpan.FromMinutes(10), TimeSpan.FromMinutes(30)));
        await worker.PublishPendingAsync();
        Assert.AreEqual((DateTimeOffset?)clock.Now.AddMinutes(10), store.GetEvent(item.EventId)!.NextAttemptAt);
        var other = new OutboxStore(); var huge = Add(other);
        var saturating = new OutboxWorker(other, Failing(), clock, new RetryPolicy(3, TimeSpan.MaxValue, TimeSpan.MaxValue));
        await saturating.PublishPendingAsync();
        Assert.AreEqual((DateTimeOffset?)DateTimeOffset.MaxValue, other.GetEvent(huge.EventId)!.NextAttemptAt);
        Assert.AreEqual(0, await saturating.PublishPendingAsync());
        clock.Now = DateTimeOffset.MaxValue;
        await saturating.PublishPendingAsync();
        Assert.AreEqual(2, other.GetEvent(huge.EventId)!.Attempts);
    }

    [TestMethod]
    public async Task delayed_events_do_not_block_ready_events()
    {
        var store = new OutboxStore(); var first = Add(store, "first"); var clock = new Clock();
        var calls = new List<string>();
        var publisher = new Publisher((item, _) => {
            calls.Add(item.CommandId);
            if (item.CommandId == "first") throw new Exception("later");
            return Task.CompletedTask;
        });
        var worker = new OutboxWorker(store, publisher, clock, new RetryPolicy(3, TimeSpan.FromHours(1), TimeSpan.FromHours(2)));
        await worker.PublishPendingAsync();
        store.Enqueue("second", "kind", "body");
        store.Enqueue("third", "kind", "body");
        Assert.AreEqual(2, await worker.PublishPendingAsync());
        CollectionAssert.AreEqual(new[] { "first", "second", "third" }, calls);
        Assert.AreEqual(1, store.GetEvent(first.EventId)!.Attempts);
    }
}

