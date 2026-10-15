using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Reservations.Models;

[TestClass]
public sealed class FeatureTests
{
    private static DateTime At(int hour) => new(2026, 1, 1, hour, 0, 0);
    private static ReservationDto Reservation(string id, string room, int start = 9, int end = 10)
        => new(id, room, At(start), At(end));
    private static Task<HttpResponseMessage> Change(HttpClient client, string id, string room, int start, int end)
        => client.PutAsJsonAsync($"/reservations/{id}/schedule", new { roomId = room, start = At(start), end = At(end) });

    [TestMethod]
    public async Task reschedule_updates_interval_and_preserves_id()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        await client.PostAsJsonAsync("/reservations", Reservation("r1", "room-a"));
        var response = await Change(client, "r1", "room-a", 13, 14);
        Assert.AreEqual(HttpStatusCode.OK, response.StatusCode);
        var expected = Reservation("r1", "room-a", 13, 14);
        Assert.AreEqual(expected, await response.Content.ReadFromJsonAsync<ReservationDto>());
        Assert.AreEqual(expected, await client.GetFromJsonAsync<ReservationDto>("/reservations/r1"));
        Assert.AreEqual(expected, (await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-a/reservations"))!.Single());
        Assert.AreEqual(HttpStatusCode.Created,
            (await client.PostAsJsonAsync("/reservations", Reservation("replacement", "room-a"))).StatusCode);
        Assert.AreEqual(HttpStatusCode.Conflict,
            (await client.PostAsJsonAsync("/reservations", Reservation("collision", "room-a", 13, 14))).StatusCode);
    }

    [TestMethod]
    public async Task reschedule_moves_rooms_and_frees_old_slot()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        await client.PostAsJsonAsync("/reservations", Reservation("r1", "room-a"));
        await client.PostAsJsonAsync("/reservations", Reservation("later", "room-b", 13, 14));
        Assert.AreEqual(HttpStatusCode.OK, (await Change(client, "r1", "room-b", 11, 12)).StatusCode);
        Assert.AreEqual(0, (await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-a/reservations"))!.Count);
        var moved = await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-b/reservations");
        CollectionAssert.AreEqual(new[] { "r1", "later" }, moved!.Select(item => item.Id).ToArray());
        Assert.AreEqual(Reservation("r1", "room-b", 11, 12), moved[0]);
        Assert.AreEqual(HttpStatusCode.Created,
            (await client.PostAsJsonAsync("/reservations", Reservation("new", "room-a"))).StatusCode);
        Assert.AreEqual(HttpStatusCode.Conflict,
            (await client.PostAsJsonAsync("/reservations", Reservation("busy", "room-b", 11, 12))).StatusCode);
    }

    [TestMethod]
    public async Task conflicting_reschedule_preserves_original()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        var original = Reservation("r1", "room-a");
        var other = Reservation("r2", "room-b", 13, 15);
        await client.PostAsJsonAsync("/reservations", original);
        await client.PostAsJsonAsync("/reservations", other);
        Assert.AreEqual(HttpStatusCode.Conflict, (await Change(client, "r1", "room-b", 14, 16)).StatusCode);
        Assert.AreEqual(original, await client.GetFromJsonAsync<ReservationDto>("/reservations/r1"));
        Assert.AreEqual(other, await client.GetFromJsonAsync<ReservationDto>("/reservations/r2"));
        Assert.AreEqual(original, (await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-a/reservations"))!.Single());
        Assert.AreEqual(other, (await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-b/reservations"))!.Single());
        Assert.AreEqual(HttpStatusCode.Conflict,
            (await client.PostAsJsonAsync("/reservations", Reservation("old-slot", "room-a"))).StatusCode);
    }

    [TestMethod]
    public async Task invalid_reschedule_preserves_original()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        var original = Reservation("r1", "room-a");
        await client.PostAsJsonAsync("/reservations", original);
        foreach (var change in new[] { (Room: " ", Start: 11, End: 12), (Room: "room-b", Start: 12, End: 12),
                                      (Room: "room-b", Start: 13, End: 12) })
        {
            Assert.AreEqual(HttpStatusCode.BadRequest, (await Change(client, "r1", change.Room, change.Start, change.End)).StatusCode);
            Assert.AreEqual(original, await client.GetFromJsonAsync<ReservationDto>("/reservations/r1"));
        }
        Assert.AreEqual(HttpStatusCode.BadRequest,
            (await client.PutAsJsonAsync<object?>("/reservations/r1/schedule", null)).StatusCode);
        Assert.AreEqual(original, await client.GetFromJsonAsync<ReservationDto>("/reservations/r1"));
        Assert.AreEqual(0, (await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-b/reservations"))!.Count);
    }

    [TestMethod]
    public async Task unknown_reservation_returns_404()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        // Positive control: an absent route must not earn feature points for returning 404.
        await client.PostAsJsonAsync("/reservations", Reservation("probe", "room-a"));
        Assert.AreEqual(HttpStatusCode.OK, (await Change(client, "probe", "room-a", 11, 12)).StatusCode);
        Assert.AreEqual(HttpStatusCode.NotFound, (await Change(client, "absent", "room-a", 13, 14)).StatusCode);
        Assert.AreEqual(HttpStatusCode.BadRequest, (await Change(client, "absent", " ", 13, 14)).StatusCode);
        Assert.AreEqual(1, (await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-a/reservations"))!.Count);
    }

    [TestMethod]
    public async Task reschedule_allows_self_and_adjacent_intervals()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        await client.PostAsJsonAsync("/reservations", Reservation("r1", "room-a"));
        await client.PostAsJsonAsync("/reservations", Reservation("r2", "room-a", 12, 13));
        Assert.AreEqual(HttpStatusCode.OK, (await Change(client, "r1", "room-a", 9, 10)).StatusCode);
        Assert.AreEqual(HttpStatusCode.OK, (await Change(client, "r1", "room-a", 11, 12)).StatusCode);
        Assert.AreEqual(HttpStatusCode.OK, (await Change(client, "r1", "room-a", 13, 14)).StatusCode);
        Assert.AreEqual(2, (await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-a/reservations"))!.Count);
    }

    [TestMethod]
    public async Task concurrent_reschedules_prevent_double_booking()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        for (var round = 0; round < 8; round++)
        {
            var target = $"target-{round}";
            var ids = Enumerable.Range(0, 6).Select(i => $"r-{round}-{i}").ToArray();
            foreach (var id in ids)
            {
                Assert.AreEqual(HttpStatusCode.Created,
                    (await client.PostAsJsonAsync("/reservations", Reservation(id, $"origin-{id}"))).StatusCode);
            }
            var start = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var attempts = ids.Select(async id => { await start.Task; return await Change(client, id, target, 14, 15); }).ToArray();
            start.SetResult(true);
            var responses = await Task.WhenAll(attempts);
            Assert.AreEqual(1, responses.Count(response => response.StatusCode == HttpStatusCode.OK));
            Assert.AreEqual(5, responses.Count(response => response.StatusCode == HttpStatusCode.Conflict));
            Assert.AreEqual(1, (await client.GetFromJsonAsync<List<ReservationDto>>($"/rooms/{target}/reservations"))!.Count);
            for (var i = 0; i < ids.Length; i++)
            {
                var item = await client.GetFromJsonAsync<ReservationDto>($"/reservations/{ids[i]}");
                Assert.AreEqual(responses[i].StatusCode == HttpStatusCode.OK
                    ? Reservation(ids[i], target, 14, 15) : Reservation(ids[i], $"origin-{ids[i]}"), item);
            }
        }
    }

    [TestMethod]
    public async Task concurrent_reads_never_lose_reservation()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        await client.PostAsJsonAsync("/reservations", Reservation("r1", "room-a"));
        Assert.AreEqual(HttpStatusCode.OK, (await Change(client, "r1", "room-a", 9, 10)).StatusCode);
        var start = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var writer = Task.Run(async () =>
        {
            await start.Task;
            for (var i = 0; i < 60; i++)
            {
                Assert.AreEqual(HttpStatusCode.OK,
                    (await Change(client, "r1", "room-a", i % 2 == 0 ? 11 : 9, i % 2 == 0 ? 12 : 10)).StatusCode);
            }
        });
        var readers = Enumerable.Range(0, 4).Select(async _ =>
        {
            await start.Task;
            for (var i = 0; i < 60; i++)
            {
                var response = await client.GetAsync("/reservations/r1");
                Assert.AreEqual(HttpStatusCode.OK, response.StatusCode);
                var item = await response.Content.ReadFromJsonAsync<ReservationDto>();
                Assert.IsTrue(item == Reservation("r1", "room-a") || item == Reservation("r1", "room-a", 11, 12));
            }
        }).ToArray();
        start.SetResult(true);
        await Task.WhenAll(readers.Append(writer));
        Assert.AreEqual(1, (await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-a/reservations"))!.Count);
    }

    [TestMethod]
    public async Task creation_and_rescheduling_share_conflict_detection()
    {
        await using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        await client.PostAsJsonAsync("/reservations", Reservation("probe", "probe-room"));
        Assert.AreEqual(HttpStatusCode.OK, (await Change(client, "probe", "probe-room", 11, 12)).StatusCode);
        for (var round = 0; round < 12; round++)
        {
            var id = $"move-{round}";
            var room = $"target-{round}";
            var original = Reservation(id, $"origin-{round}");
            await client.PostAsJsonAsync("/reservations", original);
            var start = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var create = Task.Run(async () => { await start.Task; return await client.PostAsJsonAsync("/reservations", Reservation($"new-{round}", room, 14, 15)); });
            var move = Task.Run(async () => { await start.Task; return await Change(client, id, room, 14, 15); });
            start.SetResult(true);
            await Task.WhenAll(create, move);
            Assert.IsTrue((create.Result.StatusCode == HttpStatusCode.Created && move.Result.StatusCode == HttpStatusCode.Conflict)
                || (create.Result.StatusCode == HttpStatusCode.Conflict && move.Result.StatusCode == HttpStatusCode.OK));
            Assert.AreEqual(1, (await client.GetFromJsonAsync<List<ReservationDto>>($"/rooms/{room}/reservations"))!.Count);
            Assert.AreEqual(move.Result.StatusCode == HttpStatusCode.OK ? Reservation(id, room, 14, 15) : original,
                await client.GetFromJsonAsync<ReservationDto>($"/reservations/{id}"));
        }
    }
}
