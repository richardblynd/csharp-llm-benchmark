using Catalog.Domain;
using Catalog.Models;
using Microsoft.AspNetCore.Mvc;

namespace Catalog.Controllers;

[ApiController]
public sealed class ProductsController(ProductStore store) : ControllerBase
{
    private static bool Valid(Product? product) => product is not null && product.Id > 0
        && !string.IsNullOrWhiteSpace(product.Name) && !string.IsNullOrWhiteSpace(product.Category) && product.Price >= 0;

    [HttpPost("/products")]
    public IActionResult Create([FromBody] Product? request)
    {
        if (!Valid(request)) return BadRequest();
        return store.Add(request!) ? CreatedAtAction(nameof(Get), new { id = request!.Id }, request) : Conflict();
    }

    [HttpGet("/products/{id:int}")]
    public IActionResult Get(int id)
    {
        var product = store.Find(id);
        return product is null ? NotFound() : Ok(product);
    }

    [HttpGet("/products")]
    public IActionResult List([FromQuery] string? q, [FromQuery] string? category,
        [FromQuery] string? sort, [FromQuery] string? direction)
    {
        sort = string.IsNullOrWhiteSpace(sort) ? "id" : sort.Trim().ToLowerInvariant();
        direction = string.IsNullOrWhiteSpace(direction) ? "asc" : direction.Trim().ToLowerInvariant();
        if (sort is not ("id" or "name" or "price") || direction is not ("asc" or "desc")) return BadRequest();
        IEnumerable<Product> products = store.List();
        if (!string.IsNullOrWhiteSpace(q))
            products = products.Where(product => product.Name.Contains(q.Trim(), StringComparison.OrdinalIgnoreCase));
        if (!string.IsNullOrWhiteSpace(category))
            products = products.Where(product => string.Equals(product.Category, category.Trim(), StringComparison.OrdinalIgnoreCase));
        var descending = direction == "desc";
        products = sort switch
        {
            "name" => (descending ? products.OrderByDescending(product => product.Name, StringComparer.OrdinalIgnoreCase)
                : products.OrderBy(product => product.Name, StringComparer.OrdinalIgnoreCase)).ThenBy(product => product.Id),
            "price" => (descending ? products.OrderByDescending(product => product.Price)
                : products.OrderBy(product => product.Price)).ThenBy(product => product.Id),
            _ => descending ? products.OrderByDescending(product => product.Id) : products.OrderBy(product => product.Id)
        };
        return Ok(products.ToArray());
    }

    [HttpPut("/products/{id:int}")]
    public IActionResult Update(int id, [FromBody] Product? request)
    {
        if (!Valid(request) || request!.Id != id) return BadRequest();
        return store.Update(request) ? Ok(request) : NotFound();
    }

    [HttpDelete("/products/{id:int}")]
    public IActionResult Delete(int id) => store.Remove(id) ? NoContent() : NotFound();
}

