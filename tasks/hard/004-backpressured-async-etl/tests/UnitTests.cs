using System.Runtime.CompilerServices;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public async Task processes_valid_records_in_order()
    {
        var writer = new RecordingWriter<string>();
        var pipeline = CreatePipeline(new[] { "a", "b", "c" }, writer, batchSize: 2);

        var result = await pipeline.RunAsync();

        Assert.AreEqual(3, result.ReadCount);
        Assert.AreEqual(3, result.WrittenCount);
        CollectionAssert.AreEqual(new[] { "A", "B", "C" }, writer.Flattened.ToArray());
    }

    [TestMethod]
    public async Task records_item_errors_without_stopping_batch()
    {
        var writer = new RecordingWriter<string>();
        var pipeline = new global::BackpressuredEtlPipeline<string, string>(
            new EnumerableReader<string>(new[] { "ok", "", "boom", "fine" }),
            new DelegateValidator<string>(item => string.IsNullOrWhiteSpace(item) ? "Value is required." : null),
            new DelegateTransformer<string, string>(item => item == "boom" ? throw new InvalidOperationException("Cannot transform.") : item.ToUpperInvariant()),
            writer,
            new global::EtlOptions(2, 2));

        var result = await pipeline.RunAsync();

        Assert.AreEqual(4, result.ReadCount);
        Assert.AreEqual(2, result.WrittenCount);
        Assert.AreEqual(2, result.Errors.Count);
        CollectionAssert.AreEqual(new[] { "OK", "FINE" }, writer.Flattened.ToArray());
        CollectionAssert.AreEqual(new[] { 1, 2 }, result.Errors.Select(error => error.Index).ToArray());
    }

    [TestMethod]
    public async Task respects_buffer_capacity_while_writer_is_blocked()
    {
        var writer = new BlockingWriter<string>();
        var reader = new CountingReader(Enumerable.Range(0, 20).Select(value => value.ToString()).ToArray());
        var pipeline = new global::BackpressuredEtlPipeline<string, string>(
            reader,
            new DelegateValidator<string>(_ => null),
            new DelegateTransformer<string, string>(item => item),
            writer,
            new global::EtlOptions(1, 2));

        var run = pipeline.RunAsync();
        Assert.IsTrue(await writer.FirstBatchStarted.Task.WaitAsync(TimeSpan.FromSeconds(1)));
        await Task.Delay(50);

        Assert.IsTrue(reader.Produced <= 3, $"Reader ran too far ahead: {reader.Produced}.");

        writer.Release();
        await run;
    }

    [TestMethod]
    public async Task honors_cancellation_with_partial_report()
    {
        using var cts = new CancellationTokenSource();
        var writer = new RecordingWriter<string>();
        var pipeline = new global::BackpressuredEtlPipeline<string, string>(
            new CancelingReader(cts),
            new DelegateValidator<string>(_ => null),
            new DelegateTransformer<string, string>(item => item.ToUpperInvariant()),
            writer,
            new global::EtlOptions(1, 1));

        var result = await pipeline.RunAsync(cts.Token);

        Assert.AreEqual(1, result.ReadCount);
        Assert.AreEqual(1, result.WrittenCount);
        CollectionAssert.AreEqual(new[] { "FIRST" }, writer.Flattened.ToArray());
    }

    [TestMethod]
    public async Task writes_records_in_configured_batches()
    {
        var writer = new RecordingWriter<string>();
        var pipeline = CreatePipeline(new[] { "a", "b", "c", "d", "e" }, writer, batchSize: 2);

        await pipeline.RunAsync();

        CollectionAssert.AreEqual(new[] { 2, 2, 1 }, writer.Batches.Select(batch => batch.Count).ToArray());
    }

    [TestMethod]
    public void exposes_separate_contracts_for_pipeline_parts()
    {
        var constructor = typeof(global::BackpressuredEtlPipeline<string, string>).GetConstructors().Single();
        var parameters = constructor.GetParameters().Select(parameter => parameter.ParameterType).ToArray();

        CollectionAssert.AreEqual(new[]
        {
            typeof(global::IAsyncRecordReader<string>),
            typeof(global::IAsyncRecordValidator<string>),
            typeof(global::IAsyncRecordTransformer<string, string>),
            typeof(global::IAsyncBatchWriter<string>),
            typeof(global::EtlOptions)
        }, parameters);
    }

    [TestMethod]
    public async Task handles_empty_input()
    {
        var writer = new RecordingWriter<string>();
        var pipeline = CreatePipeline(Array.Empty<string>(), writer, batchSize: 3);

        var result = await pipeline.RunAsync();

        Assert.AreEqual(0, result.ReadCount);
        Assert.AreEqual(0, result.WrittenCount);
        Assert.AreEqual(0, result.Errors.Count);
        Assert.AreEqual(0, writer.Batches.Count);
    }

    private static global::BackpressuredEtlPipeline<string, string> CreatePipeline(
        IReadOnlyList<string> items,
        RecordingWriter<string> writer,
        int batchSize)
    {
        return new global::BackpressuredEtlPipeline<string, string>(
            new EnumerableReader<string>(items),
            new DelegateValidator<string>(_ => null),
            new DelegateTransformer<string, string>(item => item.ToUpperInvariant()),
            writer,
            new global::EtlOptions(batchSize, 2));
    }

    private sealed class EnumerableReader<T> : global::IAsyncRecordReader<T>
    {
        private readonly IReadOnlyList<T> items;

        public EnumerableReader(IReadOnlyList<T> items) => this.items = items;

        public async IAsyncEnumerable<T> ReadAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            foreach (var item in items)
            {
                cancellationToken.ThrowIfCancellationRequested();
                await Task.Yield();
                yield return item;
            }
        }
    }

    private sealed class CountingReader : global::IAsyncRecordReader<string>
    {
        private readonly IReadOnlyList<string> items;

        public CountingReader(IReadOnlyList<string> items) => this.items = items;

        public int Produced { get; private set; }

        public async IAsyncEnumerable<string> ReadAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            foreach (var item in items)
            {
                cancellationToken.ThrowIfCancellationRequested();
                Produced++;
                await Task.Yield();
                yield return item;
            }
        }
    }

    private sealed class CancelingReader : global::IAsyncRecordReader<string>
    {
        private readonly CancellationTokenSource source;

        public CancelingReader(CancellationTokenSource source) => this.source = source;

        public async IAsyncEnumerable<string> ReadAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            yield return "first";
            source.Cancel();
            await Task.Yield();
            cancellationToken.ThrowIfCancellationRequested();
            yield return "second";
        }
    }

    private sealed class DelegateValidator<T> : global::IAsyncRecordValidator<T>
    {
        private readonly Func<T, string?> validate;

        public DelegateValidator(Func<T, string?> validate) => this.validate = validate;

        public ValueTask<string?> ValidateAsync(T item, CancellationToken cancellationToken = default) => ValueTask.FromResult(validate(item));
    }

    private sealed class DelegateTransformer<TInput, TOutput> : global::IAsyncRecordTransformer<TInput, TOutput>
    {
        private readonly Func<TInput, TOutput> transform;

        public DelegateTransformer(Func<TInput, TOutput> transform) => this.transform = transform;

        public ValueTask<TOutput> TransformAsync(TInput item, CancellationToken cancellationToken = default) => ValueTask.FromResult(transform(item));
    }

    private sealed class RecordingWriter<T> : global::IAsyncBatchWriter<T>
    {
        public List<IReadOnlyList<T>> Batches { get; } = new();
        public IEnumerable<T> Flattened => Batches.SelectMany(batch => batch);

        public ValueTask WriteBatchAsync(IReadOnlyList<T> batch, CancellationToken cancellationToken = default)
        {
            Batches.Add(batch.ToArray());
            return ValueTask.CompletedTask;
        }
    }

    private sealed class BlockingWriter<T> : global::IAsyncBatchWriter<T>
    {
        private readonly TaskCompletionSource release = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int started;

        public TaskCompletionSource<bool> FirstBatchStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public async ValueTask WriteBatchAsync(IReadOnlyList<T> batch, CancellationToken cancellationToken = default)
        {
            if (Interlocked.Exchange(ref started, 1) == 0)
            {
                FirstBatchStarted.TrySetResult(true);
                await release.Task.WaitAsync(cancellationToken);
            }
        }

        public void Release() => release.TrySetResult();
    }
}
