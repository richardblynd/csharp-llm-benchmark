public class Item
{
    public string Category { get; set; } = string.Empty;
    public decimal Amount { get; set; }
}

public class Solution
{
    public static Dictionary<string, int> CountWords(string text) => new();
    public static Dictionary<string, decimal> AggregateByCategory(IEnumerable<Item> items) => new();
    public static bool Execute() => true;
}
