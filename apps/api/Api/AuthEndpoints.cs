using System.Data;
using System.Net.Mail;
using System.Security.Claims;
using Auth.Application;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Api;

// Serializes local requests; serializable database transactions also protect multi-instance state.
public sealed class AuthGate { public SemaphoreSlim Semaphore { get; } = new(1, 1); }
public static class AuthEndpoints
{
    public static void MapAuth(this WebApplication app)
    {
        var group = app.MapGroup("/auth").RequireRateLimiting("auth");
        group.MapPost("/sign-in", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.SignIn(r, ct), ct));
        group.MapPost("/unlock", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.SignIn(r, ct), ct));
        group.MapPost("/verify-device", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.VerifyDevice(r), ct));
        group.MapPost("/setup-pin/request", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.RequestPin(r, CodePurpose.FirstSetup, ct), ct));
        group.MapPost("/setup-pin/verify", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.VerifyCode(r, CodePurpose.FirstSetup), ct));
        group.MapPost("/setup-pin/complete", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.CompletePin(r, CodePurpose.FirstSetup), ct));
        group.MapPost("/pin-reset/request", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.RequestPin(r, CodePurpose.PinReset, ct), ct));
        group.MapPost("/pin-reset/verify", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.VerifyCode(r, CodePurpose.PinReset), ct));
        group.MapPost("/pin-reset/complete", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.CompletePin(r, CodePurpose.PinReset), ct));
        group.MapPost("/refresh", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.Refresh(r), ct));
        group.MapPost("/sign-out", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.SignOut(r), ct));
        group.MapPost("/devices/{id}/revoke", (string id, ClaimsPrincipal principal, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) =>
        {
            var current = principal.FindFirstValue("device");
            return string.Equals(current, id, StringComparison.Ordinal)
                ? Run(new(DeviceId: id), db, gate, s, () => s.RevokeDevice(Guid.Parse(principal.FindFirstValue("sub")!), id), ct)
                : Task.FromResult<IResult>(Results.Forbid());
        }).RequireAuthorization();
        group.MapGet("/session", (ClaimsPrincipal principal) =>
            Results.Ok(new AuthSessionResponse(
                Guid.Parse(principal.FindFirstValue("sub")!),
                principal.FindFirstValue("first_name") ?? "",
                principal.FindFirstValue("last_name") ?? "",
                principal.FindFirstValue("role") ?? "",
                principal.FindAll("permission").Select(x => x.Value).ToArray())))
            .RequireAuthorization();
    }
    private static async Task<IResult> Run(AuthRequest r, AuthDb db, AuthGate gate, AuthService s, Func<Task<AuthResult>> action, CancellationToken ct)
    {
        if (r.DeviceId is null || r.DeviceId.Length is < 1 or > 128 || r.PhoneNumber is null || r.PhoneNumber.Length > 14 || r.Email is null || r.Email.Length > 320 ||
            (r.Email.Length > 0 && !MailAddress.TryCreate(r.Email, out _)) || r.Pin is null || r.Pin.Length > 128 || r.Code is null || r.Code.Length > 32 || r.RefreshToken is null || r.RefreshToken.Length > 256)
            return Results.Json(new AuthResponse("invalid_request"), statusCode: 400);
        AuthResult result;
        await gate.Semaphore.WaitAsync(ct);
        try
        {
            await using var transaction = await db.Database.BeginTransactionAsync(IsolationLevel.Serializable, ct);
            result = await action();
            await db.SaveChangesAsync(ct);
            await transaction.CommitAsync(ct);
        }
        finally { gate.Semaphore.Release(); }
        // A verification email goes out only now: after the commit, so a failed commit sends nothing, and outside the
        // gate, so a slow mail server holds up no one else's sign-in.
        result = await s.Deliver(result, ct);
        return Results.Json(result.Body, statusCode: result.HttpStatus);
    }
}
