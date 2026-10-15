namespace Notifications;

public sealed partial class NotificationService
{
    private readonly NotificationRouter router;
    public NotificationService(NotificationRouter router)
    {
        this.router = router ?? throw new ArgumentNullException(nameof(router));
    }

    public IReadOnlyList<NotificationDeliveryResult> SendWelcome(string recipient) => router.Send(Welcome(recipient));

    private static NotificationMessage Welcome(string recipient)
    {
        if (string.IsNullOrWhiteSpace(recipient)) throw new ArgumentException("Recipient must not be blank.");
        return new NotificationMessage(recipient.Trim(), "Welcome", "Welcome to the service.");
    }
}

