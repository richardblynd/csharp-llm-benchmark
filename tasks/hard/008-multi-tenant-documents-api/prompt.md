Write a multi-tenant in-memory documents API with ETag concurrency.

The generated file must be `Controllers/DocumentsController.cs`.

Required behavior:
- Do not use external services, external storage or network calls.
- All code, public identifiers, exception messages and comments must be written in English.
- Use controllers and the `DocumentStore` service registered by `Program.cs`.
- Documents are addressed under `/tenants/{tenantId}/documents`.
- `POST /tenants/{tenantId}/documents` creates a document from `id`, `title` and `content`, returns `201 Created`, and includes an `ETag` response header.
- `GET /tenants/{tenantId}/documents/{id}` returns a document in that tenant and includes the current `ETag`.
- `PUT /tenants/{tenantId}/documents/{id}` updates a document only when the `If-Match` header matches the current ETag.
- A successful update returns `200 OK` and a new `ETag`.
- A stale or incorrect `If-Match` value returns `412 Precondition Failed`.
- Documents with the same id in different tenants must be isolated.
- `GET /tenants/{tenantId}/documents` lists only that tenant's documents in ordinal id order.
- Validate tenant ids, document ids, titles and path/body id consistency; invalid input returns `400 Bad Request`.
- Application state must be isolated per web application factory.
