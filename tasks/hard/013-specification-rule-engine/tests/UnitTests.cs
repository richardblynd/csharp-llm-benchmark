using System.Linq.Expressions;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    private sealed record Product(string Name, decimal Price, bool Active);

    [TestMethod]
    public void evaluates_simple_expression_specifications()
    {
        var expensive = global::Specification.FromExpression<Product>(product => product.Price > 100m);

        Assert.IsTrue(expensive.IsSatisfiedBy(new Product("Desk", 150m, true)));
        Assert.IsFalse(expensive.IsSatisfiedBy(new Product("Pen", 2m, true)));
    }

    [TestMethod]
    public void combines_rules_with_and_or_not()
    {
        var expensive = global::Specification.FromExpression<Product>(product => product.Price > 100m);
        var active = global::Specification.FromExpression<Product>(product => product.Active);
        var namedDesk = global::Specification.FromExpression<Product>(product => product.Name == "Desk");
        var rule = expensive.And(active).Or(namedDesk.Not());

        Assert.IsTrue(rule.IsSatisfiedBy(new Product("Chair", 200m, true)));
        Assert.IsFalse(rule.IsSatisfiedBy(new Product("Desk", 50m, true)));
        Assert.IsTrue(rule.IsSatisfiedBy(new Product("Lamp", 20m, false)));
    }

    [TestMethod]
    public void preserves_short_circuit_for_in_memory_evaluation()
    {
        var calls = 0;
        var alwaysFalse = global::Specification.FromPredicate<int>(_ => false);
        var alwaysTrue = global::Specification.FromPredicate<int>(_ => true);
        var counting = global::Specification.FromPredicate<int>(_ =>
        {
            calls++;
            return true;
        });

        Assert.IsFalse(alwaysFalse.And(counting).IsSatisfiedBy(1));
        Assert.IsTrue(alwaysTrue.Or(counting).IsSatisfiedBy(1));
        Assert.AreEqual(0, calls);
    }

    [TestMethod]
    public void builds_equivalent_expression_tree()
    {
        var rule = global::Specification
            .FromExpression<Product>(product => product.Price >= 10m)
            .And(global::Specification.FromExpression<Product>(product => product.Active))
            .Not();

        var compiled = rule.ToExpression().Compile();

        Assert.IsFalse(compiled(new Product("Book", 20m, true)));
        Assert.IsTrue(compiled(new Product("Book", 5m, true)));
        Assert.IsTrue(compiled(new Product("Book", 20m, false)));
    }

    [TestMethod]
    public void allows_custom_specifications_without_engine_changes()
    {
        var startsWithA = new StartsWithSpecification("A");
        var active = global::Specification.FromExpression<Product>(product => product.Active);
        var rule = startsWithA.And(active);

        Assert.IsTrue(rule.IsSatisfiedBy(new Product("Apple", 1m, true)));
        Assert.IsFalse(rule.IsSatisfiedBy(new Product("Banana", 1m, true)));
        Assert.IsFalse(rule.IsSatisfiedBy(new Product("Apple", 1m, false)));
    }

    [TestMethod]
    public void reports_non_convertible_rules_clearly()
    {
        var rule = global::Specification.FromPredicate<Product>(product => product.Active);

        var exception = Assert.ThrowsException<NotSupportedException>(() => rule.ToExpression());

        Assert.IsTrue(exception.Message.Contains("expression", StringComparison.OrdinalIgnoreCase));
    }

    private sealed class StartsWithSpecification : global::Specification<Product>
    {
        private readonly string prefix;

        public StartsWithSpecification(string prefix) => this.prefix = prefix;

        public override bool IsSatisfiedBy(Product candidate) => candidate.Name.StartsWith(prefix, StringComparison.Ordinal);

        public override Expression<Func<Product, bool>> ToExpression()
        {
            return product => product.Name.StartsWith(prefix);
        }
    }
}
