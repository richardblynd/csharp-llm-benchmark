using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

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
    {
        throw new NotImplementedException();
    }

    public Task<EtlResult> RunAsync(CancellationToken cancellationToken = default)
    {
        throw new NotImplementedException();
    }
}
