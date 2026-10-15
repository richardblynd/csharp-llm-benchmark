using Microsoft.VisualStudio.TestTools.UnitTesting;
using Notifications;

[TestClass]
public sealed class RegressionTests
{
    private sealed class Channel(string name, Func<NotificationMessage, NotificationDeliveryResult> send, bool available = true) : INotificationChannel
    {
        public string Name => name;
        public bool IsAvailable => available;
        public NotificationDeliveryResult Send(NotificationMessage message) => send(message);
    }
    private static NotificationMessage Message() => new("user", "subject", "body");

    [TestMethod]
    public void old_send_uses_every_channel_in_order()
    {
        var router = new NotificationRouter(new INotificationChannel[] { new EmailNotificationChannel(), new SmsNotificationChannel(), new PushNotificationChannel() });
        var results = router.Send(Message());
        CollectionAssert.AreEqual(new[] { "email", "sms", "push" }, results.Select(result => result.Channel).ToArray());
        Assert.IsTrue(results.All(result => result.Succeeded && result.Target == "user" && result.Error is null));
    }

    [TestMethod]
    public void old_send_reports_unavailable_channels()
    {
        var calls = 0;
        var router = new NotificationRouter(new INotificationChannel[] {
            new Channel("offline", _ => { calls++; throw new Exception(); }, false), new EmailNotificationChannel() });
        var results = router.Send(Message());
        Assert.AreEqual(0, calls);
        Assert.AreEqual(2, results.Count);
        Assert.AreEqual(NotificationDeliveryResult.Failure("offline", "user", "Unavailable"), results[0]);
        Assert.IsTrue(results[1].Succeeded);
    }

    [TestMethod]
    public void old_send_contains_channel_exceptions()
    {
        var router = new NotificationRouter(new INotificationChannel[] {
            new Channel("broken", _ => throw new InvalidOperationException("failed")), new SmsNotificationChannel() });
        var results = router.Send(Message());
        Assert.AreEqual(NotificationDeliveryResult.Failure("broken", "user", "failed"), results[0]);
        Assert.IsTrue(results[1].Succeeded);
    }

    [TestMethod]
    public void old_send_supports_custom_results_and_duplicates()
    {
        var expected = NotificationDeliveryResult.Success("custom-result", "custom-target");
        var calls = 0;
        var custom = new Channel("custom", _ => { calls++; return expected; });
        var results = new NotificationRouter(new[] { custom, custom }).Send(Message());
        Assert.AreEqual(2, calls);
        Assert.AreSame(expected, results[0]);
        Assert.AreSame(expected, results[1]);
    }

    [TestMethod]
    public void old_router_snapshots_and_validates_channels()
    {
        var channels = new List<INotificationChannel> { new EmailNotificationChannel() };
        var router = new NotificationRouter(channels);
        channels.Clear();
        Assert.AreEqual(1, router.Send(Message()).Count);
        Assert.AreEqual(0, new NotificationRouter(Array.Empty<INotificationChannel>()).Send(Message()).Count);
        Assert.ThrowsException<ArgumentNullException>(() => new NotificationRouter(null!));
        Assert.ThrowsException<ArgumentException>(() => new NotificationRouter(new INotificationChannel[] { null! }));
    }

    [TestMethod]
    public void old_welcome_service_keeps_its_message_and_fanout()
    {
        var messages = new List<NotificationMessage>();
        var channel = new Channel("custom", message => { messages.Add(message); return NotificationDeliveryResult.Success("custom", message.Recipient); });
        var service = new NotificationService(new NotificationRouter(new[] { channel, channel }));
        Assert.AreEqual(2, service.SendWelcome(" user ").Count);
        Assert.AreEqual(2, messages.Count);
        Assert.IsTrue(messages.All(message => message == new NotificationMessage("user", "Welcome", "Welcome to the service.")));
    }

    [TestMethod]
    public void old_messages_and_null_validation_are_preserved()
    {
        var message = new NotificationMessage(" recipient ", " subject ", " body ");
        Assert.AreEqual(" recipient ", message.Recipient);
        Assert.AreEqual(" subject ", message.Subject);
        Assert.AreEqual(" body ", message.Body);
        var router = new NotificationRouter(new[] { new EmailNotificationChannel() });
        Assert.ThrowsException<ArgumentNullException>(() => router.Send(null!));
        Assert.ThrowsException<ArgumentNullException>(() => new EmailNotificationChannel().Send(null!));
        Assert.ThrowsException<ArgumentNullException>(() => new NotificationService(null!));
        Assert.ThrowsException<ArgumentException>(() => new NotificationService(router).SendWelcome(" "));
    }
}

