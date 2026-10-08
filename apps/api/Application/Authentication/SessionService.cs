using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Application.Authentication;

// Refresh-token rotation, sign-out and revoking this device.
public sealed class SessionService(AuthDb db, AuthDevices devices, AuthCodes codes, SessionTokens sessions, TokenIssuer tokens, IClock clock)
{
    public async Task<AuthResult> Refresh(AuthRequest request)
    {
        var hash = tokens.Hash(request.RefreshToken);
        var token = await db.RefreshTokens
            .SingleOrDefaultAsync(t => t.TokenHash == hash);

        if (token is null || token.DeviceId != request.DeviceId)
            return AuthResult.Failure();

        var user = await db.Users.FindAsync(token.UserId);

        if (!AuthAccounts.Active(user))
        {
            await sessions.Revoke(token.UserId);
            return AuthResult.Failure();
        }
        // A revoked token coming back means it was copied: end every session on that device.
        if (token.Revoked)
        {
            await sessions.Revoke(token.UserId, token.DeviceId);
            return AuthResult.Failure();
        }
        if (clock.UtcNow >= token.ExpiresAt || user!.IsPaused(clock.UtcNow) || !await devices.Trusted(user, request.DeviceId))
            return AuthResult.Failure();

        token.Revoke();
        return await sessions.Issue(user, request.DeviceId);
    }

    public async Task<AuthResult> SignOut(AuthRequest request)
    {
        var hash = tokens.Hash(request.RefreshToken);
        var token = await db.RefreshTokens
            .SingleOrDefaultAsync(t => t.TokenHash == hash && t.DeviceId == request.DeviceId);
        if (token is not null)
            await sessions.Revoke(token.UserId, token.DeviceId);
        return new(200, new("signed_out"));
    }

    public async Task<AuthResult> RevokeDevice(Guid userId, string deviceId)
    {
        var device = await db.TrustedDevices
            .SingleOrDefaultAsync(d => d.UserId == userId && d.DeviceId == deviceId);
        if (device is not null)
            device.Revoke();

        await sessions.Revoke(userId, deviceId);
        await codes.ConsumeAll(userId, deviceId);
        return new(200, new("device_revoked"));
    }

    // The account's own lock key (its phone number), so revoking a device waits for the account's other auth work.
    public async Task<string?> AccountKey(Guid userId) =>
        await db.Users.FindAsync(userId) is { } user ? PhoneNumber.Normalize(user.PhoneNumber) : null;
}
