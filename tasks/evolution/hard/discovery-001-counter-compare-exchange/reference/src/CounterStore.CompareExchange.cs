namespace Counters;
public sealed record CounterUpdate(bool Applied,int Value);
public sealed partial class CounterStore
{
    public Task<CounterUpdate> CompareExchangeAsync(string name,int expected,int replacement,CancellationToken cancellationToken=default)
    {
        name=Key(name);cancellationToken.ThrowIfCancellationRequested();
        lock(gate)
        {
            using var tx=connection.BeginTransaction();int current=Read(name,tx);
            if(current!=expected)return Task.FromResult(new CounterUpdate(false,current));
            Write(name,replacement,tx);cancellationToken.ThrowIfCancellationRequested();tx.Commit();
            return Task.FromResult(new CounterUpdate(true,replacement));
        }
    }
}
