Add search and sorting to GET /products in the existing catalog API.
Preserve every existing CRUD route, status code, validation rule and JSON DTO.
Requests without query parameters must keep their current ascending-Id behavior.

Support these optional query parameters:
- q: trim the supplied text, then match a substring of Name using OrdinalIgnoreCase.
- category: trim the supplied text, then match the full Category using OrdinalIgnoreCase.
  Combine q and category with AND. Null/blank filters do not restrict the result.
- sort: id (default), name or price.
- direction: asc (default) or desc.

Trim sorting values and accept them case-insensitively. Null/blank sorting values use
their defaults. Unsupported sort/direction values return 400, including on an empty store.
For name sorting use OrdinalIgnoreCase. For equal names or prices, tie-break by ascending Id
in BOTH directions. For id sorting, use the requested direction directly.
Return the existing complete DTO array with 200; no matches returns [].
Searching must reflect later creates, updates and deletes and must never change store state,
stored strings or the order returned by a later request without parameters.
Do not add pagination, dependencies, routes or external services. Write English code and messages.

