Extend the existing outbox worker with configurable retry backoff and dead letters.
Preserve the existing enqueue, snapshot, publication, ordering, concurrency and cancellation contracts.

Add public record RetryPolicy(int MaxAttempts, TimeSpan InitialDelay, TimeSpan MaxDelay).
Extend the existing worker constructor with an optional FOURTH parameter
RetryPolicy? retryPolicy = null; keep its first three parameters compatible.
Add optional properties NextAttemptAt (DateTimeOffset?) and LastError (string?) to
OutboxEvent, preserving compatibility with its existing six constructor arguments.

When a policy is supplied:
- MaxAttempts must be positive; InitialDelay must be nonnegative; MaxDelay must
  be nonnegative and at least InitialDelay. Reject invalid policies with ArgumentOutOfRangeException.
- After failed attempt k (counted from 1), schedule the next attempt after
  min(MaxDelay, InitialDelay * 2^(k-1)). Use the injected TimeProvider, measured at
  FAILURE COMPLETION. Avoid arithmetic overflow; cap a due date past the representable
  range at DateTimeOffset.MaxValue.
- A pending event may be claimed when NextAttemptAt is null or now >= NextAttemptAt.
  Until then it remains Pending, without increasing Attempts or calling the publisher.
- Zero delay permits retry on a subsequent call, still at most once per call.
- A failure that reaches MaxAttempts changes Status to DeadLetter. Keep the event
  retrievable, set LastError to the exception message, clear NextAttemptAt, and never
  automatically publish it again. GetPending excludes dead letters.
- Before that limit, failures keep Status Pending, record LastError and the due date.
- A successful retry changes Status to Published, clears NextAttemptAt and LastError,
  and preserves the number of completed attempts.
- Caller cancellation must propagate and release the claim without consuming a retry
  attempt, scheduling a delay or dead-lettering the event.
- Claims, attempt counts and state transitions must stay safe across concurrent
  workers sharing a store. A delayed or claimed event must not block other ready events.
- A worker sees only the pending snapshot taken at call entry. Events enqueued later
  can be published on a later call.
- With no policy, preserve the previous unlimited, immediate retries and all old behavior.
  Both new metadata properties are initially null.

Use the current store and publisher interface. Do not add dependencies, real delays,
background loops, network services or hidden-test hooks. Write English identifiers and messages.

