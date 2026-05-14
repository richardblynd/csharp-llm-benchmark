using Microsoft.AspNetCore.Mvc;

[ApiController]
[Route("payments")]
public sealed class PaymentsController : ControllerBase
{
    private readonly PaymentStore store;

    public PaymentsController(PaymentStore store)
    {
        this.store = store;
    }

    [HttpPost]
    public IActionResult Create([FromBody] PaymentRequest? request)
    {
        if (!Request.Headers.TryGetValue("Idempotency-Key", out var keyValues) || string.IsNullOrWhiteSpace(keyValues.ToString()))
        {
            return BadRequest(new { error = "Idempotency-Key is required." });
        }

        var validation = Validate(request);
        if (validation is not null)
        {
            return BadRequest(new { error = validation });
        }

        var result = store.CreateOrReplay(keyValues.ToString().Trim(), request!);
        if (result.Conflict)
        {
            return Conflict(new { error = "The idempotency key was used with a different payload." });
        }

        return CreatedAtAction(nameof(GetById), new { id = result.Payment!.Id }, result.Payment);
    }

    [HttpGet("{id}")]
    public IActionResult GetById(string id)
    {
        var payment = store.Find(id);
        return payment is null ? NotFound() : Ok(payment);
    }

    [HttpGet]
    public IReadOnlyList<PaymentResponse> List()
    {
        return store.List();
    }

    private static string? Validate(PaymentRequest? request)
    {
        if (request is null)
        {
            return "Request body is required.";
        }

        if (request.Amount <= 0)
        {
            return "Amount must be greater than zero.";
        }

        if (request.Currency is null || request.Currency.Length != 3 || request.Currency.Any(character => !char.IsLetter(character)))
        {
            return "Currency must contain exactly three letters.";
        }

        if (string.IsNullOrWhiteSpace(request.CustomerId))
        {
            return "Customer id is required.";
        }

        return null;
    }
}

public sealed record PaymentRequest(decimal Amount, string Currency, string CustomerId);

public sealed record PaymentResponse(string Id, decimal Amount, string Currency, string CustomerId, string Status);

public sealed class PaymentStore
{
    private sealed record IdempotencyEntry(PaymentRequest Request, PaymentResponse Payment);

    private readonly object gate = new();
    private readonly Dictionary<string, IdempotencyEntry> byKey = new(StringComparer.Ordinal);
    private readonly Dictionary<string, PaymentResponse> byId = new(StringComparer.Ordinal);
    private int nextId;

    public PaymentCreationResult CreateOrReplay(string idempotencyKey, PaymentRequest request)
    {
        lock (gate)
        {
            if (byKey.TryGetValue(idempotencyKey, out var existing))
            {
                return existing.Request == request
                    ? new PaymentCreationResult(false, existing.Payment)
                    : new PaymentCreationResult(true, null);
            }

            var payment = new PaymentResponse(
                $"pay-{++nextId:0000}",
                request.Amount,
                request.Currency.ToUpperInvariant(),
                request.CustomerId,
                "Authorized");
            byKey[idempotencyKey] = new IdempotencyEntry(request, payment);
            byId[payment.Id] = payment;
            return new PaymentCreationResult(false, payment);
        }
    }

    public PaymentResponse? Find(string id)
    {
        lock (gate)
        {
            return byId.GetValueOrDefault(id);
        }
    }

    public IReadOnlyList<PaymentResponse> List()
    {
        lock (gate)
        {
            return byId.Values.OrderBy(payment => payment.Id, StringComparer.Ordinal).ToArray();
        }
    }
}

public sealed record PaymentCreationResult(bool Conflict, PaymentResponse? Payment);
