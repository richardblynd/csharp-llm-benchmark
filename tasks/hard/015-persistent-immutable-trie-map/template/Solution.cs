using System;
using System.Collections.Generic;

public sealed class PersistentTrieMap<T>
{
    public static PersistentTrieMap<T> Empty => throw new NotImplementedException();
    public int Count => throw new NotImplementedException();
    public PersistentTrieMap<T> Set(string key, T value) => throw new NotImplementedException();
    public PersistentTrieMap<T> Remove(string key) => throw new NotImplementedException();
    public bool TryGetValue(string key, out T value) => throw new NotImplementedException();
    public IReadOnlyList<KeyValuePair<string, T>> ScanPrefix(string prefix) => throw new NotImplementedException();
}
