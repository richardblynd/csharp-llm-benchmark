using Microsoft.VisualStudio.TestTools.UnitTesting;
using Notifications;

[TestClass]
public sealed class FeatureTests
{
    private sealed class Channel(string name, Func<NotificationMessage, NotificationDeliveryResult> send, Func<bool>? available = null) : INotificationChannel
    {
        public string Name => name;
        public bool IsAvailable => available?.Invoke() ?? true;
        public NotificationDeliveryResult Send(NotificationMessage message) => send(message);
    }
    private static NotificationMessage Message(string recipient = "user") => new(recipient, "subject", "body");

    [TestMethod]
    public void fallback_stops_after_first_success()
    {
        var visited = new List<string>();
        var success = NotificationDeliveryResult.Success("winner", "user");
        var router = new NotificationRouter(new[] {
            new Channel("a", m => { visited.Add("a"); return NotificationDeliveryResult.Failure("a", m.Recipient, "no"); }),
            new Channel("b", _ => { visited.Add("b"); return success; }),
            new Channel("c", _ => throw new Exception("must not send"), () => throw new Exception("must not inspect")) });
        var result = router.SendWithFallback(Message());
        Assert.IsTrue(result.Succeeded);
        Assert.AreSame(success, result.Delivery);
        Assert.AreEqual(2, result.Attempts.Count);
        CollectionAssert.AreEqual(new[] { "a", "b" }, visited);
        Assert.AreSame(success, result.Attempts[1]);
    }

    [TestMethod]
    public void fallback_records_unavailable_and_throwing_channels()
    {
        var sends = 0;
        var router = new NotificationRouter(new[] {
            new Channel("unavailable", _ => { sends++; throw new Exception(); }, () => false),
            new Channel("availability-error", _ => throw new Exception(), () => throw new Exception("check failed")),
            new Channel("send-error", _ => throw new Exception("send failed")),
            new Channel("no-result", _ => null!),
            new Channel("winner", m => NotificationDeliveryResult.Success("winner", m.Recipient)) });
        var result = router.SendWithFallback(Message());
        Assert.AreEqual(0, sends);
        Assert.IsTrue(result.Succeeded);
        CollectionAssert.AreEqual(new[] { "unavailable", "availability-error", "send-error", "no-result", "winner" },
            result.Attempts.Select(a => a.Channel).ToArray());
        CollectionAssert.AreEqual(new string?[] { "Unavailable", "check failed", "send failed", "No result", null },
            result.Attempts.Select(a => a.Error).ToArray());
        Assert.IsTrue(result.Attempts.All(a => a.Target == "user"));
    }

    [TestMethod]
    public void fallback_handles_empty_and_all_failed_routes()
    {
        var empty = new NotificationRouter(Array.Empty<INotificationChannel>()).SendWithFallback(Message());
        Assert.IsFalse(empty.Succeeded); Assert.IsNull(empty.Delivery); Assert.AreEqual(0, empty.Attempts.Count);
        var result = new NotificationRouter(new[] {
            new Channel("a", m => NotificationDeliveryResult.Failure("a", m.Recipient, "a")),
            new Channel("b", m => NotificationDeliveryResult.Failure("b", m.Recipient, "b")) }).SendWithFallback(Message());
        Assert.IsFalse(result.Succeeded); Assert.IsNull(result.Delivery); Assert.AreEqual(2, result.Attempts.Count);
    }

    [TestMethod]
    public void fallback_preserves_duplicate_channel_names()
    {
        var calls = 0;
        var duplicate = new Channel("same", m => ++calls == 1
            ? NotificationDeliveryResult.Failure("same", m.Recipient, "first")
            : NotificationDeliveryResult.Success("same", m.Recipient));
        var result = new NotificationRouter(new[] { duplicate, duplicate }).SendWithFallback(Message());
        Assert.IsTrue(result.Succeeded); Assert.AreEqual(2, calls); Assert.AreEqual(2, result.Attempts.Count);
        Assert.AreEqual("first", result.Attempts[0].Error);
        Assert.IsTrue(result.Attempts[1].Succeeded);
    }

    [TestMethod]
    public void fallback_returns_immutable_attempt_snapshots()
    {
        var channels = new List<INotificationChannel> { new EmailNotificationChannel() };
        var router = new NotificationRouter(channels);
        channels.Clear();
        var first = router.SendWithFallback(Message("first"));
        if (first.Attempts is IList<NotificationDeliveryResult> list)
            Assert.ThrowsException<NotSupportedException>(() => list[0] = NotificationDeliveryResult.Failure("changed", "changed", "changed"));
        var second = router.SendWithFallback(Message("second"));
        Assert.AreEqual("first", first.Attempts[0].Target);
        Assert.AreEqual("second", second.Attempts[0].Target);
        Assert.AreNotSame(first.Attempts, second.Attempts);
        Assert.ThrowsException<ArgumentNullException>(() => router.SendWithFallback(null!));
    }

    [TestMethod]
    public async Task fallback_keeps_concurrent_calls_independent()
    {
        var router = new NotificationRouter(new[] {
            new Channel("a", m => NotificationDeliveryResult.Failure("a", m.Recipient, "no")),
            new Channel("b", m => NotificationDeliveryResult.Success("b", m.Recipient)) });
        var results = await Task.WhenAll(Enumerable.Range(0, 40).Select(i => Task.Run(() => router.SendWithFallback(Message($"r{i}")))));
        for (var i = 0; i < results.Length; i++)
        {
            Assert.IsTrue(results[i].Succeeded);
            Assert.AreEqual(2, results[i].Attempts.Count);
            Assert.IsTrue(results[i].Attempts.All(attempt => attempt.Target == $"r{i}"));
        }
    }

    [TestMethod]
    public void welcome_service_uses_fallback()
    {
        var messages = new List<NotificationMessage>();
        var first = new Channel("first", m => { messages.Add(m); return NotificationDeliveryResult.Success("first", m.Recipient); });
        var second = new Channel("second", m => { messages.Add(m); return NotificationDeliveryResult.Success("second", m.Recipient); });
        var service = new NotificationService(new NotificationRouter(new[] { first, second }));
        var result = service.SendWelcomeWithFallback(" user ");
        Assert.IsTrue(result.Succeeded);
        Assert.AreEqual(1, messages.Count);
        Assert.AreEqual(new NotificationMessage("user", "Welcome", "Welcome to the service."), messages[0]);
        Assert.AreEqual(1, result.Attempts.Count);
        Assert.ThrowsException<ArgumentException>(() => service.SendWelcomeWithFallback(" "));
        messages.Clear();
        Assert.AreEqual(2, service.SendWelcome("user").Count);
        Assert.AreEqual(2, messages.Count);
    }
}

