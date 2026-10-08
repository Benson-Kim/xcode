using System.Data;
using Auth.Application;
using Auth.Application.Authentication;
using Auth.Domain;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

public sealed class AuthUnitOfWork(AuthDb db, AuthGate gate, VerificationMailer mailer) : IAuthUnitOfWork
{
    public async Task<AuthResult> Run(string lockKey, Func<Task<AuthResult>> action, CancellationToken ct)
    {
        AuthResult result;
        var semaphore = gate.For(lockKey);
        await semaphore.WaitAsync(ct);
        try
        {
            var attempts = 0;
            result = await db.Database.CreateExecutionStrategy().ExecuteAsync(async () =>
            {
                // A retry starts from the database: entities the rolled-back attempt saved are still tracked as saved.
                if (attempts++ > 0)
                    db.ChangeTracker.Clear();
                await using var transaction = await db.Database.BeginTransactionAsync(IsolationLevel.Serializable, ct);
                var attempt = await action();
                await db.SaveChangesAsync(ct);
                await transaction.CommitAsync(ct);
                return attempt;
            });
        }
        finally { semaphore.Release(); }
        return await Deliver(result, ct);
    }

    // A new-device code is sent before answering, so a failed send can say so. Other codes go after the reply, so the
    // response time does not reveal whether the number has an account.
    private async Task<AuthResult> Deliver(AuthResult result, CancellationToken ct)
    {
        if (result.Mail is not { } message)
            return result;
        if (message.Purpose != CodePurpose.NewDevice)
        {
            mailer.SendLater(message);
            return result;
        }
        return await mailer.Send(message, ct) ? result : new(503, new("service_unavailable"));
    }
}
