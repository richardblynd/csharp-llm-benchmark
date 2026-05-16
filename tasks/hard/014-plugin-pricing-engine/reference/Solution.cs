using System;
using System.Collections.Generic;
using System.Linq;

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
    private readonly Dictionary<string, IPricingStrategy> strategies;

    public PricingEngine(IEnumerable<IPricingStrategy> strategies)
    {
        ArgumentNullException.ThrowIfNull(strategies);
        this.strategies = new Dictionary<string, IPricingStrategy>(StringComparer.Ordinal);
        foreach (var strategy in strategies)
        {
            if (string.IsNullOrWhiteSpace(strategy.Name))
            {
                throw new PricingConfigurationException("Strategy names are required.");
            }

            if (!this.strategies.TryAdd(strategy.Name, strategy))
            {
                throw new PricingConfigurationException($"Duplicate strategy '{strategy.Name}'.");
            }
        }
    }

    public PricingResult Calculate(PricingContext context, IReadOnlyList<string>? strategyOrder = null)
    {
        var selected = SelectStrategies(strategyOrder).ToArray();
        ValidateConflicts(selected);
        var amount = Math.Max(0m, context.BasePrice);
        var steps = new List<PricingStep>();

        foreach (var strategy in selected)
        {
            var before = amount;
            amount = Math.Max(0m, strategy.Apply(amount, context));
            steps.Add(new PricingStep(strategy.Name, before, amount, strategy.Describe(before, amount, context)));
        }

        return new PricingResult(amount, steps);
    }

    private IEnumerable<IPricingStrategy> SelectStrategies(IReadOnlyList<string>? strategyOrder)
    {
        if (strategyOrder is null)
        {
            return strategies.Values.OrderBy(strategy => strategy.Order).ThenBy(strategy => strategy.Name, StringComparer.Ordinal);
        }

        return strategyOrder.Select(name =>
        {
            if (!strategies.TryGetValue(name, out var strategy))
            {
                throw new PricingConfigurationException($"Unknown strategy '{name}'.");
            }

            return strategy;
        });
    }

    private static void ValidateConflicts(IReadOnlyCollection<IPricingStrategy> selected)
    {
        var names = selected.Select(strategy => strategy.Name).ToHashSet(StringComparer.Ordinal);
        foreach (var strategy in selected)
        {
            foreach (var conflict in strategy.ConflictsWith)
            {
                if (names.Contains(conflict))
                {
                    throw new PricingConfigurationException($"Strategy '{strategy.Name}' conflicts with '{conflict}'.");
                }
            }
        }
    }
}

public sealed class PercentageDiscountStrategy : IPricingStrategy
{
    private readonly decimal percent;

    public PercentageDiscountStrategy(string name, decimal percent, int order = 0, params string[] conflictsWith)
    {
        Name = name;
        this.percent = percent;
        Order = order;
        ConflictsWith = conflictsWith;
    }

    public string Name { get; }
    public int Order { get; }
    public IReadOnlyCollection<string> ConflictsWith { get; }
    public decimal Apply(decimal currentAmount, PricingContext context) => currentAmount - currentAmount * percent / 100m;
    public string Describe(decimal amountBefore, decimal amountAfter, PricingContext context) => $"{Name} changed the amount from {amountBefore} to {amountAfter}.";
}

public sealed class FixedFeeStrategy : IPricingStrategy
{
    private readonly decimal fee;

    public FixedFeeStrategy(string name, decimal fee, int order = 0, params string[] conflictsWith)
    {
        Name = name;
        this.fee = fee;
        Order = order;
        ConflictsWith = conflictsWith;
    }

    public string Name { get; }
    public int Order { get; }
    public IReadOnlyCollection<string> ConflictsWith { get; }
    public decimal Apply(decimal currentAmount, PricingContext context) => currentAmount + fee;
    public string Describe(decimal amountBefore, decimal amountAfter, PricingContext context) => $"{Name} changed the amount from {amountBefore} to {amountAfter}.";
}

public sealed class RegionalTaxStrategy : IPricingStrategy
{
    private readonly string region;
    private readonly decimal percent;

    public RegionalTaxStrategy(string name, string region, decimal percent, int order = 0, params string[] conflictsWith)
    {
        Name = name;
        this.region = region;
        this.percent = percent;
        Order = order;
        ConflictsWith = conflictsWith;
    }

    public string Name { get; }
    public int Order { get; }
    public IReadOnlyCollection<string> ConflictsWith { get; }
    public decimal Apply(decimal currentAmount, PricingContext context) => string.Equals(context.Region, region, StringComparison.Ordinal) ? currentAmount + currentAmount * percent / 100m : currentAmount;
    public string Describe(decimal amountBefore, decimal amountAfter, PricingContext context) => $"{Name} changed the amount from {amountBefore} to {amountAfter}.";
}

public sealed class ShippingStrategy : IPricingStrategy
{
    private readonly decimal baseFee;
    private readonly decimal feePerWeightUnit;

    public ShippingStrategy(string name, decimal baseFee, decimal feePerWeightUnit, int order = 0, params string[] conflictsWith)
    {
        Name = name;
        this.baseFee = baseFee;
        this.feePerWeightUnit = feePerWeightUnit;
        Order = order;
        ConflictsWith = conflictsWith;
    }

    public string Name { get; }
    public int Order { get; }
    public IReadOnlyCollection<string> ConflictsWith { get; }
    public decimal Apply(decimal currentAmount, PricingContext context) => currentAmount + baseFee + context.Weight * feePerWeightUnit;
    public string Describe(decimal amountBefore, decimal amountAfter, PricingContext context) => $"{Name} changed the amount from {amountBefore} to {amountAfter}.";
}
