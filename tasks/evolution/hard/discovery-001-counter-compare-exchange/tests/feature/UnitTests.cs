using Counters;
using Microsoft.Data.Sqlite;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass] public class FeatureTests
{
    [TestMethod] public async Task compare_exchange_creates_updates_and_reports_mismatch()
    {using var s=new CounterStore();await s.InitializeAsync();Assert.AreEqual(new CounterUpdate(false,0),await s.CompareExchangeAsync("a",1,5));Assert.AreEqual(new CounterUpdate(true,5),await s.CompareExchangeAsync("a",0,5));Assert.AreEqual(new CounterUpdate(false,5),await s.CompareExchangeAsync("a",0,8));Assert.AreEqual(new CounterUpdate(true,-4),await s.CompareExchangeAsync("a",5,-4));Assert.AreEqual(-4,await s.GetAsync("a"));}
    [TestMethod] public async Task compare_exchange_preserves_name_and_integer_contracts()
    {using var s=new CounterStore();await s.InitializeAsync();await s.CompareExchangeAsync(" a ",0,int.MinValue);Assert.AreEqual(int.MinValue,await s.GetAsync("a"));Assert.AreEqual(0,await s.GetAsync("A"));Assert.AreEqual(new CounterUpdate(true,int.MaxValue),await s.CompareExchangeAsync("a",int.MinValue,int.MaxValue));await Assert.ThrowsExceptionAsync<ArgumentException>(()=>s.CompareExchangeAsync(" ",0,1));}
    [TestMethod] public async Task compare_exchange_is_persisted_and_initialization_is_idempotent()
    {var file=Path.Combine(Path.GetTempPath(),Guid.NewGuid()+".db");try{using(var s=new CounterStore("Data Source="+file)){await s.InitializeAsync();await s.CompareExchangeAsync("x",0,9);}using var next=new CounterStore("Data Source="+file);await next.InitializeAsync();Assert.AreEqual(new CounterUpdate(false,9),await next.CompareExchangeAsync("x",0,1));Assert.AreEqual(9,await next.GetAsync("x"));}finally{SqliteConnection.ClearAllPools();File.Delete(file);}}
    [TestMethod] public async Task concurrent_connections_have_one_compare_exchange_winner()
    {var file=Path.Combine(Path.GetTempPath(),Guid.NewGuid()+".db");try{using var a=new CounterStore("Data Source="+file);using var b=new CounterStore("Data Source="+file);await a.InitializeAsync();await b.InitializeAsync();using var ready=new Barrier(2);var results=await Task.WhenAll(Task.Run(async()=>{ready.SignalAndWait();return await a.CompareExchangeAsync("x",0,7);}),Task.Run(async()=>{ready.SignalAndWait();return await b.CompareExchangeAsync("x",0,8);}));Assert.AreEqual(1,results.Count(r=>r.Applied));Assert.IsTrue(new[]{7,8}.Contains(await a.GetAsync("x")));}finally{SqliteConnection.ClearAllPools();File.Delete(file);}}
    [TestMethod] public async Task compare_exchange_interoperates_with_addition()
    {using var s=new CounterStore();await s.InitializeAsync();await s.AddAsync("x",4);Assert.IsTrue((await s.CompareExchangeAsync("x",4,9)).Applied);Assert.AreEqual(11,await s.AddAsync("x",2));Assert.AreEqual(new CounterUpdate(false,11),await s.CompareExchangeAsync("x",9,0));}
    [TestMethod] public async Task cancelled_and_failed_writes_preserve_the_previous_value()
    {using var c=new SqliteConnection("Data Source=:memory:");c.Open();using var s=new CounterStore(c);await s.InitializeAsync();await s.AddAsync("x",3);using var stop=new CancellationTokenSource();stop.Cancel();await Assert.ThrowsExceptionAsync<OperationCanceledException>(()=>s.CompareExchangeAsync("x",3,9,stop.Token));using(var cmd=c.CreateCommand()){cmd.CommandText="CREATE TRIGGER reject_change BEFORE UPDATE ON counters BEGIN SELECT RAISE(ABORT,'rejected'); END";cmd.ExecuteNonQuery();}await Assert.ThrowsExceptionAsync<SqliteException>(()=>s.CompareExchangeAsync("x",3,9));Assert.AreEqual(3,await s.GetAsync("x"));}
}
