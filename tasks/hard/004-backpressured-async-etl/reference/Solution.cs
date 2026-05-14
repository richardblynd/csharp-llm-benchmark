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
    private readonly IAsyncRecordReader<TInput> reader;
    private readonly IAsyncRecordValidator<TInput> validator;
    private readonly IAsyncRecordTransformer<TInput, TOutput> transformer;
    private readonly IAsyncBatchWriter<TOutput> writer;
    private readonly EtlOptions options;

    public BackpressuredEtlPipeline(
        IAsyncRecordReader<TInput> reader,
        IAsyncRecordValidator<TInput> validator,
        IAsyncRecordTransformer<TInput, TOutput> transformer,
        IAsyncBatchWriter<TOutput> writer,
        EtlOptions options)
    {
        ArgumentNullException.ThrowIfNull(reader);
        ArgumentNullException.ThrowIfNull(validator);
        ArgumentNullException.ThrowIfNull(transformer);
        ArgumentNullException.ThrowIfNull(writer);
        if (options.BatchSize < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(options), "Batch size must be positive.");
        }

        if (options.BufferCapacity < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(options), "Buffer capacity must be positive.");
        }

        this.reader = reader;
        this.validator = validator;
        this.transformer = transformer;
        this.writer = writer;
        this.options = options;
    }

    public async Task<EtlResult> RunAsync(CancellationToken cancellationToken = default)
    {
        var errors = new List<EtlError>();
        var batch = new List<TOutput>(options.BatchSize);
        var readCount = 0;
        var writtenCount = 0;
        var index = 0;

        try
        {
            await foreach (var item in reader.ReadAsync(cancellationToken).WithCancellation(cancellationToken))
            {
                cancellationToken.ThrowIfCancellationRequested();
                readCount++;
                var currentIndex = index++;

                string? validationError;
                try
                {
                    validationError = await validator.ValidateAsync(item, cancellationToken);
                }
                catch (Exception ex) when (ex is not OperationCanceledException)
                {
                    validationError = ex.Message;
                }

                if (!string.IsNullOrWhiteSpace(validationError))
                {
                    errors.Add(new EtlError(currentIndex, validationError));
                    continue;
                }

                try
                {
                    batch.Add(await transformer.TransformAsync(item, cancellationToken));
                }
                catch (Exception ex) when (ex is not OperationCanceledException)
                {
                    errors.Add(new EtlError(currentIndex, ex.Message));
                    continue;
                }

                if (batch.Count >= options.BatchSize)
                {
                    await writer.WriteBatchAsync(batch.ToArray(), cancellationToken);
                    writtenCount += batch.Count;
                    batch.Clear();
                }
            }

            if (batch.Count > 0)
            {
                await writer.WriteBatchAsync(batch.ToArray(), cancellationToken);
                writtenCount += batch.Count;
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            return new EtlResult(readCount, writtenCount, errors);
        }

        return new EtlResult(readCount, writtenCount, errors);
    }
}
