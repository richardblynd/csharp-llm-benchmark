Write a public generic class named `SimpleStack<T>` and a public class named
`Solution`.

`SimpleStack<T>` must support:

```csharp
public int Count { get; }
public void Push(T item)
public T Pop()
public T Peek()
```

Rules:
- `Pop` removes and returns the most recently pushed item.
- `Peek` returns the most recently pushed item without removing it.
- `Pop` and `Peek` must throw `InvalidOperationException` when the stack is empty.
- Store items using a list or array-backed collection.

Also include a public `Solution` class with this method so the file follows the
benchmark contract:

```csharp
public static bool Execute()
```

It may simply return `true`.
