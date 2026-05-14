using System;
using System.Collections.Generic;
using System.Linq;

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
    private readonly object gate = new();
    private Dictionary<Type, Dictionary<string, IEntity>> committed = new();

    public IUnitOfWork BeginUnitOfWork()
    {
        lock (gate)
        {
            return new UnitOfWork(this, Clone(committed));
        }
    }

    private void Commit(Dictionary<Type, Dictionary<string, IEntity>> working)
    {
        lock (gate)
        {
            committed = Clone(working);
        }
    }

    private static Dictionary<Type, Dictionary<string, IEntity>> Clone(Dictionary<Type, Dictionary<string, IEntity>> source)
    {
        return source.ToDictionary(
            pair => pair.Key,
            pair => pair.Value.ToDictionary(entity => entity.Key, entity => entity.Value, StringComparer.Ordinal));
    }

    private sealed class UnitOfWork : IUnitOfWork
    {
        private readonly InMemoryDatabase database;
        private readonly Dictionary<Type, Dictionary<string, IEntity>> working;
        private readonly Dictionary<Type, object> repositories = new();
        private bool completed;
        private bool disposed;

        public UnitOfWork(InMemoryDatabase database, Dictionary<Type, Dictionary<string, IEntity>> working)
        {
            this.database = database;
            this.working = working;
        }

        public IRepository<T> Repository<T>() where T : class, IEntity
        {
            EnsureActive();
            var type = typeof(T);
            if (!repositories.TryGetValue(type, out var repository))
            {
                repository = new Repository<T>(this);
                repositories[type] = repository;
            }

            return (IRepository<T>)repository;
        }

        public void Commit()
        {
            EnsureActive();
            database.Commit(working);
            completed = true;
        }

        public void Rollback()
        {
            EnsureActive();
            completed = true;
        }

        public void Dispose()
        {
            disposed = true;
        }

        public Dictionary<string, IEntity> StoreFor<T>() where T : class, IEntity
        {
            EnsureActive();
            var type = typeof(T);
            if (!working.TryGetValue(type, out var store))
            {
                store = new Dictionary<string, IEntity>(StringComparer.Ordinal);
                working[type] = store;
            }

            return store;
        }

        public void EnsureActive()
        {
            if (completed || disposed)
            {
                throw new InvalidOperationException("The unit of work is no longer active.");
            }
        }
    }

    private sealed class Repository<T> : IRepository<T> where T : class, IEntity
    {
        private readonly UnitOfWork unitOfWork;

        public Repository(UnitOfWork unitOfWork)
        {
            this.unitOfWork = unitOfWork;
        }

        public T? Find(string id)
        {
            var normalized = NormalizeId(id);
            var store = unitOfWork.StoreFor<T>();
            return store.TryGetValue(normalized, out var entity) ? (T)entity : null;
        }

        public IReadOnlyList<T> List()
        {
            return unitOfWork.StoreFor<T>().Values.Cast<T>().OrderBy(entity => entity.Id, StringComparer.Ordinal).ToArray();
        }

        public void Add(T entity)
        {
            ArgumentNullException.ThrowIfNull(entity);
            var id = NormalizeId(entity.Id);
            var store = unitOfWork.StoreFor<T>();
            if (store.ContainsKey(id))
            {
                throw new InvalidOperationException("An entity with the same id already exists.");
            }

            store[id] = entity;
        }

        public void Upsert(T entity)
        {
            ArgumentNullException.ThrowIfNull(entity);
            unitOfWork.StoreFor<T>()[NormalizeId(entity.Id)] = entity;
        }

        public bool Remove(string id)
        {
            return unitOfWork.StoreFor<T>().Remove(NormalizeId(id));
        }

        private static string NormalizeId(string id)
        {
            if (string.IsNullOrWhiteSpace(id))
            {
                throw new ArgumentException("Entity ids must be non-empty.", nameof(id));
            }

            return id.Trim();
        }
    }
}
