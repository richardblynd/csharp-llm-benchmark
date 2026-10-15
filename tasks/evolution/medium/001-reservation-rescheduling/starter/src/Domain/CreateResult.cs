namespace Reservations.Domain;

public enum CreateResult
{
    Created,
    DuplicateId,
    Conflict
}
