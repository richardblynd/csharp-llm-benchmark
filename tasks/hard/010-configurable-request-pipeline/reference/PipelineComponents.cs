using System.Net;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Filters;
using Microsoft.Extensions.Options;

public sealed class RequestPipelineOptions
{
    public string CorrelationHeaderName { get; set; } = "X-Correlation-ID";
    public Dictionary<string, string> RoutePolicies { get; set; } = new(StringComparer.Ordinal);
}

public sealed class RequestPipelineOptionsValidator : IValidateOptions<RequestPipelineOptions>
{
    public ValidateOptionsResult Validate(string? name, RequestPipelineOptions options)
    {
        if (string.IsNullOrWhiteSpace(options.CorrelationHeaderName))
        {
            return ValidateOptionsResult.Fail("Correlation header name is required.");
        }

        foreach (var policy in options.RoutePolicies)
        {
            if (string.IsNullOrWhiteSpace(policy.Key) || string.IsNullOrWhiteSpace(policy.Value))
            {
                return ValidateOptionsResult.Fail("Route policy names and values are required.");
            }
        }

        return ValidateOptionsResult.Success;
    }
}

public sealed class CorrelationIdMiddleware
{
    private readonly RequestDelegate next;
    private readonly IOptions<RequestPipelineOptions> options;

    public CorrelationIdMiddleware(RequestDelegate next, IOptions<RequestPipelineOptions> options)
    {
        this.next = next;
        this.options = options;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        var header = options.Value.CorrelationHeaderName;
        var correlationId = context.Request.Headers.TryGetValue(header, out var values) && !string.IsNullOrWhiteSpace(values.ToString())
            ? values.ToString()
            : Guid.NewGuid().ToString("N");
        context.Response.Headers[header] = correlationId;
        await next(context);
    }
}

public sealed class DomainExceptionMiddleware
{
    private readonly RequestDelegate next;

    public DomainExceptionMiddleware(RequestDelegate next)
    {
        this.next = next;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await next(context);
        }
        catch (DomainException exception)
        {
            context.Response.StatusCode = exception.StatusCode;
            await context.Response.WriteAsJsonAsync(new ErrorResponse(exception.Code, exception.PublicMessage));
        }
        catch
        {
            context.Response.StatusCode = StatusCodes.Status500InternalServerError;
            await context.Response.WriteAsJsonAsync(new ErrorResponse("internal_error", "An unexpected error occurred."));
        }
    }
}

public sealed class DomainException : Exception
{
    public DomainException(int statusCode, string code, string publicMessage)
        : base(publicMessage)
    {
        StatusCode = statusCode;
        Code = code;
        PublicMessage = publicMessage;
    }

    public int StatusCode { get; }
    public string Code { get; }
    public string PublicMessage { get; }
}

[AttributeUsage(AttributeTargets.Method | AttributeTargets.Class)]
public sealed class RoutePolicyAttribute : Attribute
{
    public RoutePolicyAttribute(string policyName)
    {
        PolicyName = policyName;
    }

    public string PolicyName { get; }
}

public interface IRoutePolicyEvaluator
{
    bool IsAllowed(HttpContext context, string policyName);
}

public sealed class HeaderRoutePolicyEvaluator : IRoutePolicyEvaluator
{
    private readonly IOptions<RequestPipelineOptions> options;

    public HeaderRoutePolicyEvaluator(IOptions<RequestPipelineOptions> options)
    {
        this.options = options;
    }

    public bool IsAllowed(HttpContext context, string policyName)
    {
        if (!options.Value.RoutePolicies.TryGetValue(policyName, out var required))
        {
            return false;
        }

        return context.Request.Headers.TryGetValue("X-Policy", out var actual)
            && string.Equals(actual.ToString(), required, StringComparison.Ordinal);
    }
}

public sealed class RoutePolicyFilter : IAsyncActionFilter
{
    private readonly IRoutePolicyEvaluator evaluator;

    public RoutePolicyFilter(IRoutePolicyEvaluator evaluator)
    {
        this.evaluator = evaluator;
    }

    public async Task OnActionExecutionAsync(ActionExecutingContext context, ActionExecutionDelegate next)
    {
        var attribute = context.ActionDescriptor.EndpointMetadata.OfType<RoutePolicyAttribute>().FirstOrDefault();
        if (attribute is not null && !evaluator.IsAllowed(context.HttpContext, attribute.PolicyName))
        {
            context.Result = new StatusCodeResult(StatusCodes.Status403Forbidden);
            return;
        }

        await next();
    }
}

[ApiController]
public sealed class WidgetsController : ControllerBase
{
    [HttpGet("/widgets/{id}")]
    public WidgetResponse Get(string id)
    {
        if (id == "missing")
        {
            throw new DomainException((int)HttpStatusCode.NotFound, "not_found", "Widget was not found.");
        }

        if (id == "boom")
        {
            throw new InvalidOperationException("boom with internal details");
        }

        return new WidgetResponse(id, $"Widget {id}");
    }

    [HttpGet("/secure")]
    [RoutePolicy("admin")]
    public WidgetResponse Secure()
    {
        return new WidgetResponse("secure", "Secure widget");
    }
}

public sealed record WidgetResponse(string Id, string Name);
public sealed record ErrorResponse(string Code, string Message);
