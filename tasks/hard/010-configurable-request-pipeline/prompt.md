Write configurable ASP.NET Core request pipeline components for a small API.

The generated file must provide these public types because `Program.cs` wires them through dependency injection:

```csharp
public sealed class RequestPipelineOptions
{
    public string CorrelationHeaderName { get; set; }
    public Dictionary<string, string> RoutePolicies { get; set; }
}

public sealed class RequestPipelineOptionsValidator : IValidateOptions<RequestPipelineOptions> { }
public sealed class CorrelationIdMiddleware { }
public sealed class DomainExceptionMiddleware { }
public sealed class DomainException : Exception { }
public sealed class RoutePolicyAttribute : Attribute { }
public interface IRoutePolicyEvaluator { }
public sealed class HeaderRoutePolicyEvaluator : IRoutePolicyEvaluator { }
public sealed class RoutePolicyFilter : IAsyncActionFilter { }
```

Required HTTP endpoints:
- `GET /widgets/{id}` returns a widget for ordinary ids.
- `GET /widgets/missing` throws a domain exception that maps to `404`.
- `GET /widgets/boom` throws a non-domain exception that maps to a sanitized `500`.
- `GET /secure` is protected by a route policy named `admin`.

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- The default correlation header is `X-Correlation-ID`.
- If a request has the correlation header, preserve it in the response. Otherwise generate a non-empty correlation id and add it to the response.
- Options validation must reject an empty `CorrelationHeaderName` and empty configured route policy values.
- Domain exceptions must map to their configured HTTP status code.
- Unexpected exceptions must return `500` without leaking exception type names, stack traces or internal messages.
- `RoutePolicyAttribute` marks endpoints that require a named policy.
- `HeaderRoutePolicyEvaluator` must read `RequestPipelineOptions.RoutePolicies[policyName]` and allow the request only when header `X-Policy` matches the configured value exactly.
- Missing policies deny access with `403`; return the status directly and do not rely on authentication services.
- Components must be separated and testable through dependency injection.
