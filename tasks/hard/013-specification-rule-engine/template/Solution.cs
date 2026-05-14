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
    public virtual Expression<Func<T, bool>> ToExpression() => throw new NotSupportedException();
    public Specification<T> And(ISpecification<T> other) => throw new NotImplementedException();
    public Specification<T> Or(ISpecification<T> other) => throw new NotImplementedException();
    public Specification<T> Not() => throw new NotImplementedException();
}

public sealed class ExpressionSpecification<T> : Specification<T>
{
    public ExpressionSpecification(Expression<Func<T, bool>> expression)
    {
        throw new NotImplementedException();
    }

    public override bool IsSatisfiedBy(T candidate) => throw new NotImplementedException();
    public override Expression<Func<T, bool>> ToExpression() => throw new NotImplementedException();
}

public sealed class DelegateSpecification<T> : Specification<T>
{
    public DelegateSpecification(Func<T, bool> predicate)
    {
        throw new NotImplementedException();
    }

    public override bool IsSatisfiedBy(T candidate) => throw new NotImplementedException();
}

public static class Specification
{
    public static Specification<T> FromExpression<T>(Expression<Func<T, bool>> expression) => throw new NotImplementedException();
    public static Specification<T> FromPredicate<T>(Func<T, bool> predicate) => throw new NotImplementedException();
}
