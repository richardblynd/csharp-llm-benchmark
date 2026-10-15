CounterStore stores signed 32-bit counters in SQLite. InitializeAsync is idempotent and
preserves data. GetAsync returns zero for an unknown name. AddAsync atomically creates or
adds a delta with checked overflow; failed writes roll back. Names are trimmed, nonblank,
ordinal and case-sensitive. Methods accept caller cancellation. A supplied SqliteConnection
is borrowed and stays open after disposal; a connection created from a string is owned.
The table counters(name TEXT PRIMARY KEY COLLATE BINARY,value INTEGER NOT NULL) is a public
schema contract; callers may add SQLite triggers. Separate connections can use the same file.

Build: dotnet build Counters.csproj --configuration Release
