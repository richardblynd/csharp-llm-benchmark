using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    private sealed class Reader : global::IRecordReader
    {
        public IReadOnlyList<global::ImportRecord> Read() => new[]
        {
            new global::ImportRecord("1", "ok"),
            new global::ImportRecord("2", ""),
            new global::ImportRecord("3", "also ok")
        };
    }

    private sealed class Validator : global::IRecordValidator
    {
        public string? Validate(global::ImportRecord record) => string.IsNullOrWhiteSpace(record.Value) ? $"Invalid {record.Id}" : null;
    }

    private sealed class Repository : global::IRecordRepository
    {
        public readonly List<global::ImportRecord> Saved = new();
        public void Save(global::ImportRecord record) => Saved.Add(record);
    }

    [TestMethod]
    public void orchestrates_read_validate_and_persist()
    {
        var repository = new Repository();
        var importer = new global::RecordImporter(new Reader(), new Validator(), repository);

        var result = importer.Import();

        Assert.AreEqual(2, result.ImportedCount);
        Assert.AreEqual(2, repository.Saved.Count);
    }

    [TestMethod]
    public void depends_on_interfaces_not_concrete_implementations()
    {
        var parameters = typeof(global::RecordImporter).GetConstructors().Single().GetParameters().Select(p => p.ParameterType).ToArray();

        CollectionAssert.AreEqual(new[] { typeof(global::IRecordReader), typeof(global::IRecordValidator), typeof(global::IRecordRepository) }, parameters);
    }

    [TestMethod]
    public void can_be_tested_with_in_memory_fakes()
    {
        var repository = new Repository();
        var importer = new global::RecordImporter(new Reader(), new Validator(), repository);

        importer.Import();

        CollectionAssert.AreEqual(new[] { "1", "3" }, repository.Saved.Select(r => r.Id).ToArray());
    }

    [TestMethod]
    public void handles_invalid_records_without_stopping_all_processing()
    {
        var importer = new global::RecordImporter(new Reader(), new Validator(), new Repository());

        var result = importer.Import();

        Assert.AreEqual(1, result.InvalidCount);
        StringAssert.Contains(result.Errors.Single(), "Invalid 2");
    }
}
