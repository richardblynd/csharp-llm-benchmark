namespace Notifications;

public sealed record FallbackDelivery(bool Succeeded, NotificationDeliveryResult? Delivery, IReadOnlyList<NotificationDeliveryResult> Attempts);

