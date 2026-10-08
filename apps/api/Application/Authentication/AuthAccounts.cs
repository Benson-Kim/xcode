using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Application.Authentication;

public sealed class AuthAccounts(AuthDb db)
{
    public Task<User?> Find(string phone) => PhoneNumber.Normalize(phone) is { Length: > 0 } number
        ? db.Users.SingleOrDefaultAsync(u => u.PhoneNumber == number)
        : Task.FromResult<User?>(null);

    public static bool Active(User? user) => user is { Status: UserStatus.Active };

    // A first-setup code is for someone without a PIN; a reset code for someone with one.
    public static bool ReadyFor(User? user, CodePurpose purpose) =>
        Active(user) && (purpose == CodePurpose.FirstSetup ? !user!.HasPin : user!.HasPin);

    public static string MaskEmail(string email)
    {
        var at = email.IndexOf('@');
        return at <= 0 ? "***" : $"{email[0]}***{email[at..]}";
    }
}

public sealed class AuthDevices(AuthDb db, IClock clock, AuthOptions options)
{
    public async Task<bool> Trusted(User user, string deviceId)
    {
        var device = await db.TrustedDevices.SingleOrDefaultAsync(d => d.UserId == user.Id && d.DeviceId == deviceId);
        return device is not null && device.IsValid(clock.UtcNow);
    }

    // Only a trusted device learns that the account is paused; anyone else gets the unknown-number answer.
    public async Task<AuthResult> Paused(User user, string deviceId) => await Trusted(user, deviceId)
        ? new(423, new("paused", RetryAfterSeconds: (int)Math.Ceiling((user.PausedUntil!.Value - clock.UtcNow).TotalSeconds)))
        : AuthResult.Failure();

    public async Task Trust(User user, string deviceId)
    {
        var device = await db.TrustedDevices.SingleOrDefaultAsync(d => d.UserId == user.Id && d.DeviceId == deviceId);
        if (device is null)
        {
            device = new()
            {
                UserId = user.Id,
                DeviceId = deviceId
            };
            db.TrustedDevices.Add(device);
        }
        device.Trust(options.TrustLifetimeDays is int days ? clock.UtcNow.AddDays(days) : null);
    }
}

public sealed class AuthPolicy(AuthDb db)
{
    public async Task<OrganizationSecurityPolicy> For(Guid userId)
    {
        var organizationId = await db.Memberships.IgnoreQueryFilters().Where(x => x.UserId == userId && x.Active).Select(x => (Guid?)x.OrganizationId).SingleOrDefaultAsync();
        return organizationId is null ? new() : await ForOrganization(organizationId.Value);
    }

    public async Task<OrganizationSecurityPolicy> ForOrganization(Guid organizationId) => SecurityPolicyBounds.Clamp(
        await db.SecurityPolicies.IgnoreQueryFilters().AsNoTracking().SingleOrDefaultAsync(x => x.OrganizationId == organizationId)) ?? new();
}
