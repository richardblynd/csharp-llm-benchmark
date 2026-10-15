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
    public IActionResult List() => Ok(store.List());

    [HttpPut("/products/{id:int}")]
    public IActionResult Update(int id, [FromBody] Product? request)
    {
        if (!Valid(request) || request!.Id != id) return BadRequest();
        return store.Update(request) ? Ok(request) : NotFound();
    }

    [HttpDelete("/products/{id:int}")]
    public IActionResult Delete(int id) => store.Remove(id) ? NoContent() : NotFound();
}

