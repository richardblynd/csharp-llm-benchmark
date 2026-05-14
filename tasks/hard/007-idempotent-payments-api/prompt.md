Write an in-memory ASP.NET Core payments API.

The generated file must be `Controllers/PaymentsController.cs`.

Required behavior:
- Do not include a namespace.
- Do not use external services, external storage or network calls.
- All code, public identifiers, exception messages and comments must be written in English.
- Use controllers and the `PaymentStore` service registered by `Program.cs`.
- `POST /payments` creates a payment.
- `POST /payments` requires an `Idempotency-Key` header with a non-empty value.
- The request body must include `amount`, `currency` and `customerId`.
- `amount` must be greater than zero, `currency` must be exactly three letters and `customerId` must be non-empty.
- A valid first request returns `201 Created` with a `Location` header and a JSON response containing `id`, `amount`, `currency`, `customerId` and `status`.
- Successful payment responses must use the exact status value `Authorized`.
- Repeating the same idempotency key with an equivalent payload must return the same status code and same response body without creating a second payment.
- Reusing the same idempotency key with a different payload must return `409 Conflict`.
- Concurrent equivalent requests with the same idempotency key must create exactly one payment.
- `GET /payments/{id}` returns the payment or `404 Not Found`.
- `GET /payments` returns all payments in deterministic id order.
- Application state must be isolated per web application factory.
