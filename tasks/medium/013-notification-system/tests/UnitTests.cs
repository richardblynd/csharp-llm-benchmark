using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    private sealed class CustomChannel : global::INotificationChannel
    {
        public string Name => "custom";
        public bool IsAvailable => true;
        public global::NotificationDeliveryResult Send(global::NotificationMessage message) => global::NotificationDeliveryResult.Success(Name, message.Recipient);
    }

    private sealed class FailingChannel : global::INotificationChannel
    {
        public string Name => "failing";
        public bool IsAvailable => true;
        public global::NotificationDeliveryResult Send(global::NotificationMessage message) => throw new InvalidOperationException("failed");
    }

    [TestMethod]
    public void defines_common_notification_channel_contract()
    {
        Assert.IsTrue(typeof(global::INotificationChannel).IsInterface);
        Assert.IsTrue(typeof(global::EmailNotificationChannel).GetInterfaces().Contains(typeof(global::INotificationChannel)));
        Assert.IsTrue(typeof(global::SmsNotificationChannel).GetInterfaces().Contains(typeof(global::INotificationChannel)));
        Assert.IsTrue(typeof(global::PushNotificationChannel).GetInterfaces().Contains(typeof(global::INotificationChannel)));
    }

    [TestMethod]
    public void implements_specific_channel_behaviors()
    {
        var message = new global::NotificationMessage("user@example.com", "Subject", "Body");

        Assert.AreEqual("email", new global::EmailNotificationChannel().Send(message).Channel);
        Assert.AreEqual("sms", new global::SmsNotificationChannel().Send(message).Channel);
        Assert.AreEqual("push", new global::PushNotificationChannel().Send(message).Channel);
    }

    [TestMethod]
    public void uses_polymorphism_with_custom_channel()
    {
        var router = new global::NotificationRouter(new global::INotificationChannel[] { new CustomChannel() });

        var results = router.Send(new global::NotificationMessage("target", "Subject", "Body"));

        Assert.AreEqual("custom", results.Single().Channel);
    }

    [TestMethod]
    public void uses_composition_to_orchestrate_channels()
    {
        var router = new global::NotificationRouter(new global::INotificationChannel[]
        {
            new global::EmailNotificationChannel(),
            new global::SmsNotificationChannel()
        });

        var results = router.Send(new global::NotificationMessage("target", "Subject", "Body"));

        CollectionAssert.AreEqual(new[] { "email", "sms" }, results.Select(r => r.Channel).ToArray());
    }

    [TestMethod]
    public void handles_unavailable_or_failed_channels_predictably()
    {
        var router = new global::NotificationRouter(new global::INotificationChannel[] { new FailingChannel() });

        var result = router.Send(new global::NotificationMessage("target", "Subject", "Body")).Single();

        Assert.IsFalse(result.Succeeded);
        Assert.AreEqual("failing", result.Channel);
    }
}
