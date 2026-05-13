Implement substitutable discount rules following the Liskov Substitution Principle.

Required public API:

```csharp
public interface IDiscountRule
{
    decimal CalculateDiscount(decimal price);
}

public sealed class PercentageDiscountRule
{
    public PercentageDiscountRule(decimal percentage)
}

public sealed class FixedAmountDiscountRule
{
    public FixedAmountDiscountRule(decimal amount)
}

public sealed class NoDiscountRule

public sealed class DiscountService
{
    public DiscountService(IDiscountRule rule)
    public decimal GetFinalPrice(decimal price)
}
```

Rules:
- Do not include a namespace.
- Do not use external libraries.
- All code, public identifiers, exception messages and comments must be written in English.
- `IDiscountRule` must expose a method that returns the discount amount for a valid price.
- Valid prices are zero or positive.
- Rules must not throw for valid prices.
- Returned discounts must never be negative and must never exceed the original price.
- `PercentageDiscountRule(0.10m)` gives a 10% discount.
- `FixedAmountDiscountRule(5m)` discounts up to 5, capped by the price.
- `DiscountService` must accept any `IDiscountRule` and return the final price.
