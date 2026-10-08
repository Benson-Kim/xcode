namespace Auth.Application.Authentication;

// Runs one auth operation for one account at a time, in a serializable transaction, and sends the code the
// committed attempt issued (if any) once the account's lock is released.
public interface IAuthUnitOfWork
{
    Task<AuthResult> Run(string lockKey, Func<Task<AuthResult>> action, CancellationToken ct);
}
