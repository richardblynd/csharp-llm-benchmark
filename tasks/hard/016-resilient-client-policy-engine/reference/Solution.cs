using System;
using System.Collections.Generic;
using System.Linq;
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
    private readonly HttpMessageInvoker invoker;
    private readonly IReadOnlyList<IHttpClientPolicy> policies;

    public ResilientHttpClient(HttpMessageHandler handler, IEnumerable<IHttpClientPolicy> policies)
    {
        ArgumentNullException.ThrowIfNull(handler);
        ArgumentNullException.ThrowIfNull(policies);
        invoker = new HttpMessageInvoker(handler, disposeHandler: false);
        this.policies = policies.ToArray();
    }

    public Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        HttpSendDelegate pipeline = (message, token) => invoker.SendAsync(message, token);
        for (var index = policies.Count - 1; index >= 0; index--)
        {
            var policy = policies[index];
            var next = pipeline;
            pipeline = (message, token) => policy.SendAsync(message, next, token);
        }

        return pipeline(request, cancellationToken);
    }
}

public sealed class RetryPolicy : IHttpClientPolicy
{
    private readonly int maxRetries;
    private readonly HashSet<HttpStatusCode> retryStatusCodes;

    public RetryPolicy(int maxRetries, params HttpStatusCode[] retryStatusCodes)
    {
        if (maxRetries < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxRetries));
        }

        this.maxRetries = maxRetries;
        this.retryStatusCodes = retryStatusCodes.ToHashSet();
    }

    public async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, HttpSendDelegate next, CancellationToken cancellationToken)
    {
        for (var attempt = 0; ; attempt++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            try
            {
                var response = await next(CloneRequest(request), cancellationToken);
                if (!retryStatusCodes.Contains(response.StatusCode) || attempt >= maxRetries)
                {
                    return response;
                }

                response.Dispose();
            }
            catch (HttpRequestException) when (attempt < maxRetries)
            {
            }
        }
    }

    private static HttpRequestMessage CloneRequest(HttpRequestMessage request)
    {
        if (request.Content is not null)
        {
            throw new NotSupportedException("Retrying requests with content is not supported.");
        }

        var clone = new HttpRequestMessage(request.Method, request.RequestUri)
        {
            Version = request.Version,
            VersionPolicy = request.VersionPolicy
        };
        foreach (var header in request.Headers)
        {
            clone.Headers.TryAddWithoutValidation(header.Key, header.Value);
        }

        return clone;
    }
}

public sealed class CircuitBreakerPolicy : IHttpClientPolicy
{
    private readonly object gate = new();
    private readonly int failureThreshold;
    private readonly TimeSpan breakDuration;
    private readonly TimeProvider timeProvider;
    private int failures;
    private DateTimeOffset? openUntil;

    public CircuitBreakerPolicy(int failureThreshold, TimeSpan breakDuration, TimeProvider? timeProvider = null)
    {
        if (failureThreshold <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(failureThreshold));
        }

        if (breakDuration <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(breakDuration));
        }

        this.failureThreshold = failureThreshold;
        this.breakDuration = breakDuration;
        this.timeProvider = timeProvider ?? TimeProvider.System;
    }

    public async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, HttpSendDelegate next, CancellationToken cancellationToken)
    {
        var now = timeProvider.GetUtcNow();
        lock (gate)
        {
            if (openUntil is not null && now < openUntil.Value)
            {
                throw new BrokenCircuitException("The circuit is open.");
            }
        }

        try
        {
            var response = await next(request, cancellationToken);
            if ((int)response.StatusCode >= 500)
            {
                RecordFailure();
            }
            else
            {
                RecordSuccess();
            }

            return response;
        }
        catch
        {
            RecordFailure();
            throw;
        }
    }

    private void RecordFailure()
    {
        lock (gate)
        {
            failures++;
            if (failures >= failureThreshold)
            {
                openUntil = timeProvider.GetUtcNow().Add(breakDuration);
            }
        }
    }

    private void RecordSuccess()
    {
        lock (gate)
        {
            failures = 0;
            openUntil = null;
        }
    }
}

public sealed class BulkheadPolicy : IHttpClientPolicy
{
    private readonly SemaphoreSlim semaphore;

    public BulkheadPolicy(int maxConcurrency)
    {
        if (maxConcurrency <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxConcurrency));
        }

        semaphore = new SemaphoreSlim(maxConcurrency, maxConcurrency);
    }

    public async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, HttpSendDelegate next, CancellationToken cancellationToken)
    {
        await semaphore.WaitAsync(cancellationToken);
        try
        {
            return await next(request, cancellationToken);
        }
        finally
        {
            semaphore.Release();
        }
    }
}

public sealed class TimeoutPolicy : IHttpClientPolicy
{
    private readonly TimeSpan timeout;

    public TimeoutPolicy(TimeSpan timeout)
    {
        if (timeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(timeout));
        }

        this.timeout = timeout;
    }

    public async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, HttpSendDelegate next, CancellationToken cancellationToken)
    {
        using var timeoutSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutSource.CancelAfter(timeout);
        try
        {
            return await next(request, timeoutSource.Token);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new TimeoutException("The HTTP call exceeded the configured timeout.");
        }
    }
}
