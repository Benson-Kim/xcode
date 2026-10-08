using System.Security.Cryptography;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Application.Authentication;

public sealed class SessionTokens(AuthDb db, IClock clock, TokenIssuer tokens, EffectivePermissionResolver permissionResolver, AuthPolicy policies)
{
    // Leaves the account's lockout alone: callers clear it when the person has proved who they are.
    public async Task<AuthResult> Issue(User user, string deviceId)
    {
        var membership = await db.Memberships
            .IgnoreQueryFilters()
            .SingleOrDefaultAsync(x => x.UserId == user.Id && x.Active);

        if (membership is not { Active: true })
            return AuthResult.Failure();

        var policy = await policies.ForOrganization(membership.OrganizationId);
        var roleLink = await db.PersonRoles
            .IgnoreQueryFilters()
            .SingleOrDefaultAsync(x => x.OrganizationId == membership.OrganizationId && x.UserId == user.Id);
        var role = roleLink is null ?
            null :
            await db.Roles
                .IgnoreQueryFilters()
                .SingleOrDefaultAsync(x => x.OrganizationId == membership.OrganizationId && x.Id == roleLink.RoleId);

        if (role is null)
            return AuthResult.Failure();

        var overrides = await db.PermissionOverrides
            .IgnoreQueryFilters()
            .Where(x => x.OrganizationId == membership.OrganizationId && x.UserId == user.Id)
            .ToListAsync();

        var permissions = permissionResolver.Resolve(PermissionCatalog.DefaultsFor(role.Name), overrides, membership.Active);

        var raw = Convert.ToBase64String(RandomNumberGenerator.GetBytes(48));

        db.RefreshTokens.Add(new()
        {
            UserId = user.Id,
            DeviceId = deviceId,
            TokenHash = tokens.Hash(raw),
            ExpiresAt = clock.UtcNow.AddDays(policy.RefreshTokenDays)
        });
        return new(200,
            new(
                "authenticated",
                tokens.Access(
                    user,
                    deviceId,
                    membership.OrganizationId,
                    role.Name,
                    membership.FirstName,
                    membership.LastName,
                    permissions,
                    TimeSpan.FromMinutes(policy.AccessTokenMinutes)),
                raw)
            );
    }

    public async Task Revoke(Guid userId, string? deviceId = null)
    {
        var list = await db.RefreshTokens
            .Where(t => t.UserId == userId && !t.Revoked && (deviceId == null || t.DeviceId == deviceId))
            .ToListAsync();
        foreach (var token in list)
            token.Revoke();
    }
}
