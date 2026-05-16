Write a resilient client policy engine for simulated HTTP calls.

Required public API:

```csharp
public delegate Task<HttpResponseMessage> HttpSendDelegate(HttpRequestMessage request, CancellationToken cancellationToken);

public interface IHttpClientPolicy
{
    Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, HttpSendDelegate next, CancellationToken cancellationToken);
}

public sealed class BrokenCircuitException : Exception { }

public sealed class ResilientHttpClient
{
    public ResilientHttpClient(HttpMessageHandler handler, IEnumerable<IHttpClientPolicy> policies)
    public Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken = default)
}

public sealed class RetryPolicy : IHttpClientPolicy
{
    public RetryPolicy(int maxRetries, params HttpStatusCode[] retryStatusCodes)
}

public sealed class CircuitBreakerPolicy : IHttpClientPolicy
{
    public CircuitBreakerPolicy(int failureThreshold, TimeSpan breakDuration, TimeProvider? timeProvider = null)
}

public sealed class BulkheadPolicy : IHttpClientPolicy
{
    public BulkheadPolicy(int maxConcurrency)
}

public sealed class TimeoutPolicy : IHttpClientPolicy
{
    public TimeoutPolicy(TimeSpan timeout)
}
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- The implementation must not make real network calls; it sends only through the supplied `HttpMessageHandler`.
- Policies compose in the order provided to `ResilientHttpClient`; the first policy is the outermost policy.
- `RetryPolicy` retries only for configured HTTP status codes and `HttpRequestException`, up to `maxRetries` additional attempts.
- Retry attempts must use a fresh `HttpRequestMessage` clone for each attempt. Supporting request bodies is not required.
- `CircuitBreakerPolicy` opens after `failureThreshold` failed calls. HTTP 5xx responses and exceptions count as failures.
- While open, the circuit throws `BrokenCircuitException` without calling the next delegate.
- After `breakDuration` has elapsed according to the injected clock, the circuit allows a trial call and closes on success.
- `BulkheadPolicy` limits concurrent calls with a semaphore and respects cancellation while waiting.
- `TimeoutPolicy` cancels the inner call after the configured timeout and throws `TimeoutException` for policy timeouts, while preserving external cancellation.
