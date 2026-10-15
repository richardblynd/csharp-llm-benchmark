using TodoApp;
using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass] public class RegressionTests
{
    [TestMethod] public async Task old_creation_payload_and_location_are_preserved()
    {using var app=new WebApplicationFactory<Program>();using var c=app.CreateClient();var r=await c.PostAsJsonAsync("/todos",new TodoInput(7," hello "));Assert.AreEqual(HttpStatusCode.Created,r.StatusCode);Assert.AreEqual("/todos/7",r.Headers.Location!.ToString());Assert.AreEqual(new Todo(7,"hello",false),await r.Content.ReadFromJsonAsync<Todo>());}
    [TestMethod] public async Task old_validation_and_duplicate_ids_are_preserved()
    {using var app=new WebApplicationFactory<Program>();using var c=app.CreateClient();foreach(var row in new[]{new TodoInput(0,"a"),new TodoInput(1," "),new TodoInput(1,null)})Assert.AreEqual(HttpStatusCode.BadRequest,(await c.PostAsJsonAsync("/todos",row)).StatusCode);await c.PostAsJsonAsync("/todos",new TodoInput(1,"a"));Assert.AreEqual(HttpStatusCode.Conflict,(await c.PostAsJsonAsync("/todos",new TodoInput(1,"b"))).StatusCode);Assert.AreEqual("a",(await c.GetFromJsonAsync<Todo>("/todos/1"))!.Title);}
    [TestMethod] public async Task old_reads_sort_by_id_and_missing_reads_return_404()
    {using var app=new WebApplicationFactory<Program>();using var c=app.CreateClient();await c.PostAsJsonAsync("/todos",new TodoInput(2,"b"));await c.PostAsJsonAsync("/todos",new TodoInput(1,"a"));CollectionAssert.AreEqual(new[]{1,2},(await c.GetFromJsonAsync<Todo[]>("/todos"))!.Select(t=>t.Id).ToArray());Assert.AreEqual(HttpStatusCode.NotFound,(await c.GetAsync("/todos/99")).StatusCode);}
    [TestMethod] public async Task old_deletion_and_app_isolation_are_preserved()
    {using var app=new WebApplicationFactory<Program>();using var c=app.CreateClient();await c.PostAsJsonAsync("/todos",new TodoInput(1,"a"));using var other=new WebApplicationFactory<Program>();using var oc=other.CreateClient();Assert.AreEqual(HttpStatusCode.NotFound,(await oc.GetAsync("/todos/1")).StatusCode);Assert.AreEqual(HttpStatusCode.NoContent,(await c.DeleteAsync("/todos/1")).StatusCode);Assert.AreEqual(HttpStatusCode.NotFound,(await c.DeleteAsync("/todos/1")).StatusCode);}
    [TestMethod] public async Task old_concurrent_creates_have_one_winner()
    {using var app=new WebApplicationFactory<Program>();using var c=app.CreateClient();var results=await Task.WhenAll(Enumerable.Range(0,12).Select(_=>c.PostAsJsonAsync("/todos",new TodoInput(1,"a"))));Assert.AreEqual(1,results.Count(r=>r.StatusCode==HttpStatusCode.Created));Assert.AreEqual(11,results.Count(r=>r.StatusCode==HttpStatusCode.Conflict));}
}
