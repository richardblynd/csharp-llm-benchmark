namespace TodoApp;
public sealed record Todo(int Id,string Title,bool Completed);
public sealed record TodoInput(int Id,string? Title);
public sealed partial class TodoStore
{
    private readonly object gate = new();
    private readonly Dictionary<int,Todo> items = new();
    public Todo? Get(int id) {lock(gate) return items.GetValueOrDefault(id);}
    public Todo[] List() {lock(gate) return items.Values.OrderBy(t=>t.Id).ToArray();}
    public Todo? Create(TodoInput input)
    {
        lock(gate)
        {
            if(items.ContainsKey(input.Id)) return null;
            var todo=new Todo(input.Id,input.Title!.Trim(),false);items.Add(todo.Id,todo);return todo;
        }
    }
    public bool Delete(int id) {lock(gate) return items.Remove(id);}
}
