using Catalog.Models;

namespace Catalog.Domain;

public sealed class ProductStore
{
    private readonly object gate = new();
    private readonly Dictionary<int, Product> products = new();
    public bool Add(Product product) { lock (gate) return products.TryAdd(product.Id, product); }
    public Product? Find(int id) { lock (gate) return products.GetValueOrDefault(id); }
    public IReadOnlyList<Product> List() { lock (gate) return products.Values.OrderBy(product => product.Id).ToArray(); }
    public bool Update(Product product)
    {
        lock (gate)
        {
            if (!products.ContainsKey(product.Id)) return false;
            products[product.Id] = product;
            return true;
        }
    }
    public bool Remove(int id) { lock (gate) return products.Remove(id); }
}

