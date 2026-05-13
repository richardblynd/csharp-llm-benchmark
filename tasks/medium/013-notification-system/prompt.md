Write a small object-oriented notification system.

Required public API:

```csharp
public sealed class NotificationMessage
{
    public NotificationMessage(string recipient, string subject, string body)
    public string Recipient { get; }
    public string Subject { get; }
    public string Body { get; }
}

public interface INotificationChannel
{
    string Name { get; }
    bool IsAvailable { get; }
    NotificationDeliveryResult Send(NotificationMessage message);
}

public sealed class EmailNotificationChannel
public sealed class SmsNotificationChannel
public sealed class PushNotificationChannel

public sealed class NotificationDeliveryResult
{
    public bool Succeeded { get; }
    public string Channel { get; }
    public string Target { get; }
    public string? Error { get; }
    public static NotificationDeliveryResult Success(string channel, string target)
    public static NotificationDeliveryResult Failure(string channel, string target, string error)
}

public sealed class NotificationRouter
{
    public NotificationRouter(IEnumerable<INotificationChannel> channels)
    public IReadOnlyList<NotificationDeliveryResult> Send(NotificationMessage message)
}
```

Rules:
- Do not include a namespace.
- Do not use external libraries.
- All code, public identifiers, exception messages and comments must be written in English.
- `NotificationMessage` must contain recipient, subject and body data.
- `INotificationChannel` must define a common contract used by all channels.
- Email, SMS and push channels must return channel-specific successful delivery results.
- `NotificationRouter` must receive channels through composition, use them polymorphically, and send a message through all available channels.
- The router must work with new custom `INotificationChannel` implementations without changing router code.
- Unavailable channels or channel failures must produce predictable failed delivery results instead of crashing the whole send operation.
