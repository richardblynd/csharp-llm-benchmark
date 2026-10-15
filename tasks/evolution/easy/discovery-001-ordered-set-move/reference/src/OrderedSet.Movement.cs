namespace Collections;
public sealed partial class OrderedSet<T>
{
    public bool MoveBefore(T item, T anchor) => Move(item, anchor, false);
    public bool MoveAfter(T item, T anchor) => Move(item, anchor, true);
    private bool Move(T item, T anchor, bool after)
    {
        int from = Index(item), target = Index(anchor);
        if (from < 0 || target < 0) return false;
        if (from == target) return true;
        T stored = items[from];
        items.RemoveAt(from);
        if (from < target) target--;
        items.Insert(target + (after ? 1 : 0), stored);
        return true;
    }
}
