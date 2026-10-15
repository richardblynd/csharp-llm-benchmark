namespace TodoApp;
public sealed partial class TodoStore
{
    public Todo[]? Complete(int[] ids)
    {
        lock(gate)
        {
            if(ids.Any(id=>!items.ContainsKey(id))) return null;
            return ids.Select(id=>items[id]=items[id] with {Completed=true}).ToArray();
        }
    }
}
