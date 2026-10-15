# StackProject

A .NET 8 library providing `StackProject.SimpleStack<T>`.

Build with `dotnet build StackProject.csproj --configuration Release`.

Existing public behavior:
- `Count` starts at zero and reports the number of stored items.
- `Push(T item)` adds an item to the top. Null and default values are allowed.
- `Pop()` removes and returns the most recently pushed item.
- `Peek()` returns the top item without removing it.
- `Pop()` and `Peek()` throw `InvalidOperationException` on an empty stack.
- Stack instances maintain independent state. The stack is not thread-safe.

The public stack delegates storage to an internal array-backed collection.
