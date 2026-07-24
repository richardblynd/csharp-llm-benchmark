public class ListOperationsResult
{
    public int Sum { get; set; }
    public IReadOnlyList<int> Evens { get; set; } = Array.Empty<int>();
}

public class Solution
{
    public static ListOperationsResult Execute(IReadOnlyList<int> numbers) => new();
}
