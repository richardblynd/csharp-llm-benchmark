Add POST /todos/complete accepting a JSON array of integer ids. A valid request has at
least one id, all positive, with no duplicates. Invalid input, including JSON null, returns
400 before looking up ids. If any id is unknown, return 404 and leave every todo unchanged.
Otherwise mark every requested todo Completed=true and return 200 with their Todo payloads
in REQUEST order. Completing an already completed todo succeeds idempotently. Preserve all
titles and ids. Validation, reads and updates must be atomic through the existing shared
TodoStore, including concurrent batch requests. Do not mutate a previously returned snapshot.
Keep the existing CRUD routes, validation, status codes and default ordering unchanged.
