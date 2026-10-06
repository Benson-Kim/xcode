using System.Collections.Concurrent;
using System.Data;
using System.Net.Mail;
using System.Security.Claims;
using Auth.Application;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Api;

// Per-user locking: serializes auth for the same account while unrelated users proceed concurrently.
// Capped at MaxEntries to prevent memory exhaustion from attackers probing many phone numbers.
public sealed class AuthGate
{
    private const int MaxEntries = 10_000;
    private readonly ConcurrentDictionary<string, Entry> locks = new();

    private sealed class Entry
    {
        public SemaphoreSlim Semaphore { get; } = new(1, 1);
        public long LastUsedTicks = Environment.TickCount64;
    }

    public SemaphoreSlim For(string key)
    {
        var entry = locks.GetOrAdd(key, _ => new Entry());
        entry.LastUsedTicks = Environment.TickCount64;

        if (locks.Count > MaxEntries)
            Evict();

        return entry.Semaphore;
    }

    private void Evict()
    {
        var target = (int)(MaxEntries * 0.8);
        var candidates = locks
            .Where(kv => kv.Value.Semaphore.CurrentCount > 0)
            .OrderBy(kv => kv.Value.LastUsedTicks)
            .ToList();

        foreach (var kv in candidates)
        {
            if (locks.Count <= target) break;
            locks.TryRemove(kv);
        }
    }
}
public static class AuthEndpoints
{
    public static void MapAuth(this WebApplication app)
    {
        // The rate limiter's 429 has no body.
        var group = app.MapGroup("/auth").RequireRateLimiting("auth")
            .WithMetadata(new ProducesResponseTypeMetadata(StatusCodes.Status429TooManyRequests, typeof(void)));
        group.MapPost("/sign-in", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.SignIn(r, ct), ct))
            .Answers(200, 202, 400, 401, 423, 503);
        group.MapPost("/unlock", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.SignIn(r, ct), ct))
            .Answers(200, 202, 400, 401, 423, 503);
        group.MapPost("/verify-device", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.VerifyDevice(r), ct))
            .Answers(200, 400, 401);
        group.MapPost("/setup-pin/request", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.RequestPin(r, CodePurpose.FirstSetup, ct), ct))
            .Answers(202, 400);
        group.MapPost("/setup-pin/verify", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.VerifyCode(r, CodePurpose.FirstSetup), ct))
            .Answers(200, 400, 401);
        group.MapPost("/setup-pin/complete", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.CompletePin(r, CodePurpose.FirstSetup), ct))
            .Answers(200, 400, 401);
        group.MapPost("/pin-reset/request", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.RequestPin(r, CodePurpose.PinReset, ct), ct))
            .Answers(202, 400);
        group.MapPost("/pin-reset/verify", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.VerifyCode(r, CodePurpose.PinReset), ct))
            .Answers(200, 400, 401);
        group.MapPost("/pin-reset/complete", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.CompletePin(r, CodePurpose.PinReset), ct))
            .Answers(200, 400, 401);
        group.MapPost("/refresh", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.Refresh(r), ct))
            .Answers(200, 400, 401);
        group.MapPost("/sign-out", (AuthRequest r, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) => Run(r, db, gate, s, () => s.SignOut(r), ct))
            .Answers(200, 400);
        group.MapPost("/devices/{id}/revoke", (string id, ClaimsPrincipal principal, AuthService s, AuthDb db, AuthGate gate, CancellationToken ct) =>
        {
            var current = principal.FindFirstValue("device");
            return string.Equals(current, id, StringComparison.Ordinal)
                ? Run(new(DeviceId: id), db, gate, s, () => s.RevokeDevice(Guid.Parse(principal.FindFirstValue("sub")!), id), ct)
                : Task.FromResult<IResult>(Results.Forbid());
        }).RequireAuthorization().Answers(200).Produces(StatusCodes.Status403Forbidden);
        group.MapGet("/session", (ClaimsPrincipal principal) =>
            Results.Ok(new AuthSessionResponse(
                Guid.Parse(principal.FindFirstValue("sub")!),
                principal.FindFirstValue("first_name") ?? "",
                principal.FindFirstValue("last_name") ?? "",
                principal.FindFirstValue("role") ?? "",
                principal.FindAll("permission").Select(x => x.Value).ToArray())))
            .RequireAuthorization().Produces<AuthSessionResponse>();
    }

    private static RouteHandlerBuilder Answers(this RouteHandlerBuilder endpoint, params int[] statuses)
    {
        foreach (var status in statuses)
            endpoint.Produces<AuthResponse>(status);
        return endpoint;
    }
    private static string LockKey(AuthRequest r) =>
        PhoneNumber.Normalize(r.PhoneNumber) is { Length: > 0 } phone ? phone : $"device:{r.DeviceId}";

    private static async Task<IResult> Run(AuthRequest r, AuthDb db, AuthGate gate, AuthService s, Func<Task<AuthResult>> action, CancellationToken ct)
    {
        if (r.DeviceId is null || r.DeviceId.Length is < 1 or > 128 || r.PhoneNumber is null || r.PhoneNumber.Length > 14 || r.Email is null || r.Email.Length > 320 ||
            (r.Email.Length > 0 && !MailAddress.TryCreate(r.Email, out _)) || r.Pin is null || r.Pin.Length > PinRules.MaximumLength || r.Code is null || r.Code.Length > 32 || r.RefreshToken is null || r.RefreshToken.Length > 256)
            return Results.Json(new AuthResponse("invalid_request"), statusCode: 400);
        AuthResult result;
        var semaphore = gate.For(LockKey(r));
        await semaphore.WaitAsync(ct);
        try
        {
            var strategy = db.Database.CreateExecutionStrategy();
            result = await strategy.ExecuteAsync(async () =>
            {
                await using var transaction = await db.Database.BeginTransactionAsync(IsolationLevel.Serializable, ct);
                var r2 = await action();
                await db.SaveChangesAsync(ct);
                await transaction.CommitAsync(ct);
                return r2;
            });
        }
        finally { semaphore.Release(); }
        result = await s.Deliver(result, ct);
        return Results.Json(result.Body, statusCode: result.HttpStatus);
    }
}
