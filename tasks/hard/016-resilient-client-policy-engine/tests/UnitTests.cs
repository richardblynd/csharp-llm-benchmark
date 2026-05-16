using System.Net;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public async Task applies_retry_only_for_configured_failures()
    {
        var retryingHandler = new SequenceHandler(
            _ => new HttpResponseMessage(HttpStatusCode.InternalServerError),
            _ => new HttpResponseMessage(HttpStatusCode.OK));
        var retryingClient = new global::ResilientHttpClient(retryingHandler, new[] { new global::RetryPolicy(2, HttpStatusCode.InternalServerError) });

        var retryingResponse = await retryingClient.SendAsync(new HttpRequestMessage(HttpMethod.Get, "https://example.test/retry"));

        Assert.AreEqual(HttpStatusCode.OK, retryingResponse.StatusCode);
        Assert.AreEqual(2, retryingHandler.Calls);

        var nonRetryingHandler = new SequenceHandler(
            _ => new HttpResponseMessage(HttpStatusCode.BadRequest),
            _ => new HttpResponseMessage(HttpStatusCode.OK));
        var nonRetryingClient = new global::ResilientHttpClient(nonRetryingHandler, new[] { new global::RetryPolicy(2, HttpStatusCode.InternalServerError) });

        var nonRetryingResponse = await nonRetryingClient.SendAsync(new HttpRequestMessage(HttpMethod.Get, "https://example.test/no-retry"));

        Assert.AreEqual(HttpStatusCode.BadRequest, nonRetryingResponse.StatusCode);
        Assert.AreEqual(1, nonRetryingHandler.Calls);
    }

    [TestMethod]
    public async Task opens_and_closes_circuit_breaker_with_injected_clock()
    {
        var clock = new ManualTimeProvider(DateTimeOffset.Parse("2026-01-01T00:00:00Z"));
        var calls = 0;
        var handler = new CallbackHandler(_ =>
        {
            calls++;
            return Task.FromResult(new HttpResponseMessage(calls <= 2 ? HttpStatusCode.InternalServerError : HttpStatusCode.OK));
        });
        var client = new global::ResilientHttpClient(handler, new[] { new global::CircuitBreakerPolicy(2, TimeSpan.FromMinutes(1), clock) });

        await client.SendAsync(new HttpRequestMessage(HttpMethod.Get, "https://example.test/one"));
        await client.SendAsync(new HttpRequestMessage(HttpMethod.Get, "https://example.test/two"));
        await Assert.ThrowsExceptionAsync<global::BrokenCircuitException>(() => client.SendAsync(new HttpRequestMessage(HttpMethod.Get, "https://example.test/open")));
        Assert.AreEqual(2, calls);

        clock.Advance(TimeSpan.FromMinutes(1));
        var response = await client.SendAsync(new HttpRequestMessage(HttpMethod.Get, "https://example.test/half-open"));

        Assert.AreEqual(HttpStatusCode.OK, response.StatusCode);
        Assert.AreEqual(3, calls);
    }

    [TestMethod]
    public async Task limits_concurrency_with_bulkhead()
    {
        var active = 0;
        var maxActive = 0;
        var enteredTwice = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var handler = new CallbackHandler(async cancellationToken =>
        {
            var current = Interlocked.Increment(ref active);
            maxActive = Math.Max(maxActive, current);
            if (current == 2)
            {
                enteredTwice.TrySetResult();
            }

            await release.Task.WaitAsync(cancellationToken);
            Interlocked.Decrement(ref active);
            return new HttpResponseMessage(HttpStatusCode.OK);
        });
        var client = new global::ResilientHttpClient(handler, new[] { new global::BulkheadPolicy(2) });

        var sends = Enumerable.Range(0, 5)
            .Select(index => client.SendAsync(new HttpRequestMessage(HttpMethod.Get, $"https://example.test/{index}")))
            .ToArray();

        await enteredTwice.Task.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.IsTrue(maxActive <= 2);
        release.SetResult();
        await Task.WhenAll(sends);
        Assert.IsTrue(maxActive <= 2);
    }

    [TestMethod]
    public async Task respects_timeout_and_cancellation()
    {
        var slowHandler = new CallbackHandler(async cancellationToken =>
        {
            await Task.Delay(TimeSpan.FromMinutes(1), cancellationToken);
            return new HttpResponseMessage(HttpStatusCode.OK);
        });
        var timeoutClient = new global::ResilientHttpClient(slowHandler, new[] { new global::TimeoutPolicy(TimeSpan.FromMilliseconds(25)) });

        await Assert.ThrowsExceptionAsync<TimeoutException>(() => timeoutClient.SendAsync(new HttpRequestMessage(HttpMethod.Get, "https://example.test/timeout")));

        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        try
        {
            await timeoutClient.SendAsync(new HttpRequestMessage(HttpMethod.Get, "https://example.test/cancel"), cancellation.Token);
            Assert.Fail("External cancellation should be preserved.");
        }
        catch (OperationCanceledException)
        {
        }
    }

    [TestMethod]
    public async Task composes_policies_in_deterministic_order()
    {
        var events = new List<string>();
        var handler = new SequenceHandler(_ => new HttpResponseMessage(HttpStatusCode.OK));
        var client = new global::ResilientHttpClient(handler, new global::IHttpClientPolicy[]
        {
            new RecordingPolicy("outer", events),
            new RecordingPolicy("inner", events)
        });

        await client.SendAsync(new HttpRequestMessage(HttpMethod.Get, "https://example.test/order"));

        CollectionAssert.AreEqual(new[] { "outer-before", "inner-before", "inner-after", "outer-after" }, events);
    }

    [TestMethod]
    public async Task uses_fake_handler_without_network()
    {
        var handler = new SequenceHandler(_ => new HttpResponseMessage(HttpStatusCode.Accepted));
        var client = new global::ResilientHttpClient(handler, Array.Empty<global::IHttpClientPolicy>());

        var response = await client.SendAsync(new HttpRequestMessage(HttpMethod.Get, "https://not-used.invalid/resource"));

        Assert.AreEqual(HttpStatusCode.Accepted, response.StatusCode);
        Assert.AreEqual(1, handler.Calls);
    }

    private sealed class SequenceHandler : HttpMessageHandler
    {
        private readonly Queue<Func<CancellationToken, HttpResponseMessage>> responses;

        public SequenceHandler(params Func<CancellationToken, HttpResponseMessage>[] responses)
        {
            this.responses = new Queue<Func<CancellationToken, HttpResponseMessage>>(responses);
        }

        public int Calls { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Calls++;
            var response = responses.Count == 0 ? new HttpResponseMessage(HttpStatusCode.OK) : responses.Dequeue().Invoke(cancellationToken);
            return Task.FromResult(response);
        }
    }

    private sealed class CallbackHandler : HttpMessageHandler
    {
        private readonly Func<CancellationToken, Task<HttpResponseMessage>> callback;

        public CallbackHandler(Func<CancellationToken, Task<HttpResponseMessage>> callback)
        {
            this.callback = callback;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            return callback(cancellationToken);
        }
    }

    private sealed class RecordingPolicy : global::IHttpClientPolicy
    {
        private readonly string name;
        private readonly List<string> events;

        public RecordingPolicy(string name, List<string> events)
        {
            this.name = name;
            this.events = events;
        }

        public async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, global::HttpSendDelegate next, CancellationToken cancellationToken)
        {
            events.Add($"{name}-before");
            var response = await next(request, cancellationToken);
            events.Add($"{name}-after");
            return response;
        }
    }

    private sealed class ManualTimeProvider : TimeProvider
    {
        private DateTimeOffset now;

        public ManualTimeProvider(DateTimeOffset now)
        {
            this.now = now;
        }

        public override DateTimeOffset GetUtcNow() => now;

        public void Advance(TimeSpan duration)
        {
            now = now.Add(duration);
        }
    }
}
