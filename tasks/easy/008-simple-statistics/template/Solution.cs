public class StatisticsResult
{
    public int Count { get; set; }
    public double Average { get; set; }
    public double Min { get; set; }
    public double Max { get; set; }
}

public class Solution
{
    public static StatisticsResult Execute(IReadOnlyList<double> values) => new();
}
