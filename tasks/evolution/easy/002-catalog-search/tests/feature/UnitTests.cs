using System.Net;
using System.Net.Http.Json;
using Catalog.Models;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public sealed class FeatureTests
{
    private static async Task Seed(HttpClient client)
    {
        foreach (var product in new[] {
            new Product(1, "zebra tea", "Drinks", 9), new Product(2, "Apple juice", "Drinks", 5),
            new Product(3, "apple pie", "Food", 5), new Product(4, "BANANA", "Food", 3) })
            (await client.PostAsJsonAsync("/products", product)).EnsureSuccessStatusCode();
    }
    private static async Task<int[]> Ids(HttpClient client, string query)
        => (await client.GetFromJsonAsync<Product[]>("/products" + query))!.Select(p => p.Id).ToArray();

    [TestMethod]
    public async Task query_filters_names()
    {
        await using var app = new WebApplicationFactory<Program>(); using var client = app.CreateClient(); await Seed(client);
        CollectionAssert.AreEqual(new[] { 2, 3 }, await Ids(client, "?q=%20APPle%20"));
        CollectionAssert.AreEqual(new[] { 1 }, await Ids(client, "?q=TEA"));
        Assert.AreEqual(0, (await Ids(client, "?q=absent")).Length);
        Assert.AreEqual(4, (await Ids(client, "?q=%20%20")).Length);
        CollectionAssert.AreEqual(new[] { 1, 2, 3, 4 }, await Ids(client, ""));
    }

    [TestMethod]
    public async Task query_combines_category_and_name()
    {
        await using var app = new WebApplicationFactory<Program>(); using var client = app.CreateClient(); await Seed(client);
        CollectionAssert.AreEqual(new[] { 3, 4 }, await Ids(client, "?category=%20food%20"));
        CollectionAssert.AreEqual(new[] { 3 }, await Ids(client, "?category=FOOD&q=apple"));
        CollectionAssert.AreEqual(new[] { 2 }, await Ids(client, "?category=drinks&q=JUICE"));
        Assert.AreEqual(0, (await Ids(client, "?category=Drink")).Length);
    }

    [TestMethod]
    public async Task query_orders_names_and_ties()
    {
        await using var app = new WebApplicationFactory<Program>(); using var client = app.CreateClient(); await Seed(client);
        await client.PostAsJsonAsync("/products", new Product(5, "APPLE juice", "Drinks", 8));
        CollectionAssert.AreEqual(new[] { 2, 5, 3, 4, 1 }, await Ids(client, "?sort=%20NAME%20&direction=%20asc%20"));
        CollectionAssert.AreEqual(new[] { 1, 4, 3, 2, 5 }, await Ids(client, "?sort=name&direction=DESC"));
        CollectionAssert.AreEqual(new[] { 1, 2, 3, 4, 5 }, await Ids(client, ""));
    }

    [TestMethod]
    public async Task query_orders_prices_and_ties()
    {
        await using var app = new WebApplicationFactory<Program>(); using var client = app.CreateClient(); await Seed(client);
        CollectionAssert.AreEqual(new[] { 4, 2, 3, 1 }, await Ids(client, "?sort=price"));
        CollectionAssert.AreEqual(new[] { 1, 2, 3, 4 }, await Ids(client, "?sort=price&direction=desc"));
        CollectionAssert.AreEqual(new[] { 4, 3, 2, 1 }, await Ids(client, "?sort=id&direction=desc"));
    }

    [TestMethod]
    public async Task query_rejects_invalid_sorting()
    {
        await using var app = new WebApplicationFactory<Program>(); using var client = app.CreateClient();
        foreach (var query in new[] { "?sort=rating", "?direction=sideways", "?sort=price&direction=other" })
            Assert.AreEqual(HttpStatusCode.BadRequest, (await client.GetAsync("/products" + query)).StatusCode);
        await Seed(client);
        Assert.AreEqual(HttpStatusCode.BadRequest, (await client.GetAsync("/products?sort=rating")).StatusCode);
        Assert.AreEqual(HttpStatusCode.OK, (await client.GetAsync("/products?sort=%20&direction=%20")).StatusCode);
    }

    [TestMethod]
    public async Task query_reflects_crud_without_mutating_state()
    {
        await using var app = new WebApplicationFactory<Program>(); using var client = app.CreateClient(); await Seed(client);
        var updated = new Product(2, "Bread", "Food", 1);
        (await client.PutAsJsonAsync("/products/2", updated)).EnsureSuccessStatusCode();
        (await client.DeleteAsync("/products/3")).EnsureSuccessStatusCode();
        (await client.PostAsJsonAsync("/products", new Product(5, "Apple tart", "Food", 7))).EnsureSuccessStatusCode();
        CollectionAssert.AreEqual(new[] { 5 }, await Ids(client, "?q=apple&category=food&sort=price&direction=desc"));
        Assert.AreEqual(updated, await client.GetFromJsonAsync<Product>("/products/2"));
        CollectionAssert.AreEqual(new[] { 1, 2, 4, 5 }, await Ids(client, ""));
    }
}

