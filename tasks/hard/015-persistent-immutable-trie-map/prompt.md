Write a persistent immutable trie map from strings to generic values.

Required public API:

```csharp
public sealed class PersistentTrieMap<T>
{
    public static PersistentTrieMap<T> Empty { get; }
    public int Count { get; }
    public PersistentTrieMap<T> Set(string key, T value)
    public PersistentTrieMap<T> Remove(string key)
    public bool TryGetValue(string key, out T value)
    public IReadOnlyList<KeyValuePair<string, T>> ScanPrefix(string prefix)
}
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- The map is immutable: `Set` and `Remove` return a new map and never mutate existing instances.
- `Empty` returns an empty map for the generic value type.
- String comparisons are ordinal.
- The empty string is a valid key.
- Null keys and null prefixes throw `ArgumentNullException`.
- Setting an existing key replaces only that key's value and does not increase `Count`.
- Removing a missing key returns an equivalent map without changing `Count`.
- `TryGetValue` returns `false` and assigns `default` for missing keys.
- `ScanPrefix` returns all matching pairs ordered lexicographically by key.
- Implement the structure as a trie with persistent path copying, not as a mutable dictionary exposed through snapshots.
