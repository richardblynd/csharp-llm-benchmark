namespace StackProject;

internal sealed class StackStorage<T>
{
    private readonly List<T> items = new();

    public int Count => items.Count;

    public void Add(T item) => items.Add(item);

    public T Last()
    {
        if (items.Count == 0)
        {
            throw new InvalidOperationException("The stack is empty.");
        }

        return items[^1];
    }

    public T RemoveLast()
    {
        var value = Last();
        items.RemoveAt(items.Count - 1);
        return value;
    }
}
