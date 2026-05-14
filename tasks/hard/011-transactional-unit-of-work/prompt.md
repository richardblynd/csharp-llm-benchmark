Write a transactional in-memory unit of work.

Required public API:

```csharp
public interface IEntity
{
    string Id { get; }
}

public sealed record Account(string Id, decimal Balance) : IEntity;

public interface IRepository<T> where T : class, IEntity
{
    T? Find(string id);
    IReadOnlyList<T> List();
    void Add(T entity);
    void Upsert(T entity);
    bool Remove(string id);
}

public interface IUnitOfWork : IDisposable
{
    IRepository<T> Repository<T>() where T : class, IEntity;
    void Commit();
    void Rollback();
}

public sealed class InMemoryDatabase
{
    public IUnitOfWork BeginUnitOfWork();
}
```

Rules:
- Do not include a namespace.
- Do not use external libraries.
- All code, public identifiers, exception messages and comments must be written in English.
- Entity ids must be non-empty after trimming.
- Changes are private to a unit of work until `Commit`.
- `Rollback` discards pending changes.
- Reads inside a unit of work must see that unit's own writes.
- Simultaneous units of work must not see each other's uncommitted changes.
- `Commit` and `Rollback` may be called only once. Using a unit of work or repository after commit, rollback or dispose must throw `InvalidOperationException`.
- `Add` must reject duplicate ids visible in the current unit of work.
- `Remove` returns `true` when an entity is removed and `false` when no visible entity exists for the id.
- Repositories must depend on the `IRepository<T>` contract and be obtained from `IUnitOfWork`.
