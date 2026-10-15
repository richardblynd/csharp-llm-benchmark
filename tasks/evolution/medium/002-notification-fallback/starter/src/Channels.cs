namespace Notifications;

public abstract class NotificationChannel(string name, bool isAvailable) : INotificationChannel
{
    public string Name { get; } = name;
    public bool IsAvailable { get; } = isAvailable;
    public NotificationDeliveryResult Send(NotificationMessage message)
    {
        ArgumentNullException.ThrowIfNull(message);
        return NotificationDeliveryResult.Success(Name, message.Recipient);
    }
}
public sealed class EmailNotificationChannel(bool isAvailable = true) : NotificationChannel("email", isAvailable);
public sealed class SmsNotificationChannel(bool isAvailable = true) : NotificationChannel("sms", isAvailable);
public sealed class PushNotificationChannel(bool isAvailable = true) : NotificationChannel("push", isAvailable);

