namespace Notifications;

public sealed partial class NotificationRouter
{
    private readonly INotificationChannel[] channels;
    public NotificationRouter(IEnumerable<INotificationChannel> channels)
    {
        ArgumentNullException.ThrowIfNull(channels);
        this.channels = channels.ToArray();
        if (this.channels.Any(channel => channel is null)) throw new ArgumentException("Channels must not contain null.");
    }

    public IReadOnlyList<NotificationDeliveryResult> Send(NotificationMessage message)
    {
        ArgumentNullException.ThrowIfNull(message);
        return channels.Select(channel => Deliver(channel, message)).ToArray();
    }

    private static NotificationDeliveryResult Deliver(INotificationChannel channel, NotificationMessage message)
    {
        try
        {
            if (!channel.IsAvailable) return NotificationDeliveryResult.Failure(channel.Name, message.Recipient, "Unavailable");
            return channel.Send(message) ?? NotificationDeliveryResult.Failure(channel.Name, message.Recipient, "No result");
        }
        catch (Exception error)
        {
            return NotificationDeliveryResult.Failure(channel.Name, message.Recipient, error.Message);
        }
    }
}

