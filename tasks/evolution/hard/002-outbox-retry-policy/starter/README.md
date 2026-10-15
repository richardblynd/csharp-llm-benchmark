# Outbox
A working .NET 8 library with an in-memory store and an asynchronous publication worker.
Build: dotnet build Outbox.csproj --configuration Release.

Existing contracts:
- OutboxStore.Enqueue(commandId, type, payload) trims and validates all three strings.
  Blank values throw ArgumentException. Ids are ordinal and case-sensitive.
- A repeated commandId returns its existing event even if the new type/payload differs.
  Every new command creates exactly one event. Event ids are evt-0001, evt-0002, etc.
- New events have Status Pending and Attempts 0. GetEvent returns null for unknown ids.
- GetPending returns pending events in insertion order, as a detached snapshot.
- OutboxWorker(store, publisher, timeProvider = null) accepts a custom publisher.
  PublishPendingAsync returns the number successfully published in that call.
- Each pending event can be attempted at most once per call. Each attempt increments Attempts.
  The worker processes only its pending snapshot at call entry; later enqueues wait for another call.
  A failure stays Pending and is immediately eligible for the next call, without a retry limit.
  A success becomes Published and cannot be attempted again.
- Workers sharing one store claim events exclusively, including while awaiting the publisher.
  Other workers skip claimed events; they do not block or publish them twice.
- Cancellation is checked at entry and before each event. Caller cancellation during
  publication propagates, releases the claim and restores the attempt count.
  An OperationCanceledException without caller cancellation is an ordinary failure.
- Publisher failures do not stop later events. RecordingEventPublisher records deliveries.
- Returned records are immutable; changing a returned list cannot change store state.
  Store instances have separate state and publication callbacks run outside the store lock.

