using System.Net.Mail;
using System.Security.Claims;
using Auth.Application;
using Auth.Application.Authentication;
using Auth.Domain;
using Auth.Infrastructure;

namespace Auth.Api;

public static class AuthEndpoints
{
    public static IServiceCollection AddAuthServices(this IServiceCollection services) => services
        .AddScoped<AuthAccounts>()
        .AddScoped<AuthDevices>()
        .AddScoped<AuthPolicy>()
        .AddScoped<AuthCodes>()
        .AddScoped<SessionTokens>()
        .AddScoped<SignInService>()
        .AddScoped<PinSetupService>()
        .AddScoped<SessionService>()
        .AddScoped<IAuthUnitOfWork, AuthUnitOfWork>();

    public static void MapAuth(this WebApplication app)
    {
        // The rate limiter's 429 has no body.
        var group = app.MapGroup("/auth").RequireRateLimiting("auth")
            .WithMetadata(new ProducesResponseTypeMetadata(StatusCodes.Status429TooManyRequests, typeof(void)));
        group.MapPost("/sign-in", (AuthRequest r, SignInService s, IAuthUnitOfWork work, CancellationToken ct) => Run(r, work, () => s.SignIn(r, ct), ct))
            .Answers(200, 202, 400, 401, 423, 503);
        group.MapPost("/unlock", (AuthRequest r, SignInService s, IAuthUnitOfWork work, CancellationToken ct) => Run(r, work, () => s.SignIn(r, ct), ct))
            .Answers(200, 202, 400, 401, 423, 503);
        group.MapPost("/verify-device", (AuthRequest r, SignInService s, IAuthUnitOfWork work, CancellationToken ct) => Run(r, work, () => s.VerifyDevice(r), ct))
            .Answers(200, 400, 401);
        group.MapPost("/setup-pin/request", (AuthRequest r, PinSetupService s, IAuthUnitOfWork work, CancellationToken ct) => Run(r, work, () => s.Request(r, CodePurpose.FirstSetup, ct), ct))
            .Answers(202, 400);
        group.MapPost("/setup-pin/verify", (AuthRequest r, PinSetupService s, IAuthUnitOfWork work, CancellationToken ct) => Run(r, work, () => s.VerifyCode(r, CodePurpose.FirstSetup), ct))
            .Answers(200, 400, 401);
        group.MapPost("/setup-pin/complete", (AuthRequest r, PinSetupService s, IAuthUnitOfWork work, CancellationToken ct) => Run(r, work, () => s.CompletePin(r, CodePurpose.FirstSetup), ct))
            .Answers(200, 400, 401);
        group.MapPost("/pin-reset/request", (AuthRequest r, PinSetupService s, IAuthUnitOfWork work, CancellationToken ct) => Run(r, work, () => s.Request(r, CodePurpose.PinReset, ct), ct))
            .Answers(202, 400);
        group.MapPost("/pin-reset/verify", (AuthRequest r, PinSetupService s, IAuthUnitOfWork work, CancellationToken ct) => Run(r, work, () => s.VerifyCode(r, CodePurpose.PinReset), ct))
            .Answers(200, 400, 401);
        group.MapPost("/pin-reset/complete", (AuthRequest r, PinSetupService s, IAuthUnitOfWork work, CancellationToken ct) => Run(r, work, () => s.CompletePin(r, CodePurpose.PinReset), ct))
            .Answers(200, 400, 401);
        group.MapPost("/refresh", (AuthRequest r, SessionService s, IAuthUnitOfWork work, CancellationToken ct) => Run(r, work, () => s.Refresh(r), ct))
            .Answers(200, 400, 401);
        group.MapPost("/sign-out", (AuthRequest r, SessionService s, IAuthUnitOfWork work, CancellationToken ct) => Run(r, work, () => s.SignOut(r), ct))
            .Answers(200, 400);
        group.MapPost("/devices/{id}/revoke", async (string id, ClaimsPrincipal principal, SessionService s, IAuthUnitOfWork work, CancellationToken ct) =>
        {
            if (!string.Equals(principal.FindFirstValue("device"), id, StringComparison.Ordinal))
                return Results.Forbid();
            var userId = Guid.Parse(principal.FindFirstValue("sub")!);
            return await Run(new(DeviceId: id), work, () => s.RevokeDevice(userId, id), ct, await s.AccountKey(userId));
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

    private static async Task<IResult> Run(AuthRequest r, IAuthUnitOfWork work, Func<Task<AuthResult>> action, CancellationToken ct, string? lockKey = null)
    {
        if (r.DeviceId is null || r.DeviceId.Length is < 1 or > 128 || r.PhoneNumber is null || r.PhoneNumber.Length > 14 || r.Email is null || r.Email.Length > 320 ||
            (r.Email.Length > 0 && !MailAddress.TryCreate(r.Email, out _)) || r.Pin is null || r.Pin.Length > PinRules.MaximumLength || r.Code is null || r.Code.Length > 32 || r.RefreshToken is null || r.RefreshToken.Length > 256)
            return Results.Json(new AuthResponse("invalid_request"), statusCode: 400);
        var result = await work.Run(lockKey ?? LockKey(r), action, ct);
        return Results.Json(result.Body, statusCode: result.HttpStatus);
    }
}
