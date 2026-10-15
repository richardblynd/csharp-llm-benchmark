using Microsoft.Data.Sqlite;
namespace Counters;
public sealed partial class CounterStore : IDisposable
{
    private readonly SqliteConnection connection;
    private readonly bool ownsConnection;
    private readonly object gate=new();
    public CounterStore(string connectionString="Data Source=:memory:")
    {connection=new(connectionString);connection.Open();ownsConnection=true;}
    public CounterStore(SqliteConnection connection)
    {ArgumentNullException.ThrowIfNull(connection);this.connection=connection;if(connection.State!=System.Data.ConnectionState.Open)connection.Open();}
    private static string Key(string name)
    {if(string.IsNullOrWhiteSpace(name))throw new ArgumentException("A name is required.",nameof(name));return name.Trim();}
    public Task InitializeAsync(CancellationToken cancellationToken=default)
    {cancellationToken.ThrowIfCancellationRequested();lock(gate){using var c=connection.CreateCommand();c.CommandText="CREATE TABLE IF NOT EXISTS counters(name TEXT PRIMARY KEY COLLATE BINARY,value INTEGER NOT NULL)";c.ExecuteNonQuery();}return Task.CompletedTask;}
    private int Read(string name,SqliteTransaction? tx=null)
    {using var c=connection.CreateCommand();c.Transaction=tx;c.CommandText="SELECT value FROM counters WHERE name=$name";c.Parameters.AddWithValue("$name",name);var result=c.ExecuteScalar();return result is null?0:Convert.ToInt32(result);}
    private void Write(string name,int value,SqliteTransaction tx)
    {using var c=connection.CreateCommand();c.Transaction=tx;c.CommandText="INSERT INTO counters(name,value) VALUES($name,$value) ON CONFLICT(name) DO UPDATE SET value=excluded.value";c.Parameters.AddWithValue("$name",name);c.Parameters.AddWithValue("$value",value);c.ExecuteNonQuery();}
    public Task<int> GetAsync(string name,CancellationToken cancellationToken=default)
    {name=Key(name);cancellationToken.ThrowIfCancellationRequested();lock(gate)return Task.FromResult(Read(name));}
    public Task<int> AddAsync(string name,int delta,CancellationToken cancellationToken=default)
    {name=Key(name);cancellationToken.ThrowIfCancellationRequested();lock(gate){using var tx=connection.BeginTransaction();int value=checked(Read(name,tx)+delta);Write(name,value,tx);cancellationToken.ThrowIfCancellationRequested();tx.Commit();return Task.FromResult(value);}}
    public void Dispose(){if(ownsConnection)connection.Dispose();}
}
