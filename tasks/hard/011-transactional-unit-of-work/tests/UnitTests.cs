using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    private static void AssertThrowsAnyException(Action action)
    {
        try
        {
            action();
        }
        catch (Exception)
        {
            return;
        }

        Assert.Fail("Expected an exception, but no exception was thrown.");
    }

    [TestMethod]
    public void persists_entities_after_commit()
    {
        var database = new global::InMemoryDatabase();
        using (var unit = database.BeginUnitOfWork())
        {
            unit.Repository<global::Account>().Add(new global::Account("a1", 100m));
            unit.Commit();
        }

        using var read = database.BeginUnitOfWork();
        Assert.AreEqual(100m, read.Repository<global::Account>().Find("a1")!.Balance);
    }

    [TestMethod]
    public void discards_changes_after_rollback()
    {
        var database = new global::InMemoryDatabase();
        using (var unit = database.BeginUnitOfWork())
        {
            unit.Repository<global::Account>().Add(new global::Account("a1", 100m));
            unit.Rollback();
        }

        using var read = database.BeginUnitOfWork();
        Assert.IsNull(read.Repository<global::Account>().Find("a1"));
    }

    [TestMethod]
    public void reads_own_writes_before_commit()
    {
        using var unit = new global::InMemoryDatabase().BeginUnitOfWork();
        var repository = unit.Repository<global::Account>();

        repository.Add(new global::Account("a1", 10m));
        repository.Upsert(new global::Account("a1", 15m));

        Assert.AreEqual(15m, repository.Find("a1")!.Balance);
        CollectionAssert.AreEqual(new[] { "a1" }, repository.List().Select(account => account.Id).ToArray());
    }

    [TestMethod]
    public void isolates_concurrent_units_of_work()
    {
        var database = new global::InMemoryDatabase();
        using var first = database.BeginUnitOfWork();
        using var second = database.BeginUnitOfWork();

        first.Repository<global::Account>().Add(new global::Account("a1", 10m));

        Assert.IsNull(second.Repository<global::Account>().Find("a1"));

        first.Commit();

        Assert.IsNull(second.Repository<global::Account>().Find("a1"));
        using var third = database.BeginUnitOfWork();
        Assert.IsNotNull(third.Repository<global::Account>().Find("a1"));
    }

    [TestMethod]
    public void rejects_double_commit_and_use_after_dispose()
    {
        var database = new global::InMemoryDatabase();
        var unit = database.BeginUnitOfWork();
        var repository = unit.Repository<global::Account>();
        unit.Commit();

        Assert.ThrowsException<InvalidOperationException>(() => unit.Commit());
        Assert.ThrowsException<InvalidOperationException>(() => repository.List());
        unit.Dispose();
        Assert.ThrowsException<InvalidOperationException>(() => unit.Repository<global::Account>());
    }

    [TestMethod]
    public void exposes_repository_contracts()
    {
        var unitType = typeof(global::IUnitOfWork);
        var method = unitType.GetMethod(nameof(global::IUnitOfWork.Repository))!;

        Assert.AreEqual(typeof(global::IRepository<>), method.ReturnType.GetGenericTypeDefinition());
        Assert.IsTrue(typeof(IDisposable).IsAssignableFrom(unitType));
    }

    [TestMethod]
    public void handles_duplicate_ids_and_missing_entities()
    {
        using var unit = new global::InMemoryDatabase().BeginUnitOfWork();
        var repository = unit.Repository<global::Account>();

        repository.Add(new global::Account("a1", 1m));

        AssertThrowsAnyException(() => repository.Add(new global::Account("a1", 2m)));
        Assert.IsFalse(repository.Remove("missing"));
        AssertThrowsAnyException(() => repository.Add(new global::Account("", 0m)));
    }
}
