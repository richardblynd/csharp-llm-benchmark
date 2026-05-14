using System;
using System.Collections.Generic;

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
    public IUnitOfWork BeginUnitOfWork()
    {
        throw new NotImplementedException();
    }
}
