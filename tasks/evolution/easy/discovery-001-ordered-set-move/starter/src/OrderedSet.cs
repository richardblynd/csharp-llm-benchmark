namespace Collections;

public sealed partial class OrderedSet<T>
{
    private readonly List<T> items = new();
    private readonly IEqualityComparer<T> comparer;
    public OrderedSet(IEqualityComparer<T>? comparer = null) => this.comparer = comparer ?? EqualityComparer<T>.Default;
    public int Count => items.Count;
    public IReadOnlyList<T> Items => items.ToArray();
    private int Index(T item) => items.FindIndex(value => comparer.Equals(value, item));
    public bool Contains(T item) => Index(item) >= 0;
    public bool Add(T item)
    {
        if (Contains(item)) return false;
        items.Add(item);
        return true;
    }
    public bool Remove(T item)
    {
        var index = Index(item);
        if (index < 0) return false;
        items.RemoveAt(index);
        return true;
    }
}
