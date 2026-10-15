using TodoApp;
using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass] public class FeatureTests
{
    private static async Task Seed(HttpClient c){foreach(var id in new[]{1,2,3}) Assert.AreEqual(HttpStatusCode.Created,(await c.PostAsJsonAsync("/todos",new TodoInput(id," task "+id))).StatusCode);}
    [TestMethod] public async Task batch_returns_requested_order_and_updates_reads()
    {using var app=new WebApplicationFactory<Program>();using var c=app.CreateClient();await Seed(c);var r=await c.PostAsJsonAsync("/todos/complete",new[]{3,1});Assert.AreEqual(HttpStatusCode.OK,r.StatusCode);var rows=(await r.Content.ReadFromJsonAsync<Todo[]>())!;CollectionAssert.AreEqual(new[]{3,1},rows.Select(t=>t.Id).ToArray());Assert.IsTrue(rows.All(t=>t.Completed));Assert.AreEqual("task 3",rows[0].Title);Assert.IsTrue((await c.GetFromJsonAsync<Todo>("/todos/1"))!.Completed);Assert.IsFalse((await c.GetFromJsonAsync<Todo>("/todos/2"))!.Completed);}
    [TestMethod] public async Task invalid_batches_return_400_without_changes()
    {using var app=new WebApplicationFactory<Program>();using var c=app.CreateClient();await Seed(c);foreach(var ids in new int[]?[]{null,Array.Empty<int>(),new[]{1,1},new[]{1,-1},new[]{0,99}})Assert.AreEqual(HttpStatusCode.BadRequest,(await c.PostAsJsonAsync("/todos/complete",ids)).StatusCode);Assert.IsTrue((await c.GetFromJsonAsync<Todo[]>("/todos"))!.All(t=>!t.Completed));}
    [TestMethod] public async Task unknown_ids_roll_back_the_whole_batch()
    {using var app=new WebApplicationFactory<Program>();using var c=app.CreateClient();await Seed(c);Assert.AreEqual(HttpStatusCode.NotFound,(await c.PostAsJsonAsync("/todos/complete",new[]{1,99,2})).StatusCode);Assert.IsTrue((await c.GetFromJsonAsync<Todo[]>("/todos"))!.All(t=>!t.Completed));}
    [TestMethod] public async Task repeated_completion_is_idempotent_and_snapshots_are_stable()
    {using var app=new WebApplicationFactory<Program>();using var c=app.CreateClient();await Seed(c);var before=await c.GetFromJsonAsync<Todo[]>("/todos");for(int i=0;i<2;i++)Assert.AreEqual(HttpStatusCode.OK,(await c.PostAsJsonAsync("/todos/complete",new[]{2})).StatusCode);Assert.IsFalse(before![1].Completed);Assert.IsTrue((await c.GetFromJsonAsync<Todo>("/todos/2"))!.Completed);}
    [TestMethod] public async Task concurrent_batches_preserve_all_updates_and_sorted_reads()
    {using var app=new WebApplicationFactory<Program>();using var c=app.CreateClient();await Seed(c);var results=await Task.WhenAll(Enumerable.Range(0,18).Select(i=>c.PostAsJsonAsync("/todos/complete",i%2==0?new[]{1,2}:new[]{2,3})));Assert.IsTrue(results.All(r=>r.StatusCode==HttpStatusCode.OK));var rows=(await c.GetFromJsonAsync<Todo[]>("/todos"))!;CollectionAssert.AreEqual(new[]{1,2,3},rows.Select(t=>t.Id).ToArray());Assert.IsTrue(rows.All(t=>t.Completed));}
}
