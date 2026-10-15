Add public record CounterUpdate(bool Applied, int Value) and CounterStore method
Task<CounterUpdate> CompareExchangeAsync(string name, int expected, int replacement,
CancellationToken cancellationToken = default). Treat a missing counter as value zero.
If current value equals expected, persist replacement and return (true, replacement).
Otherwise leave the database unchanged and return (false, current). Negative and boundary
int values are valid. Normalize names using the existing rule, retaining ordinal case sensitivity.
The check and write must be atomic across separate instances/connections to the same SQLite
file and coordinate with existing AddAsync. Values must survive reopening the database.
Cancellation and SQLite write failures must leave the old value intact. Preserve all existing
APIs, checked addition/overflow, initialization and connection ownership behavior. Keep using
the existing SQLite dependency; do not substitute an in-memory dictionary for persistence.
