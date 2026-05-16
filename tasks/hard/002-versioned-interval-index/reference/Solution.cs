using System;
using System.Collections.Generic;
using System.Linq;

public sealed record Interval<T>(int Start, int End, T Value, long Sequence);

public sealed class InvalidIntervalException : Exception
{
    public InvalidIntervalException(int start, int end)
        : base($"Invalid interval [{start}, {end}).")
    {
        Start = start;
        End = end;
    }

    public int Start { get; }
    public int End { get; }
}

public sealed class VersionedIntervalIndex<T>
{
    private readonly List<IReadOnlyList<Interval<T>>> versions = new() { Array.Empty<Interval<T>>() };
    private long nextSequence;

    public int CurrentVersion => versions.Count - 1;

    public int Add(int start, int end, T value)
    {
        ValidateRange(start, end);
        var next = versions[^1].Concat(new[] { new Interval<T>(start, end, value, ++nextSequence) }).ToArray();
        versions.Add(next);
        return CurrentVersion;
    }

    public IReadOnlyList<Interval<T>> Query(int start, int end)
    {
        return QueryVersion(CurrentVersion, start, end);
    }

    public IReadOnlyList<Interval<T>> QueryVersion(int version, int start, int end)
    {
        ValidateRange(start, end);
        if (version < 0 || version >= versions.Count)
        {
            throw new ArgumentOutOfRangeException(nameof(version));
        }

        return versions[version]
            .Where(interval => interval.Start < end && start < interval.End)
            .OrderBy(interval => interval.Start)
            .ThenBy(interval => interval.End)
            .ThenBy(interval => interval.Sequence)
            .ToArray();
    }

    private static void ValidateRange(int start, int end)
    {
        if (start >= end)
        {
            throw new InvalidIntervalException(start, end);
        }
    }
}
