public class SimpleStack<T>
{
    public int Count => 0;
    public void Push(T item) { }
    public T Pop() => throw new InvalidOperationException();
    public T Peek() => throw new InvalidOperationException();
}

public class Solution
{
    public static bool Execute() => true;
}
