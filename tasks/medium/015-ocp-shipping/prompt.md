Implement extensible shipping calculation using the Open/Closed Principle.

Required public API:

```csharp
public sealed class ShippingRequest
{
    public ShippingRequest(decimal weightKg, decimal distanceKm)
    public decimal WeightKg { get; }
    public decimal DistanceKm { get; }
}

public interface IShippingStrategy
{
    string Method { get; }
    decimal Calculate(ShippingRequest request);
}

public sealed class StandardShippingStrategy
public sealed class ExpressShippingStrategy

public sealed class ShippingCalculator
{
    public ShippingCalculator(IEnumerable<IShippingStrategy> strategies)
    public decimal Calculate(string method, ShippingRequest request)
}
```

Rules:
- Do not include a namespace.
- Do not use external libraries.
- All code, public identifiers, exception messages and comments must be written in English.
- `ShippingRequest` must expose weight in kilograms and distance in kilometers.
- `IShippingStrategy` must expose a method name and a calculation method.
- Standard shipping costs `5 + weightKg * 1.25m + distanceKm * 0.02m`.
- Express shipping costs `12 + weightKg * 2.00m + distanceKm * 0.05m`.
- `ShippingCalculator` must receive strategies through its constructor and choose by method name.
- New strategies supplied by tests must work without modifying `ShippingCalculator`.
- Unknown method names must throw `InvalidOperationException`.
