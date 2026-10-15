namespace StackProject;

public sealed partial class SimpleStack<T>
{
    private readonly StackStorage<T> storage = new();

    public int Count => storage.Count;

    public void Push(T item) => storage.Add(item);

    public T Pop() => storage.RemoveLast();

    public T Peek() => storage.Last();
}
