namespace Notifications;

public sealed partial class NotificationRouter
{
    public FallbackDelivery SendWithFallback(NotificationMessage message)
    {
        ArgumentNullException.ThrowIfNull(message);
        var attempts = new List<NotificationDeliveryResult>();
        foreach (var channel in channels)
        {
            var attempt = Deliver(channel, message);
            attempts.Add(attempt);
            if (attempt.Succeeded) return new FallbackDelivery(true, attempt, attempts.AsReadOnly());
        }
        return new FallbackDelivery(false, null, attempts.AsReadOnly());
    }
}

