Add bool MoveBefore(T item, T anchor) and bool MoveAfter(T item, T anchor) to OrderedSet<T>.
Both values must already exist according to the configured equality comparer. Return false
and leave the collection unchanged if either is absent. If they identify the same entry,
return true without changing anything. Otherwise move the existing item immediately before
or after the anchor, preserving all other relative order, the stored values, and Count.
Already adjacent entries succeed. Null/default values must work when supported by the
comparer. Preserve Add, Remove, Contains, insertion order and independent snapshots.
Do not replace an existing value by the spelling of an argument. No new dependencies.
