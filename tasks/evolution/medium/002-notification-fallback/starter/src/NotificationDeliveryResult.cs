namespace Notifications;

public sealed record NotificationDeliveryResult(bool Succeeded, string Channel, string Target, string? Error)
{
    public static NotificationDeliveryResult Success(string channel, string target) => new(true, channel, target, null);
    public static NotificationDeliveryResult Failure(string channel, string target, string error) => new(false, channel, target, error);
}

