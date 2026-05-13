public class Product
{
    public string Name { get; set; } = string.Empty;
    public decimal Price { get; set; }
    public decimal DiscountPercentage { get; set; }
}

public class Solution
{
    public static decimal Execute(Product product) => product.Price;
}
