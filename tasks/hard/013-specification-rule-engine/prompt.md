Write a composable specification rule engine.

Required public API:

```csharp
public interface ISpecification<T>
{
    bool IsSatisfiedBy(T candidate);
    Expression<Func<T, bool>> ToExpression();
}

public abstract class Specification<T> : ISpecification<T>
{
    public abstract bool IsSatisfiedBy(T candidate);
    public virtual Expression<Func<T, bool>> ToExpression();
    public Specification<T> And(ISpecification<T> other);
    public Specification<T> Or(ISpecification<T> other);
    public Specification<T> Not();
}

public sealed class ExpressionSpecification<T> : Specification<T>
{
    public ExpressionSpecification(Expression<Func<T, bool>> expression);
}

public sealed class DelegateSpecification<T> : Specification<T>
{
    public DelegateSpecification(Func<T, bool> predicate);
}

public static class Specification
{
    public static Specification<T> FromExpression<T>(Expression<Func<T, bool>> expression);
    public static Specification<T> FromPredicate<T>(Func<T, bool> predicate);
}
```

Rules:
- Do not include a namespace.
- Do not use external libraries.
- All code, public identifiers, exception messages and comments must be written in English.
- `And`, `Or` and `Not` must be composable without modifying existing specification classes.
- In-memory evaluation must preserve normal C# short-circuit behavior for `And` and `Or`.
- Expression-backed specifications must produce equivalent `Expression<Func<T, bool>>` trees for composed rules.
- Delegate-backed specifications may be evaluated in memory but are not convertible to expression trees.
- Non-convertible specifications must throw `NotSupportedException` with a clear English message from `ToExpression`.
- Custom specifications derived in tests must work with the composition engine.
