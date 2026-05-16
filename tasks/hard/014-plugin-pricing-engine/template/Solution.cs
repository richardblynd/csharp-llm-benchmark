using System;
using System.Collections.Generic;

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

public sealed class PricingConfigurationException : Exception
{
    public PricingConfigurationException(string message) : base(message) { }
}

public sealed class PricingEngine
{
    public PricingEngine(IEnumerable<IPricingStrategy> strategies) => throw new NotImplementedException();
    public PricingResult Calculate(PricingContext context, IReadOnlyList<string>? strategyOrder = null) => throw new NotImplementedException();
}

public sealed class PercentageDiscountStrategy : IPricingStrategy
{
    public PercentageDiscountStrategy(string name, decimal percent, int order = 0, params string[] conflictsWith) => throw new NotImplementedException();
    public string Name => throw new NotImplementedException();
    public int Order => throw new NotImplementedException();
    public IReadOnlyCollection<string> ConflictsWith => throw new NotImplementedException();
    public decimal Apply(decimal currentAmount, PricingContext context) => throw new NotImplementedException();
    public string Describe(decimal amountBefore, decimal amountAfter, PricingContext context) => throw new NotImplementedException();
}

public sealed class FixedFeeStrategy : IPricingStrategy
{
    public FixedFeeStrategy(string name, decimal fee, int order = 0, params string[] conflictsWith) => throw new NotImplementedException();
    public string Name => throw new NotImplementedException();
    public int Order => throw new NotImplementedException();
    public IReadOnlyCollection<string> ConflictsWith => throw new NotImplementedException();
    public decimal Apply(decimal currentAmount, PricingContext context) => throw new NotImplementedException();
    public string Describe(decimal amountBefore, decimal amountAfter, PricingContext context) => throw new NotImplementedException();
}

public sealed class RegionalTaxStrategy : IPricingStrategy
{
    public RegionalTaxStrategy(string name, string region, decimal percent, int order = 0, params string[] conflictsWith) => throw new NotImplementedException();
    public string Name => throw new NotImplementedException();
    public int Order => throw new NotImplementedException();
    public IReadOnlyCollection<string> ConflictsWith => throw new NotImplementedException();
    public decimal Apply(decimal currentAmount, PricingContext context) => throw new NotImplementedException();
    public string Describe(decimal amountBefore, decimal amountAfter, PricingContext context) => throw new NotImplementedException();
}

public sealed class ShippingStrategy : IPricingStrategy
{
    public ShippingStrategy(string name, decimal baseFee, decimal feePerWeightUnit, int order = 0, params string[] conflictsWith) => throw new NotImplementedException();
    public string Name => throw new NotImplementedException();
    public int Order => throw new NotImplementedException();
    public IReadOnlyCollection<string> ConflictsWith => throw new NotImplementedException();
    public decimal Apply(decimal currentAmount, PricingContext context) => throw new NotImplementedException();
    public string Describe(decimal amountBefore, decimal amountAfter, PricingContext context) => throw new NotImplementedException();
}
