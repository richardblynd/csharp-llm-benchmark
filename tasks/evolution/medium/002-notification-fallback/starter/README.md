# Notifications
Working .NET 8 library. Build: dotnet build Notifications.csproj --configuration Release.

NotificationMessage(Recipient, Subject, Body) and NotificationDeliveryResult(Succeeded,
Channel, Target, Error) are immutable records. Result factories Success and Failure are public.
INotificationChannel exposes Name, IsAvailable and Send(message). Channels may be supplied
by callers; their Name is stable. Email, Sms and Push channels report email, sms and push.

NotificationRouter snapshots the constructor's channel enumeration in order, preserving
duplicates. A null collection throws ArgumentNullException; null entries throw ArgumentException.
Send(message) rejects null and sends through EVERY available channel. Results stay in input
order. An unavailable channel produces Failure(Name, Recipient, "Unavailable") without calling
Send. Exceptions from IsAvailable or Send produce Failure(Name, Recipient, exception.Message).
A null channel result becomes Failure(Name, Recipient, "No result"). Custom non-null delivery
results are returned unchanged. Failure in one channel never prevents later channels.
Each call returns a detached result snapshot; callers cannot change the router by changing
the original channel list or a result list. New custom channels need no router modifications.

NotificationService.SendWelcome(recipient) validates and trims the recipient, creates a
message with Subject Welcome and Body Welcome to the service., and uses the router's normal
fanout. Blank recipients throw ArgumentException; a null router throws ArgumentNullException.

