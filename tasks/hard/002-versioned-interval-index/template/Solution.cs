using System;
using System.Collections.Generic;

public sealed record Interval<T>(int Start, int End, T Value, long Sequence);

public sealed class InvalidIntervalException : Exception
{
    public InvalidIntervalException(int start, int end)
    {
        Start = start;
        End = end;
    }

    public int Start { get; }
    public int End { get; }
}

public sealed class VersionedIntervalIndex<T>
{
    public int CurrentVersion => throw new NotImplementedException();
    public int Add(int start, int end, T value) => throw new NotImplementedException();
    public IReadOnlyList<Interval<T>> Query(int start, int end) => throw new NotImplementedException();
    public IReadOnlyList<Interval<T>> QueryVersion(int version, int start, int end) => throw new NotImplementedException();
}
