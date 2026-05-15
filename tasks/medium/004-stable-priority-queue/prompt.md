Write a public generic class named `StablePriorityQueue<T>`.

Required public API:

```csharp
public int Count { get; }
public void Enqueue(T item, int priority)
public T Peek()
public T Dequeue()
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- Smaller numeric priority values are dequeued first.
- Items with the same priority must be dequeued in insertion order.
- `Peek` returns the next item without removing it.
- `Peek` and `Dequeue` throw `InvalidOperationException` when the queue is empty.
