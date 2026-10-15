namespace StackProject;

public sealed partial class SimpleStack<T>
{
    public bool TryPop(out T value)
    {
        if (Count == 0)
        {
            value = default!;
            return false;
        }

        value = Pop();
        return true;
    }

    public bool TryPeek(out T value)
    {
        if (Count == 0)
        {
            value = default!;
            return false;
        }

        value = Peek();
        return true;
    }
}
