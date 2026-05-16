Write a plugin-based pricing engine.

Required public API:

```csharp
public sealed record PricingContext(decimal BasePrice, string CustomerType, string Region, decimal Weight);
public sealed record PricingStep(string StrategyName, decimal AmountBefore, decimal AmountAfter, string Description);
public sealed record PricingResult(decimal Total, IReadOnlyList<PricingStep> Steps);

public interface IPricingStrategy
{
    string Name { get; }
    int Order { get; }
    IReadOnlyCollection<string> ConflictsWith { get; }
    decimal Apply(decimal currentAmount, PricingContext context);
    string Describe(decimal amountBefore, decimal amountAfter, PricingContext context);
}

public sealed class PricingConfigurationException : Exception { }

public sealed class PricingEngine
{
    public PricingEngine(IEnumerable<IPricingStrategy> strategies)
    public PricingResult Calculate(PricingContext context, IReadOnlyList<string>? strategyOrder = null)
}

public sealed class PercentageDiscountStrategy : IPricingStrategy { }
public sealed class FixedFeeStrategy : IPricingStrategy { }
public sealed class RegionalTaxStrategy : IPricingStrategy { }
public sealed class ShippingStrategy : IPricingStrategy { }
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- Strategy names are compared ordinally.
- The engine must reject duplicate strategy names during construction.
- `Calculate` must start the running amount at `context.BasePrice`.
- `Calculate` uses `strategyOrder` when provided; otherwise it runs all strategies by ascending `Order`, then `Name`.
- A configured strategy name that was not registered must throw `PricingConfigurationException`.
- If selected strategies conflict through `ConflictsWith`, calculation must throw `PricingConfigurationException`.
- The running amount must never become negative; clamp negative strategy results to zero.
- Every executed strategy must append a `PricingStep` with before and after amounts.
- Custom strategies supplied by tests must work without changing the engine.
- Built-in strategies:
  - `PercentageDiscountStrategy(string name, decimal percent, int order = 0, params string[] conflictsWith)` subtracts `percent` percent from the current amount.
  - `FixedFeeStrategy(string name, decimal fee, int order = 0, params string[] conflictsWith)` adds `fee`.
  - `RegionalTaxStrategy(string name, string region, decimal percent, int order = 0, params string[] conflictsWith)` adds tax only when `context.Region` matches.
  - `ShippingStrategy(string name, decimal baseFee, decimal feePerWeightUnit, int order = 0, params string[] conflictsWith)` adds `baseFee + context.Weight * feePerWeightUnit`.
