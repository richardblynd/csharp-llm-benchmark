namespace Notifications;

public sealed partial class NotificationService
{
    public FallbackDelivery SendWelcomeWithFallback(string recipient) => router.SendWithFallback(Welcome(recipient));
}

