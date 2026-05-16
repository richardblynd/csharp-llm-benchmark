using System.Net;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public async Task injects_or_preserves_correlation_id()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();

        var generated = await client.GetAsync("/widgets/alpha");
        var request = new HttpRequestMessage(HttpMethod.Get, "/widgets/beta");
        request.Headers.Add("X-Correlation-ID", "corr-123");
        var preserved = await client.SendAsync(request);

        Assert.IsTrue(generated.Headers.TryGetValues("X-Correlation-ID", out var generatedValues));
        Assert.IsFalse(string.IsNullOrWhiteSpace(generatedValues!.Single()));
        Assert.AreEqual("corr-123", preserved.Headers.GetValues("X-Correlation-ID").Single());
    }

    [TestMethod]
    public void validates_options_on_startup()
    {
        using var factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
        {
            builder.ConfigureServices(services =>
            {
                services.PostConfigure<global::RequestPipelineOptions>(options => options.CorrelationHeaderName = "");
            });
        });

        var exception = Assert.ThrowsException<OptionsValidationException>(() => factory.CreateClient());

        StringAssert.Contains(exception.Message, "Correlation");
    }

    [TestMethod]
    public async Task maps_domain_exceptions_to_status_codes()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();

        var response = await client.GetAsync("/widgets/missing");
        var body = await response.Content.ReadAsStringAsync();

        Assert.AreEqual(HttpStatusCode.NotFound, response.StatusCode);
        StringAssert.Contains(body, "not_found");
    }

    [TestMethod]
    public async Task applies_configurable_policy_per_endpoint()
    {
        await using var factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
        {
            builder.ConfigureServices(services =>
            {
                services.PostConfigure<global::RequestPipelineOptions>(options => options.RoutePolicies["admin"] = "allow");
            });
        });
        var client = factory.CreateClient();

        var denied = await client.GetAsync("/secure");
        var request = new HttpRequestMessage(HttpMethod.Get, "/secure");
        request.Headers.Add("X-Policy", "allow");
        var allowed = await client.SendAsync(request);

        Assert.AreEqual(HttpStatusCode.Forbidden, denied.StatusCode);
        Assert.AreEqual(HttpStatusCode.OK, allowed.StatusCode);
    }

    [TestMethod]
    public void keeps_components_separated_and_testable_via_di()
    {
        using var factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
        {
            builder.ConfigureServices(services =>
            {
                services.PostConfigure<global::RequestPipelineOptions>(options => options.RoutePolicies["admin"] = "secret");
            });
        });
        var evaluator = factory.Services.GetRequiredService<global::IRoutePolicyEvaluator>();
        var context = new DefaultHttpContext();

        Assert.IsFalse(evaluator.IsAllowed(context, "admin"));
        context.Request.Headers["X-Policy"] = "secret";
        Assert.IsTrue(evaluator.IsAllowed(context, "admin"));
    }

    [TestMethod]
    public async Task hides_internal_error_details()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();

        var response = await client.GetAsync("/widgets/boom");
        var body = await response.Content.ReadAsStringAsync();

        Assert.AreEqual(HttpStatusCode.InternalServerError, response.StatusCode);
        Assert.IsFalse(body.Contains("InvalidOperationException", StringComparison.Ordinal));
        Assert.IsFalse(body.Contains("boom", StringComparison.OrdinalIgnoreCase));
        Assert.IsFalse(body.Contains("stack", StringComparison.OrdinalIgnoreCase));
    }
}
