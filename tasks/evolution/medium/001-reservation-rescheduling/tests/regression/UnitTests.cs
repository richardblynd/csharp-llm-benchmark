using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Reservations.Models;

[TestClass]
public sealed class RegressionTests
{
    private static DateTime At(int hour) => new(2026, 1, 1, hour, 0, 0);
    private static ReservationDto Reservation(string id, string room, int start = 9, int end = 10)
        => new(id, room, At(start), At(end));

    [TestMethod]
    public async Task existing_post_returns_created_payload_and_location()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        var reservation = Reservation("r1", "room-a");
        var response = await client.PostAsJsonAsync("/reservations", reservation);
        Assert.AreEqual(HttpStatusCode.Created, response.StatusCode);
        Assert.IsTrue(response.Headers.Location!.ToString().EndsWith("/reservations/r1", StringComparison.Ordinal));
        Assert.AreEqual(reservation, await response.Content.ReadFromJsonAsync<ReservationDto>());
        Assert.AreEqual(reservation, await client.GetFromJsonAsync<ReservationDto>("/reservations/r1"));
        var json = await response.Content.ReadAsStringAsync();
        foreach (var field in new[] { "id", "roomId", "start", "end" })
        {
            StringAssert.Contains(json, $"\"{field}\"");
        }
    }

    [TestMethod]
    public async Task existing_validation_rejects_bad_input()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        var invalid = new ReservationDto?[] { null, Reservation(" ", "room-a"), Reservation("r1", " "),
            Reservation("r1", "room-a", 10, 10), Reservation("r1", "room-a", 11, 10) };
        foreach (var reservation in invalid)
        {
            Assert.AreEqual(HttpStatusCode.BadRequest, (await client.PostAsJsonAsync("/reservations", reservation)).StatusCode);
        }
        Assert.AreEqual(0, (await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-a/reservations"))!.Count);
    }

    [TestMethod]
    public async Task existing_duplicate_ids_are_rejected()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        var original = Reservation("same", "room-a");
        await client.PostAsJsonAsync("/reservations", original);
        var response = await client.PostAsJsonAsync("/reservations", Reservation("same", "room-b", 12, 13));
        Assert.AreEqual(HttpStatusCode.Conflict, response.StatusCode);
        Assert.AreEqual(original, await client.GetFromJsonAsync<ReservationDto>("/reservations/same"));
        Assert.AreEqual(0, (await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-b/reservations"))!.Count);
    }

    [TestMethod]
    public async Task existing_conflicts_and_adjacency_are_preserved()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        await client.PostAsJsonAsync("/reservations", Reservation("first", "room-a", 9, 11));
        Assert.AreEqual(HttpStatusCode.Conflict,
            (await client.PostAsJsonAsync("/reservations", Reservation("overlap", "room-a", 10, 12))).StatusCode);
        Assert.AreEqual(HttpStatusCode.Created,
            (await client.PostAsJsonAsync("/reservations", Reservation("adjacent", "room-a", 11, 12))).StatusCode);
        Assert.AreEqual(HttpStatusCode.NotFound, (await client.GetAsync("/reservations/overlap")).StatusCode);
    }

    [TestMethod]
    public async Task existing_room_isolation_and_order_are_preserved()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        await client.PostAsJsonAsync("/reservations", Reservation("late", "room-a", 13, 14));
        await client.PostAsJsonAsync("/reservations", Reservation("early", "room-a"));
        Assert.AreEqual(HttpStatusCode.Created,
            (await client.PostAsJsonAsync("/reservations", Reservation("other", "room-b"))).StatusCode);
        var first = await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-a/reservations");
        CollectionAssert.AreEqual(new[] { "early", "late" }, first!.Select(item => item.Id).ToArray());
        Assert.AreEqual("other", (await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-b/reservations"))!.Single().Id);
    }

    [TestMethod]
    public async Task existing_reads_and_app_instances_are_isolated()
    {
        await using var firstFactory = new WebApplicationFactory<Program>();
        await using var secondFactory = new WebApplicationFactory<Program>();
        using var first = firstFactory.CreateClient();
        using var second = secondFactory.CreateClient();
        Assert.AreEqual(HttpStatusCode.NotFound, (await first.GetAsync("/reservations/absent")).StatusCode);
        Assert.AreEqual(0, (await first.GetFromJsonAsync<List<ReservationDto>>("/rooms/empty/reservations"))!.Count);
        await first.PostAsJsonAsync("/reservations", Reservation("r1", "room-a"));
        Assert.AreEqual(HttpStatusCode.NotFound, (await second.GetAsync("/reservations/r1")).StatusCode);
        Assert.AreEqual(0, (await second.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-a/reservations"))!.Count);
    }

    [TestMethod]
    public async Task existing_concurrent_creates_prevent_double_booking()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        var start = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var attempts = Enumerable.Range(0, 12).Select(async i =>
        {
            await start.Task;
            return await client.PostAsJsonAsync("/reservations", Reservation($"r{i}", "room-a"));
        }).ToArray();
        start.SetResult(true);
        var responses = await Task.WhenAll(attempts);
        Assert.AreEqual(1, responses.Count(response => response.StatusCode == HttpStatusCode.Created));
        Assert.AreEqual(11, responses.Count(response => response.StatusCode == HttpStatusCode.Conflict));
        Assert.AreEqual(1, (await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-a/reservations"))!.Count);
    }
}
