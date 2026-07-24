Create the generated file `Controllers/ProductsController.cs` for an ASP.NET Core API.

Required public surface:
- A controller that handles products.
- A public `ProductStore` service registered by the template.
- A public `ProductDto` model or record with `Id`, `Name` and `Price`.

Routes:
- `GET /products` returns all products as JSON.
- `GET /products/{id}` returns `200` with a product or `404`.
- `POST /products` creates a product and returns `201` with a `Location` header.
- `PUT /products/{id}` updates an existing product and returns `200`, or `404` if it does not exist.

Suggested shape:

```csharp
public sealed record ProductDto(string Id, string Name, decimal Price);
```

Rules:
- All code, public identifiers, exception messages and comments must be written in English.
- Product JSON fields are `id`, `name` and `price`.
- Reject blank names and negative prices with `400`.
- Reject duplicate ids on create with `400`.
- Keep data in memory for the lifetime of the app instance.
