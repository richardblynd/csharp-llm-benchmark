OrderedSet<T> stores unique values in insertion order using its optional equality comparer.
Add returns false for an existing value without replacing it. Remove returns whether an
entry existed. Items returns an independent snapshot. Null/default values are supported.
Instances are independent. The collection has no concurrent-use contract.

Build: dotnet build Collections.csproj --configuration Release
