using Counters;
using Microsoft.Data.Sqlite;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass] public class RegressionTests
{
    [TestMethod] public async Task old_initialization_and_unknown_values_are_preserved()
    {using var s=new CounterStore();await s.InitializeAsync();Assert.AreEqual(0,await s.GetAsync("missing"));await s.AddAsync("x",4);await s.InitializeAsync();Assert.AreEqual(4,await s.GetAsync("x"));}
    [TestMethod] public async Task old_addition_normalization_and_case_are_preserved()
    {using var s=new CounterStore();await s.InitializeAsync();Assert.AreEqual(4,await s.AddAsync(" a ",4));Assert.AreEqual(2,await s.AddAsync("a",-2));Assert.AreEqual(0,await s.GetAsync("A"));await Assert.ThrowsExceptionAsync<ArgumentException>(()=>s.GetAsync(" "));}
    [TestMethod] public async Task old_overflow_and_cancellation_leave_state_intact()
    {using var s=new CounterStore();await s.InitializeAsync();await s.AddAsync("x",int.MaxValue);await Assert.ThrowsExceptionAsync<OverflowException>(()=>s.AddAsync("x",1));using var stop=new CancellationTokenSource();stop.Cancel();await Assert.ThrowsExceptionAsync<OperationCanceledException>(()=>s.AddAsync("x",-1,stop.Token));Assert.AreEqual(int.MaxValue,await s.GetAsync("x"));}
    [TestMethod] public async Task old_borrowed_connections_and_failures_are_preserved()
    {using var c=new SqliteConnection("Data Source=:memory:");c.Open();using(var s=new CounterStore(c)){await s.InitializeAsync();await s.AddAsync("x",2);using(var cmd=c.CreateCommand()){cmd.CommandText="CREATE TRIGGER reject_change BEFORE UPDATE ON counters BEGIN SELECT RAISE(ABORT,'rejected'); END";cmd.ExecuteNonQuery();}await Assert.ThrowsExceptionAsync<SqliteException>(()=>s.AddAsync("x",1));Assert.AreEqual(2,await s.GetAsync("x"));}Assert.AreEqual(System.Data.ConnectionState.Open,c.State);}
    [TestMethod] public async Task old_concurrent_additions_are_atomic_across_connections()
    {var file=Path.Combine(Path.GetTempPath(),Guid.NewGuid()+".db");try{using var a=new CounterStore("Data Source="+file);using var b=new CounterStore("Data Source="+file);await a.InitializeAsync();await b.InitializeAsync();await Task.WhenAll(Enumerable.Range(0,12).Select(i=>Task.Run(()=>i%2==0?a.AddAsync("x",1):b.AddAsync("x",1))));Assert.AreEqual(12,await a.GetAsync("x"));}finally{SqliteConnection.ClearAllPools();File.Delete(file);}}
}
