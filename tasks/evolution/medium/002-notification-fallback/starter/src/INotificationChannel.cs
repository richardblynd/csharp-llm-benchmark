namespace Notifications;

public interface INotificationChannel
{
    string Name { get; }
    bool IsAvailable { get; }
    NotificationDeliveryResult Send(NotificationMessage message);
}

