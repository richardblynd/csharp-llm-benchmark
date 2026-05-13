using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public async Task get_products_returns_list()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();

        var response = await client.GetAsync("/products");

        response.EnsureSuccessStatusCode();
        var products = await response.Content.ReadFromJsonAsync<List<ProductDto>>();
        Assert.IsNotNull(products);
        Assert.AreEqual(0, products.Count);
    }

    [TestMethod]
    public async Task get_product_by_id_returns_200_or_404()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        await client.PostAsJsonAsync("/products", new ProductDto("p1", "Notebook", 12.5m));

        var found = await client.GetAsync("/products/p1");
        var missing = await client.GetAsync("/products/missing");

        Assert.AreEqual(HttpStatusCode.OK, found.StatusCode);
        Assert.AreEqual(HttpStatusCode.NotFound, missing.StatusCode);
    }

    [TestMethod]
    public async Task post_products_creates_with_201_and_validates_input()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();

        var created = await client.PostAsJsonAsync("/products", new ProductDto("p1", "Pen", 2.5m));
        var invalid = await client.PostAsJsonAsync("/products", new ProductDto("p2", "", -1m));
        var duplicate = await client.PostAsJsonAsync("/products", new ProductDto("p1", "Other", 3m));

        Assert.AreEqual(HttpStatusCode.Created, created.StatusCode);
        Assert.IsNotNull(created.Headers.Location);
        Assert.AreEqual(HttpStatusCode.BadRequest, invalid.StatusCode);
        Assert.AreEqual(HttpStatusCode.BadRequest, duplicate.StatusCode);
    }

    [TestMethod]
    public async Task put_products_updates_or_returns_404()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        await client.PostAsJsonAsync("/products", new ProductDto("p1", "Old", 1m));

        var updated = await client.PutAsJsonAsync("/products/p1", new ProductDto("ignored", "New", 5m));
        var missing = await client.PutAsJsonAsync("/products/missing", new ProductDto("missing", "Nope", 1m));
        var product = await client.GetFromJsonAsync<ProductDto>("/products/p1");

        Assert.AreEqual(HttpStatusCode.OK, updated.StatusCode);
        Assert.AreEqual(HttpStatusCode.NotFound, missing.StatusCode);
        Assert.AreEqual("New", product!.Name);
        Assert.AreEqual(5m, product.Price);
    }

    [TestMethod]
    public async Task keeps_state_in_memory_during_integration_test()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        await client.PostAsJsonAsync("/products", new ProductDto("p1", "Stored", 1m));

        var products = await client.GetFromJsonAsync<List<ProductDto>>("/products");

        Assert.AreEqual(1, products!.Count);
    }
}
