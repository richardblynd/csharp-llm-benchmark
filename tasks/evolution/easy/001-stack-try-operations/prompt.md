Extend the existing `StackProject` library with non-throwing stack operations.

The current `StackProject.SimpleStack<T>` is a working generic stack. Inspect
the project and preserve all existing public contracts described in its README.

Add these public instance methods to `SimpleStack<T>`:

```csharp
public bool TryPop(out T value)
public bool TryPeek(out T value)
```

Requirements:
- When empty, both methods return `false` and set `value` to `default(T)`.
- When nonempty, `TryPop` returns `true`, returns the latest pushed value and
  removes exactly that value.
- When nonempty, `TryPeek` returns `true` and returns the latest pushed value
  without removing it or changing `Count`.
- `null` and default values are valid stack items; success is determined by
  whether an item exists, not by its value.
- Calls to new and existing methods must observe the same stack contents.
- Preserve the namespace, generic type and existing methods. In particular,
  `Pop` and `Peek` must still throw `InvalidOperationException` when empty.
- Write code and identifiers in English. No new dependencies are needed.

You may organize the implementation across the permitted source files. No
thread-safety requirement is added by this feature.
