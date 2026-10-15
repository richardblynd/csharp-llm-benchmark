Add ordered fallback delivery to the existing notification router and welcome service.
Keep Send and SendWelcome delivering through every channel exactly as before.

Add public record FallbackDelivery with these readable properties:
bool Succeeded, NotificationDeliveryResult? Delivery,
IReadOnlyList<NotificationDeliveryResult> Attempts.
Add FallbackDelivery NotificationRouter.SendWithFallback(NotificationMessage message)
and FallbackDelivery NotificationService.SendWelcomeWithFallback(string recipient).

Rules:
- Try channels in their existing constructor order. Return immediately after the first
  successful delivery; do not probe availability or call later channels.
- Record every visited channel's result in Attempts, including unavailable channels and
  exceptions from availability or Send. Use the existing predictable failure conversions.
- Preserve duplicate channel names, duplicate instances and custom result objects.
  Do not choose channels by their concrete type or name.
- On success, Succeeded is true and Delivery is that channel's result.
  If every visited channel fails (or there are no channels), Succeeded is false and Delivery is null.
- Attempts is an immutable snapshot, in visitation order. Callers must not be able to
  replace its elements. Separate and concurrent fallback calls must have separate snapshots.
- Reject null messages with ArgumentNullException.
- The welcome fallback entry point must construct exactly the existing welcome message,
  apply the existing recipient validation, and use the router's fallback behavior.
  The legacy welcome entry point keeps its old fanout.
- Keep existing composition and namespaces. No extra dependencies, I/O, static shared
  delivery history or implementation-specific test hooks. Write English identifiers and messages.

