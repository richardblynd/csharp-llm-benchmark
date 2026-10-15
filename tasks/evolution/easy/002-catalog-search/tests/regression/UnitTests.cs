using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Catalog.Models;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public sealed class RegressionTests
{
    [TestMethod]
    public async Task old_crud_returns_payloads_and_locations()
    {
        await using var app = new WebApplicationFactory<Program>(); using var client = app.CreateClient();
        var product = new Product(7, " Widget ", " Tools ", 12.50m);
        var response = await client.PostAsJsonAsync("/products", product);
        Assert.AreEqual(HttpStatusCode.Created, response.StatusCode);
        Assert.IsTrue(response.Headers.Location!.ToString().EndsWith("/products/7"));
        Assert.AreEqual(product, await response.Content.ReadFromJsonAsync<Product>());
        Assert.AreEqual(product, await client.GetFromJsonAsync<Product>("/products/7"));
        using var json = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        CollectionAssert.AreEquivalent(new[] { "id", "name", "category", "price" }, json.RootElement.EnumerateObject().Select(p => p.Name).ToArray());
        Assert.AreEqual(HttpStatusCode.NotFound, (await client.GetAsync("/products/99")).StatusCode);
    }

    [TestMethod]
    public async Task old_validation_and_duplicate_ids_are_preserved()
    {
        await using var app = new WebApplicationFactory<Program>(); using var client = app.CreateClient();
        foreach (var product in new[] { new Product(0, "A", "C", 1), new Product(1, " ", "C", 1),
            new Product(1, "A", " ", 1), new Product(1, "A", "C", -1) })
            Assert.AreEqual(HttpStatusCode.BadRequest, (await client.PostAsJsonAsync("/products", product)).StatusCode);
        Assert.AreEqual(HttpStatusCode.BadRequest, (await client.PostAsJsonAsync<Product?>("/products", null)).StatusCode);
        var original = new Product(1, "A", "C", 0);
        Assert.AreEqual(HttpStatusCode.Created, (await client.PostAsJsonAsync("/products", original)).StatusCode);
        Assert.AreEqual(HttpStatusCode.Conflict, (await client.PostAsJsonAsync("/products", original with { Name = "Changed" })).StatusCode);
        Assert.AreEqual(original, await client.GetFromJsonAsync<Product>("/products/1"));
    }

    [TestMethod]
    public async Task old_updates_preserve_routes_and_replace_products()
    {
        await using var app = new WebApplicationFactory<Program>(); using var client = app.CreateClient();
        var original = new Product(1, "A", "C", 1); await client.PostAsJsonAsync("/products", original);
        Assert.AreEqual(HttpStatusCode.BadRequest, (await client.PutAsJsonAsync("/products/1", original with { Id = 2 })).StatusCode);
        Assert.AreEqual(HttpStatusCode.BadRequest, (await client.PutAsJsonAsync("/products/1", original with { Name = " " })).StatusCode);
        Assert.AreEqual(original, await client.GetFromJsonAsync<Product>("/products/1"));
        var updated = new Product(1, "B", "D", 2);
        var response = await client.PutAsJsonAsync("/products/1", updated);
        Assert.AreEqual(HttpStatusCode.OK, response.StatusCode);
        Assert.AreEqual(updated, await response.Content.ReadFromJsonAsync<Product>());
        Assert.AreEqual(updated, await client.GetFromJsonAsync<Product>("/products/1"));
        Assert.AreEqual(HttpStatusCode.NotFound, (await client.PutAsJsonAsync("/products/2", updated with { Id = 2 })).StatusCode);
    }

    [TestMethod]
    public async Task old_deletes_and_default_order_are_preserved()
    {
        await using var app = new WebApplicationFactory<Program>(); using var client = app.CreateClient();
        foreach (var id in new[] { 8, 2, 5 }) await client.PostAsJsonAsync("/products", new Product(id, $"P{id}", "C", id));
        CollectionAssert.AreEqual(new[] { 2, 5, 8 }, (await client.GetFromJsonAsync<Product[]>("/products"))!.Select(p => p.Id).ToArray());
        var response = await client.DeleteAsync("/products/5");
        Assert.AreEqual(HttpStatusCode.NoContent, response.StatusCode);
        Assert.AreEqual("", await response.Content.ReadAsStringAsync());
        Assert.AreEqual(HttpStatusCode.NotFound, (await client.DeleteAsync("/products/5")).StatusCode);
        Assert.AreEqual(HttpStatusCode.NotFound, (await client.GetAsync("/products/5")).StatusCode);
        CollectionAssert.AreEqual(new[] { 2, 8 }, (await client.GetFromJsonAsync<Product[]>("/products"))!.Select(p => p.Id).ToArray());
    }

    [TestMethod]
    public async Task old_application_instances_are_isolated()
    {
        await using var first = new WebApplicationFactory<Program>(); await using var second = new WebApplicationFactory<Program>();
        using var a = first.CreateClient(); using var b = second.CreateClient();
        await a.PostAsJsonAsync("/products", new Product(1, "A", "C", 1));
        Assert.AreEqual(0, (await b.GetFromJsonAsync<Product[]>("/products"))!.Length);
        Assert.AreEqual(HttpStatusCode.NotFound, (await b.GetAsync("/products/1")).StatusCode);
        Assert.AreEqual(1, (await a.GetFromJsonAsync<Product[]>("/products"))!.Length);
    }
}

