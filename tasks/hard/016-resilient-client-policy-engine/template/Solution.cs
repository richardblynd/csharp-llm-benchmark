using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

public delegate Task<HttpResponseMessage> HttpSendDelegate(HttpRequestMessage request, CancellationToken cancellationToken);

public interface IHttpClientPolicy
{
    Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, HttpSendDelegate next, CancellationToken cancellationToken);
}

public sealed class BrokenCircuitException : Exception
{
    public BrokenCircuitException(string message) : base(message) { }
}

public sealed class ResilientHttpClient
{
    public ResilientHttpClient(HttpMessageHandler handler, IEnumerable<IHttpClientPolicy> policies) => throw new NotImplementedException();
    public Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken = default) => throw new NotImplementedException();
}

public sealed class RetryPolicy : IHttpClientPolicy
{
    public RetryPolicy(int maxRetries, params HttpStatusCode[] retryStatusCodes) => throw new NotImplementedException();
    public Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, HttpSendDelegate next, CancellationToken cancellationToken) => throw new NotImplementedException();
}

public sealed class CircuitBreakerPolicy : IHttpClientPolicy
{
    public CircuitBreakerPolicy(int failureThreshold, TimeSpan breakDuration, TimeProvider? timeProvider = null) => throw new NotImplementedException();
    public Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, HttpSendDelegate next, CancellationToken cancellationToken) => throw new NotImplementedException();
}

public sealed class BulkheadPolicy : IHttpClientPolicy
{
    public BulkheadPolicy(int maxConcurrency) => throw new NotImplementedException();
    public Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, HttpSendDelegate next, CancellationToken cancellationToken) => throw new NotImplementedException();
}

public sealed class TimeoutPolicy : IHttpClientPolicy
{
    public TimeoutPolicy(TimeSpan timeout) => throw new NotImplementedException();
    public Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, HttpSendDelegate next, CancellationToken cancellationToken) => throw new NotImplementedException();
}
