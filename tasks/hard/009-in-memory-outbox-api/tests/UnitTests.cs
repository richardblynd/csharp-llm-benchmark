using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public async Task endpoint_records_command_and_outbox_atomically()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();

        var created = await client.PostAsJsonAsync("/commands", new global::CommandRequest("cmd-1", "ship", "payload"));
        var status = await created.Content.ReadFromJsonAsync<global::CommandStatus>();
        var outbox = await client.GetAsync($"/outbox/{status!.EventId}");

        Assert.AreEqual(HttpStatusCode.Created, created.StatusCode);
        Assert.AreEqual("cmd-1", status.CommandId);
        Assert.AreEqual("Accepted", status.Status);
        Assert.IsFalse(string.IsNullOrWhiteSpace(status.EventId));
        Assert.AreEqual(HttpStatusCode.OK, outbox.StatusCode);
    }

    [TestMethod]
    public async Task worker_publishes_pending_events()
    {
        var store = new global::OutboxStore();
        var publisher = new FakePublisher();
        var worker = new global::OutboxWorker(store, publisher);
        var status = store.Enqueue(new global::CommandRequest("cmd-2", "bill", "payload"));

        var published = await worker.PublishPendingAsync();
        var item = store.FindEvent(status.EventId);

        Assert.AreEqual(1, published);
        Assert.AreEqual(1, publisher.Published.Count);
        Assert.AreEqual("Published", item!.Status);
    }

    [TestMethod]
    public async Task avoids_publishing_successful_event_twice()
    {
        var store = new global::OutboxStore();
        var publisher = new FakePublisher();
        var worker = new global::OutboxWorker(store, publisher);
        store.Enqueue(new global::CommandRequest("cmd-3", "bill", "payload"));

        Assert.AreEqual(1, await worker.PublishPendingAsync());
        Assert.AreEqual(0, await worker.PublishPendingAsync());

        Assert.AreEqual(1, publisher.Published.Count);
    }

    [TestMethod]
    public async Task retries_after_temporary_failure()
    {
        var store = new global::OutboxStore();
        var publisher = new FakePublisher { FailuresBeforeSuccess = 1 };
        var worker = new global::OutboxWorker(store, publisher);
        var status = store.Enqueue(new global::CommandRequest("cmd-4", "bill", "payload"));

        Assert.AreEqual(0, await worker.PublishPendingAsync());
        Assert.AreEqual("Pending", store.FindEvent(status.EventId)!.Status);
        Assert.AreEqual(1, await worker.PublishPendingAsync());

        Assert.AreEqual(2, publisher.Attempts);
        Assert.AreEqual("Published", store.FindEvent(status.EventId)!.Status);
    }

    [TestMethod]
    public void allows_replacing_publisher_in_tests()
    {
        var fake = new FakePublisher();
        using var factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
        {
            builder.ConfigureServices(services =>
            {
                services.RemoveAll<global::IEventPublisher>();
                services.AddSingleton<global::IEventPublisher>(fake);
            });
        });

        var resolved = factory.Services.GetRequiredService<global::IEventPublisher>();

        Assert.AreSame(fake, resolved);
    }

    [TestMethod]
    public async Task respects_worker_cancellation()
    {
        var store = new global::OutboxStore();
        var publisher = new FakePublisher();
        var worker = new global::OutboxWorker(store, publisher);
        store.Enqueue(new global::CommandRequest("cmd-5", "bill", "payload"));
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();

        await Assert.ThrowsExceptionAsync<OperationCanceledException>(() => worker.PublishPendingAsync(cancellation.Token));

        Assert.AreEqual(0, publisher.Published.Count);
    }

    [TestMethod]
    public async Task exposes_command_and_event_status()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        var created = await client.PostAsJsonAsync("/commands", new global::CommandRequest("cmd-6", "ship", "payload"));
        var status = await created.Content.ReadFromJsonAsync<global::CommandStatus>();

        var command = await client.GetFromJsonAsync<global::CommandStatus>($"/commands/{status!.CommandId}");
        var outbox = await client.GetFromJsonAsync<global::OutboxEvent>($"/outbox/{status.EventId}");

        Assert.AreEqual("cmd-6", command!.CommandId);
        Assert.AreEqual(status.EventId, command.EventId);
        Assert.AreEqual("cmd-6", outbox!.CommandId);
        Assert.IsTrue(outbox.Status is "Pending" or "Published");
    }

    private sealed class FakePublisher : global::IEventPublisher
    {
        public int FailuresBeforeSuccess { get; set; }
        public int Attempts { get; private set; }
        public List<global::OutboxEvent> Published { get; } = new();

        public Task PublishAsync(global::OutboxEvent item, CancellationToken cancellationToken)
        {
            Attempts++;
            if (Attempts <= FailuresBeforeSuccess)
            {
                throw new InvalidOperationException("Temporary failure.");
            }

            Published.Add(item);
            return Task.CompletedTask;
        }
    }
}
