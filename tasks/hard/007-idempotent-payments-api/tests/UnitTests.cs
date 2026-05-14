using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    private sealed record PaymentRequest(decimal Amount, string Currency, string CustomerId);
    private sealed record PaymentResponse(string Id, decimal Amount, string Currency, string CustomerId, string Status);

    [TestMethod]
    public async Task creates_valid_payment_with_created_response()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();

        var response = await PostPayment(client, "key-1", new PaymentRequest(12.50m, "USD", "customer-1"));
        var payment = await response.Content.ReadFromJsonAsync<PaymentResponse>();

        Assert.AreEqual(HttpStatusCode.Created, response.StatusCode);
        Assert.IsNotNull(response.Headers.Location);
        Assert.IsNotNull(payment);
        Assert.AreEqual(12.50m, payment.Amount);
        Assert.AreEqual("USD", payment.Currency);
        Assert.AreEqual("customer-1", payment.CustomerId);
        Assert.AreEqual("Authorized", payment.Status);
    }

    [TestMethod]
    public async Task rejects_invalid_payload_with_bad_request()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();

        var missingKey = await client.PostAsJsonAsync("/payments", new PaymentRequest(10m, "USD", "customer-1"));
        var negativeAmount = await PostPayment(client, "key-2", new PaymentRequest(0m, "USD", "customer-1"));
        var badCurrency = await PostPayment(client, "key-3", new PaymentRequest(10m, "US", "customer-1"));
        var emptyCustomer = await PostPayment(client, "key-4", new PaymentRequest(10m, "USD", ""));

        Assert.AreEqual(HttpStatusCode.BadRequest, missingKey.StatusCode);
        Assert.AreEqual(HttpStatusCode.BadRequest, negativeAmount.StatusCode);
        Assert.AreEqual(HttpStatusCode.BadRequest, badCurrency.StatusCode);
        Assert.AreEqual(HttpStatusCode.BadRequest, emptyCustomer.StatusCode);
    }

    [TestMethod]
    public async Task reuses_response_for_same_key_and_payload()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        var request = new PaymentRequest(15m, "EUR", "customer-2");

        var first = await PostPayment(client, "repeat-key", request);
        var second = await PostPayment(client, "repeat-key", request);
        var firstPayment = await first.Content.ReadFromJsonAsync<PaymentResponse>();
        var secondPayment = await second.Content.ReadFromJsonAsync<PaymentResponse>();

        Assert.AreEqual(HttpStatusCode.Created, first.StatusCode);
        Assert.AreEqual(first.StatusCode, second.StatusCode);
        Assert.AreEqual(firstPayment, secondPayment);
    }

    [TestMethod]
    public async Task rejects_same_key_with_different_payload()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();

        await PostPayment(client, "conflict-key", new PaymentRequest(15m, "EUR", "customer-2"));
        var conflict = await PostPayment(client, "conflict-key", new PaymentRequest(20m, "EUR", "customer-2"));

        Assert.AreEqual(HttpStatusCode.Conflict, conflict.StatusCode);
    }

    [TestMethod]
    public async Task prevents_duplicate_charges_under_concurrency()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        var request = new PaymentRequest(25m, "BRL", "customer-3");

        var responses = await Task.WhenAll(Enumerable.Range(0, 16).Select(_ => PostPayment(client, "concurrent-key", request)));
        var payments = await Task.WhenAll(responses.Select(response => response.Content.ReadFromJsonAsync<PaymentResponse>()));
        var list = await client.GetFromJsonAsync<List<PaymentResponse>>("/payments");

        Assert.IsTrue(responses.All(response => response.StatusCode == HttpStatusCode.Created));
        Assert.AreEqual(1, payments.Select(payment => payment!.Id).Distinct(StringComparer.Ordinal).Count());
        Assert.AreEqual(1, list!.Count);
    }

    [TestMethod]
    public async Task gets_payment_by_id()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        var created = await PostPayment(client, "lookup-key", new PaymentRequest(30m, "USD", "customer-4"));
        var payment = await created.Content.ReadFromJsonAsync<PaymentResponse>();

        var found = await client.GetAsync($"/payments/{payment!.Id}");
        var missing = await client.GetAsync("/payments/missing");

        Assert.AreEqual(HttpStatusCode.OK, found.StatusCode);
        Assert.AreEqual(HttpStatusCode.NotFound, missing.StatusCode);
    }

    [TestMethod]
    public async Task isolates_state_between_factories()
    {
        await using var firstFactory = new WebApplicationFactory<Program>();
        await using var secondFactory = new WebApplicationFactory<Program>();

        await PostPayment(firstFactory.CreateClient(), "isolated-key", new PaymentRequest(8m, "USD", "customer-5"));
        var secondList = await secondFactory.CreateClient().GetFromJsonAsync<List<PaymentResponse>>("/payments");

        Assert.AreEqual(0, secondList!.Count);
    }

    private static Task<HttpResponseMessage> PostPayment(HttpClient client, string key, PaymentRequest request)
    {
        var message = new HttpRequestMessage(HttpMethod.Post, "/payments")
        {
            Content = JsonContent.Create(request)
        };
        message.Headers.Add("Idempotency-Key", key);
        return client.SendAsync(message);
    }
}
