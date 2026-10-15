# Catalog
Working ASP.NET Core .NET 8 API with a singleton product store per application.
Build: dotnet build Catalog.csproj --configuration Release.

Product is an immutable record with Id (positive integer), Name, Category and Price
(nonnegative decimal). JSON fields are id, name, category, price.
Strings are stored exactly as supplied; blank names/categories are invalid.

- POST /products: valid new product returns 201, its DTO and Location /products/{id}.
  Duplicate ids return 409. Null/invalid bodies return 400.
- GET /products/{id}: 200 and the DTO, or 404 when absent.
- GET /products: 200 and a DTO array ordered by ascending Id, including [] when empty.
- PUT /products/{id}: body Id must match the route and all fields remain valid.
  Return 200 with the replaced DTO, 404 for a valid unknown id, or 400 for invalid input.
- DELETE /products/{id}: 204 with no body when removed, otherwise 404.
- Update validation does not partially change a product. Reads return snapshots.
  All store operations are synchronized and application instances have separate state.

