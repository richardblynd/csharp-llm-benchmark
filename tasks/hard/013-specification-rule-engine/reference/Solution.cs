using System;
using System.Linq.Expressions;

public interface ISpecification<T>
{
    bool IsSatisfiedBy(T candidate);
    Expression<Func<T, bool>> ToExpression();
}

public abstract class Specification<T> : ISpecification<T>
{
    public abstract bool IsSatisfiedBy(T candidate);

    public virtual Expression<Func<T, bool>> ToExpression()
    {
        throw new NotSupportedException("This specification cannot be converted to an expression tree.");
    }

    public Specification<T> And(ISpecification<T> other)
    {
        ArgumentNullException.ThrowIfNull(other);
        return new AndSpecification<T>(this, other);
    }

    public Specification<T> Or(ISpecification<T> other)
    {
        ArgumentNullException.ThrowIfNull(other);
        return new OrSpecification<T>(this, other);
    }

    public Specification<T> Not()
    {
        return new NotSpecification<T>(this);
    }
}

public sealed class ExpressionSpecification<T> : Specification<T>
{
    private readonly Expression<Func<T, bool>> expression;
    private readonly Lazy<Func<T, bool>> compiled;

    public ExpressionSpecification(Expression<Func<T, bool>> expression)
    {
        this.expression = expression ?? throw new ArgumentNullException(nameof(expression));
        compiled = new Lazy<Func<T, bool>>(() => expression.Compile());
    }

    public override bool IsSatisfiedBy(T candidate) => compiled.Value(candidate);

    public override Expression<Func<T, bool>> ToExpression() => expression;
}

public sealed class DelegateSpecification<T> : Specification<T>
{
    private readonly Func<T, bool> predicate;

    public DelegateSpecification(Func<T, bool> predicate)
    {
        this.predicate = predicate ?? throw new ArgumentNullException(nameof(predicate));
    }

    public override bool IsSatisfiedBy(T candidate) => predicate(candidate);
}

public static class Specification
{
    public static Specification<T> FromExpression<T>(Expression<Func<T, bool>> expression) => new ExpressionSpecification<T>(expression);

    public static Specification<T> FromPredicate<T>(Func<T, bool> predicate) => new DelegateSpecification<T>(predicate);
}

internal sealed class AndSpecification<T> : Specification<T>
{
    private readonly ISpecification<T> left;
    private readonly ISpecification<T> right;

    public AndSpecification(ISpecification<T> left, ISpecification<T> right)
    {
        this.left = left;
        this.right = right;
    }

    public override bool IsSatisfiedBy(T candidate) => left.IsSatisfiedBy(candidate) && right.IsSatisfiedBy(candidate);

    public override Expression<Func<T, bool>> ToExpression()
    {
        var leftExpression = left.ToExpression();
        var rightExpression = right.ToExpression();
        return ExpressionComposer.Combine(leftExpression, rightExpression, Expression.AndAlso);
    }
}

internal sealed class OrSpecification<T> : Specification<T>
{
    private readonly ISpecification<T> left;
    private readonly ISpecification<T> right;

    public OrSpecification(ISpecification<T> left, ISpecification<T> right)
    {
        this.left = left;
        this.right = right;
    }

    public override bool IsSatisfiedBy(T candidate) => left.IsSatisfiedBy(candidate) || right.IsSatisfiedBy(candidate);

    public override Expression<Func<T, bool>> ToExpression()
    {
        var leftExpression = left.ToExpression();
        var rightExpression = right.ToExpression();
        return ExpressionComposer.Combine(leftExpression, rightExpression, Expression.OrElse);
    }
}

internal sealed class NotSpecification<T> : Specification<T>
{
    private readonly ISpecification<T> inner;

    public NotSpecification(ISpecification<T> inner)
    {
        this.inner = inner;
    }

    public override bool IsSatisfiedBy(T candidate) => !inner.IsSatisfiedBy(candidate);

    public override Expression<Func<T, bool>> ToExpression()
    {
        var expression = inner.ToExpression();
        return Expression.Lambda<Func<T, bool>>(Expression.Not(expression.Body), expression.Parameters);
    }
}

internal sealed class ReplaceParameterVisitor : ExpressionVisitor
{
    private readonly ParameterExpression from;
    private readonly ParameterExpression to;

    public ReplaceParameterVisitor(ParameterExpression from, ParameterExpression to)
    {
        this.from = from;
        this.to = to;
    }

    protected override Expression VisitParameter(ParameterExpression node)
    {
        return node == from ? to : node;
    }
}

internal static class ExpressionComposer
{
    public static Expression<Func<T, bool>> Combine<T>(
        Expression<Func<T, bool>> left,
        Expression<Func<T, bool>> right,
        Func<Expression, Expression, BinaryExpression> merge)
    {
        var parameter = left.Parameters[0];
        var rewrittenRight = new ReplaceParameterVisitor(right.Parameters[0], parameter).Visit(right.Body)!;
        return Expression.Lambda<Func<T, bool>>(merge(left.Body, rewrittenRight), parameter);
    }
}
