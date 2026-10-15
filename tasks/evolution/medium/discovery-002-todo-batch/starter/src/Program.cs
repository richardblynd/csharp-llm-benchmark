using TodoApp;
var builder=WebApplication.CreateBuilder(args);builder.Services.AddSingleton<TodoStore>();
var app=builder.Build();
app.MapPost("/todos",(TodoInput input,TodoStore store)=>
{
    if(input.Id<=0 || string.IsNullOrWhiteSpace(input.Title)) return Results.BadRequest();
    var todo=store.Create(input);return todo is null?Results.Conflict():Results.Created($"/todos/{todo.Id}",todo);
});
app.MapGet("/todos",(TodoStore store)=>store.List());
app.MapGet("/todos/{id:int}",(int id,TodoStore store)=>store.Get(id) is { } todo?Results.Ok(todo):Results.NotFound());
app.MapDelete("/todos/{id:int}",(int id,TodoStore store)=>store.Delete(id)?Results.NoContent():Results.NotFound());
app.Run();
public partial class Program { }
