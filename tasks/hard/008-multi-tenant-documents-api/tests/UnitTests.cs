using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    private sealed record DocumentRequest(string Id, string Title, string Content);
    private sealed record DocumentResponse(string Id, string Title, string Content, long Version);

    [TestMethod]
    public async Task creates_and_reads_document_within_tenant()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();

        var created = await client.PostAsJsonAsync("/tenants/t1/documents", new DocumentRequest("doc-1", "Title", "Body"));
        var found = await client.GetAsync("/tenants/t1/documents/doc-1");
        var document = await found.Content.ReadFromJsonAsync<DocumentResponse>();

        Assert.AreEqual(HttpStatusCode.Created, created.StatusCode);
        Assert.AreEqual(HttpStatusCode.OK, found.StatusCode);
        Assert.AreEqual("doc-1", document!.Id);
        Assert.AreEqual("Title", document.Title);
    }

    [TestMethod]
    public async Task isolates_documents_between_tenants()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();

        await client.PostAsJsonAsync("/tenants/t1/documents", new DocumentRequest("shared", "Tenant One", "A"));
        var otherTenant = await client.GetAsync("/tenants/t2/documents/shared");
        await client.PostAsJsonAsync("/tenants/t2/documents", new DocumentRequest("shared", "Tenant Two", "B"));
        var first = await client.GetFromJsonAsync<DocumentResponse>("/tenants/t1/documents/shared");
        var second = await client.GetFromJsonAsync<DocumentResponse>("/tenants/t2/documents/shared");

        Assert.AreEqual(HttpStatusCode.NotFound, otherTenant.StatusCode);
        Assert.AreEqual("Tenant One", first!.Title);
        Assert.AreEqual("Tenant Two", second!.Title);
    }

    [TestMethod]
    public async Task returns_etag_on_create_and_get()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();

        var created = await client.PostAsJsonAsync("/tenants/t1/documents", new DocumentRequest("doc-1", "Title", "Body"));
        var found = await client.GetAsync("/tenants/t1/documents/doc-1");

        Assert.IsNotNull(created.Headers.ETag);
        Assert.IsNotNull(found.Headers.ETag);
        Assert.AreEqual(created.Headers.ETag!.Tag, found.Headers.ETag!.Tag);
    }

    [TestMethod]
    public async Task updates_with_matching_etag()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        var created = await client.PostAsJsonAsync("/tenants/t1/documents", new DocumentRequest("doc-1", "Old", "Body"));

        var updated = await PutDocument(client, "/tenants/t1/documents/doc-1", new DocumentRequest("doc-1", "New", "Changed"), created.Headers.ETag!.Tag);
        var document = await updated.Content.ReadFromJsonAsync<DocumentResponse>();

        Assert.AreEqual(HttpStatusCode.OK, updated.StatusCode);
        Assert.AreEqual("New", document!.Title);
        Assert.AreNotEqual(created.Headers.ETag!.Tag, updated.Headers.ETag!.Tag);
    }

    [TestMethod]
    public async Task rejects_stale_etag_with_precondition_failed()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        var created = await client.PostAsJsonAsync("/tenants/t1/documents", new DocumentRequest("doc-1", "Old", "Body"));
        var stale = created.Headers.ETag!.Tag;
        await PutDocument(client, "/tenants/t1/documents/doc-1", new DocumentRequest("doc-1", "New", "Changed"), stale);

        var rejected = await PutDocument(client, "/tenants/t1/documents/doc-1", new DocumentRequest("doc-1", "Other", "Changed"), stale);

        Assert.AreEqual(HttpStatusCode.PreconditionFailed, rejected.StatusCode);
    }

    [TestMethod]
    public async Task validates_input_and_inconsistent_ids()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        await client.PostAsJsonAsync("/tenants/t1/documents", new DocumentRequest("doc-1", "Title", "Body"));
        var current = await client.GetAsync("/tenants/t1/documents/doc-1");

        var invalidCreate = await client.PostAsJsonAsync("/tenants/t1/documents", new DocumentRequest("", "", "Body"));
        var inconsistentUpdate = await PutDocument(client, "/tenants/t1/documents/doc-1", new DocumentRequest("other", "Title", "Body"), current.Headers.ETag!.Tag);

        Assert.AreEqual(HttpStatusCode.BadRequest, invalidCreate.StatusCode);
        Assert.AreEqual(HttpStatusCode.BadRequest, inconsistentUpdate.StatusCode);
    }

    [TestMethod]
    public async Task lists_documents_for_tenant_in_deterministic_order()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        await client.PostAsJsonAsync("/tenants/t1/documents", new DocumentRequest("b", "Second", "B"));
        await client.PostAsJsonAsync("/tenants/t1/documents", new DocumentRequest("a", "First", "A"));
        await client.PostAsJsonAsync("/tenants/t2/documents", new DocumentRequest("c", "Other", "C"));

        var documents = await client.GetFromJsonAsync<List<DocumentResponse>>("/tenants/t1/documents");

        CollectionAssert.AreEqual(new[] { "a", "b" }, documents!.Select(document => document.Id).ToArray());
    }

    private static Task<HttpResponseMessage> PutDocument(HttpClient client, string path, DocumentRequest request, string etag)
    {
        var message = new HttpRequestMessage(HttpMethod.Put, path)
        {
            Content = JsonContent.Create(request)
        };
        message.Headers.TryAddWithoutValidation("If-Match", etag);
        return client.SendAsync(message);
    }
}
