Write a backpressured asynchronous ETL pipeline.

Required public API:

```csharp
public sealed record EtlOptions(int BatchSize, int BufferCapacity);
public sealed record EtlError(int Index, string Message);
public sealed record EtlResult(int ReadCount, int WrittenCount, IReadOnlyList<EtlError> Errors);

public interface IAsyncRecordReader<TInput>
{
    IAsyncEnumerable<TInput> ReadAsync(CancellationToken cancellationToken = default);
}

public interface IAsyncRecordValidator<TInput>
{
    ValueTask<string?> ValidateAsync(TInput item, CancellationToken cancellationToken = default);
}

public interface IAsyncRecordTransformer<TInput, TOutput>
{
    ValueTask<TOutput> TransformAsync(TInput item, CancellationToken cancellationToken = default);
}

public interface IAsyncBatchWriter<TOutput>
{
    ValueTask WriteBatchAsync(IReadOnlyList<TOutput> batch, CancellationToken cancellationToken = default);
}

public sealed class BackpressuredEtlPipeline<TInput, TOutput>
{
    public BackpressuredEtlPipeline(
        IAsyncRecordReader<TInput> reader,
        IAsyncRecordValidator<TInput> validator,
        IAsyncRecordTransformer<TInput, TOutput> transformer,
        IAsyncBatchWriter<TOutput> writer,
        EtlOptions options)

    public Task<EtlResult> RunAsync(CancellationToken cancellationToken = default)
}

public sealed class ResilientTransformer<TInput, TOutput> : IAsyncRecordTransformer<TInput, TOutput>
{
    public ResilientTransformer(IAsyncRecordTransformer<TInput, TOutput> inner, int maxAttempts)
    public ValueTask<TOutput> TransformAsync(TInput item, CancellationToken cancellationToken = default)
}
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- `BatchSize` and `BufferCapacity` must be positive.
- The pipeline must keep the input order for valid transformed records.
- Validation failures are reported as `EtlError` entries and must not stop other records from being processed.
- Transformation failures are reported as `EtlError` entries and must not stop other records from being processing.
- The writer receives only valid transformed records, in batches no larger than `BatchSize`.
- The reader must not be allowed to run unboundedly ahead of downstream work; use bounded buffering or sequential backpressure.
- If cancellation is requested after partial work, return the partial `EtlResult` instead of discarding it.
- Constructor dependencies must be abstractions so tests can provide in-memory fakes.

**ResilientTransformer:**
- Wraps an inner transformer and retries on transient failures up to `maxAttempts`.
- If the inner transform succeeds within the retry limit, return its value normally (no error).
- If all attempts fail, record a single `EtlError` via the pipeline mechanism — do not throw. The item must not appear in written output.
- Do not retry beyond `maxAttempts`. Each attempt counts toward the total, including the first call.
