using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public class UnitTests
{
    [TestMethod]
    public async Task post_reservations_creates_valid_reservation()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        var reservation = new ReservationDto("r1", "room-a", new DateTime(2026, 1, 1, 9, 0, 0), new DateTime(2026, 1, 1, 10, 0, 0));

        var response = await client.PostAsJsonAsync("/reservations", reservation);

        Assert.AreEqual(HttpStatusCode.Created, response.StatusCode);
    }

    [TestMethod]
    public async Task rejects_invalid_interval_with_400()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        var reservation = new ReservationDto("r1", "room-a", new DateTime(2026, 1, 1, 10, 0, 0), new DateTime(2026, 1, 1, 10, 0, 0));

        var response = await client.PostAsJsonAsync("/reservations", reservation);

        Assert.AreEqual(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [TestMethod]
    public async Task rejects_conflict_in_same_room_with_409()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        await client.PostAsJsonAsync("/reservations", new ReservationDto("r1", "room-a", new DateTime(2026, 1, 1, 9, 0, 0), new DateTime(2026, 1, 1, 11, 0, 0)));

        var response = await client.PostAsJsonAsync("/reservations", new ReservationDto("r2", "room-a", new DateTime(2026, 1, 1, 10, 0, 0), new DateTime(2026, 1, 1, 12, 0, 0)));

        Assert.AreEqual(HttpStatusCode.Conflict, response.StatusCode);
    }

    [TestMethod]
    public async Task accepts_same_time_in_different_rooms()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        var start = new DateTime(2026, 1, 1, 9, 0, 0);
        var end = new DateTime(2026, 1, 1, 10, 0, 0);
        await client.PostAsJsonAsync("/reservations", new ReservationDto("r1", "room-a", start, end));

        var response = await client.PostAsJsonAsync("/reservations", new ReservationDto("r2", "room-b", start, end));

        Assert.AreEqual(HttpStatusCode.Created, response.StatusCode);
    }

    [TestMethod]
    public async Task lists_room_reservations_in_order()
    {
        await using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        await client.PostAsJsonAsync("/reservations", new ReservationDto("late", "room-a", new DateTime(2026, 1, 1, 11, 0, 0), new DateTime(2026, 1, 1, 12, 0, 0)));
        await client.PostAsJsonAsync("/reservations", new ReservationDto("early", "room-a", new DateTime(2026, 1, 1, 9, 0, 0), new DateTime(2026, 1, 1, 10, 0, 0)));

        var reservations = await client.GetFromJsonAsync<List<ReservationDto>>("/rooms/room-a/reservations");

        CollectionAssert.AreEqual(new[] { "early", "late" }, reservations!.Select(r => r.Id).ToArray());
    }
}
