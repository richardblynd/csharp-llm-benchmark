public class Item
{
    public string Category { get; set; } = string.Empty;
    public decimal Amount { get; set; }
}

public class Solution
{
    public static Dictionary<string, decimal> Execute(IEnumerable<Item> items) => new();
}
