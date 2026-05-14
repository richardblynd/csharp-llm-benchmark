using Microsoft.AspNetCore.Mvc;

[ApiController]
[Route("tenants/{tenantId}/documents")]
public sealed class DocumentsController : ControllerBase
{
    private readonly DocumentStore store;

    public DocumentsController(DocumentStore store)
    {
        this.store = store;
    }

    [HttpPost]
    public IActionResult Create(string tenantId, [FromBody] DocumentRequest? request)
    {
        var validation = ValidateTenantAndDocument(tenantId, request);
        if (validation is not null)
        {
            return BadRequest(new { error = validation });
        }

        var created = store.Create(tenantId.Trim(), request!);
        Response.Headers.ETag = created.ETag;
        return CreatedAtAction(nameof(GetById), new { tenantId = tenantId.Trim(), id = created.Document.Id }, created.Document);
    }

    [HttpGet("{id}")]
    public IActionResult GetById(string tenantId, string id)
    {
        if (string.IsNullOrWhiteSpace(tenantId) || string.IsNullOrWhiteSpace(id))
        {
            return BadRequest(new { error = "Tenant id and document id are required." });
        }

        var found = store.Find(tenantId.Trim(), id.Trim());
        if (found is null)
        {
            return NotFound();
        }

        Response.Headers.ETag = found.ETag;
        return Ok(found.Document);
    }

    [HttpPut("{id}")]
    public IActionResult Update(string tenantId, string id, [FromBody] DocumentRequest? request)
    {
        var validation = ValidateTenantAndDocument(tenantId, request);
        if (validation is not null)
        {
            return BadRequest(new { error = validation });
        }

        if (!string.Equals(id.Trim(), request!.Id.Trim(), StringComparison.Ordinal))
        {
            return BadRequest(new { error = "Path id and body id must match." });
        }

        if (!Request.Headers.TryGetValue("If-Match", out var etag) || string.IsNullOrWhiteSpace(etag.ToString()))
        {
            return StatusCode(StatusCodes.Status412PreconditionFailed);
        }

        var updated = store.Update(tenantId.Trim(), id.Trim(), request, etag.ToString());
        if (updated.NotFound)
        {
            return NotFound();
        }

        if (updated.PreconditionFailed)
        {
            return StatusCode(StatusCodes.Status412PreconditionFailed);
        }

        Response.Headers.ETag = updated.Document!.ETag;
        return Ok(updated.Document.Document);
    }

    [HttpGet]
    public IReadOnlyList<DocumentResponse> List(string tenantId)
    {
        return store.List(tenantId.Trim());
    }

    private static string? ValidateTenantAndDocument(string tenantId, DocumentRequest? request)
    {
        if (string.IsNullOrWhiteSpace(tenantId))
        {
            return "Tenant id is required.";
        }

        if (request is null)
        {
            return "Request body is required.";
        }

        if (string.IsNullOrWhiteSpace(request.Id))
        {
            return "Document id is required.";
        }

        if (string.IsNullOrWhiteSpace(request.Title))
        {
            return "Title is required.";
        }

        return null;
    }
}

public sealed record DocumentRequest(string Id, string Title, string Content);
public sealed record DocumentResponse(string Id, string Title, string Content, long Version);
public sealed record StoredDocument(DocumentResponse Document, string ETag);
public sealed record UpdateDocumentResult(bool NotFound, bool PreconditionFailed, StoredDocument? Document);

public sealed class DocumentStore
{
    private readonly object gate = new();
    private readonly Dictionary<string, Dictionary<string, DocumentResponse>> documents = new(StringComparer.Ordinal);

    public StoredDocument Create(string tenantId, DocumentRequest request)
    {
        lock (gate)
        {
            var tenant = GetTenant(tenantId);
            var document = new DocumentResponse(request.Id.Trim(), request.Title, request.Content, 1);
            tenant[document.Id] = document;
            return WithEtag(document);
        }
    }

    public StoredDocument? Find(string tenantId, string id)
    {
        lock (gate)
        {
            return documents.TryGetValue(tenantId, out var tenant) && tenant.TryGetValue(id, out var document)
                ? WithEtag(document)
                : null;
        }
    }

    public UpdateDocumentResult Update(string tenantId, string id, DocumentRequest request, string ifMatch)
    {
        lock (gate)
        {
            if (!documents.TryGetValue(tenantId, out var tenant) || !tenant.TryGetValue(id, out var current))
            {
                return new UpdateDocumentResult(true, false, null);
            }

            if (!string.Equals(ToEtag(current.Version), ifMatch.Trim(), StringComparison.Ordinal))
            {
                return new UpdateDocumentResult(false, true, null);
            }

            var updated = current with
            {
                Title = request.Title,
                Content = request.Content,
                Version = current.Version + 1
            };
            tenant[id] = updated;
            return new UpdateDocumentResult(false, false, WithEtag(updated));
        }
    }

    public IReadOnlyList<DocumentResponse> List(string tenantId)
    {
        lock (gate)
        {
            return documents.TryGetValue(tenantId, out var tenant)
                ? tenant.Values.OrderBy(document => document.Id, StringComparer.Ordinal).ToArray()
                : Array.Empty<DocumentResponse>();
        }
    }

    private Dictionary<string, DocumentResponse> GetTenant(string tenantId)
    {
        if (!documents.TryGetValue(tenantId, out var tenant))
        {
            tenant = new Dictionary<string, DocumentResponse>(StringComparer.Ordinal);
            documents[tenantId] = tenant;
        }

        return tenant;
    }

    private static StoredDocument WithEtag(DocumentResponse document) => new(document, ToEtag(document.Version));

    private static string ToEtag(long version) => $"\"{version}\"";
}
