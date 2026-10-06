using System.Security.Cryptography;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Application;

public sealed class AuthService(AuthDb db, IClock clock, VerificationMailer mailer, TokenIssuer tokens, AuthOptions options, EffectivePermissionResolver permissionResolver,
    IOrganizationContext context)
{
    private VerificationMailer.Message? outgoing;

    private Task<User?> Find(string phone) => PhoneNumber.Normalize(phone) is { Length: > 0 } number
        ? db.Users.SingleOrDefaultAsync(u => u.PhoneNumber == number)
        : Task.FromResult<User?>(null);
    private bool Active(User? user) => user is { Status: UserStatus.Active };

    private async Task<bool> Trusted(User user, string deviceId)
    {
        var device = await db.TrustedDevices.SingleOrDefaultAsync(d => d.UserId == user.Id && d.DeviceId == deviceId);
        return device is not null && device.IsValid(clock.UtcNow);
    }

    private async Task<AuthResult> Paused(User user, string deviceId) => await Trusted(user, deviceId)
        ? new(423, new("paused", RetryAfterSeconds: (int)Math.Ceiling((user.PausedUntil!.Value - clock.UtcNow).TotalSeconds)))
        : AuthResult.Failure();
    private async Task Trust(User user, string deviceId)
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

    public const int HourlyCodeLimit = 5;
    public const int DailyCodeLimit = 10;
    public const int UntrustedAttemptLimit = 10;

    private async Task<string?> IssueCode(User user, string deviceId, CodePurpose purpose, CancellationToken ct)
    {
        var existing = await db.VerificationCodes.Where(c => c.UserId == user.Id && c.Purpose == purpose).ToListAsync(ct);
        if (!options.DevelopmentMode && existing.Any(c => !c.IsWithdrawn && c.CreatedAt.AddMinutes(1) > clock.UtcNow)) return null;

        var allCodes = await db.VerificationCodes.Where(c => c.UserId == user.Id).ToListAsync(ct);
        var nonWithdrawn = allCodes.Where(c => !c.IsWithdrawn).ToList();
        if (nonWithdrawn.Count(c => c.CreatedAt > clock.UtcNow.AddHours(-1)) >= HourlyCodeLimit) return null;
        if (nonWithdrawn.Count(c => c.CreatedAt > clock.UtcNow.AddHours(-24)) >= DailyCodeLimit) return null;

        foreach (var old in existing) old.Consume();
        var code = RandomNumberGenerator.GetInt32(0, 1_000_000).ToString("D6");

        var issued = new VerificationCode
        {
            UserId = user.Id,
            DeviceId = deviceId,
            Purpose = purpose,
            CodeHash = tokens.Hash(code),
            CreatedAt = clock.UtcNow,
            ExpiresAt = clock.UtcNow.AddMinutes(10)
        };
        db.VerificationCodes.Add(issued);
        outgoing = new(issued.Id, user.Id, user.Email, code, purpose, context.CorrelationId);
        return options.DevelopmentMode ? code : null;
    }

    public async Task<AuthResult> Deliver(AuthResult result, CancellationToken ct)
    {
        if (outgoing is not { } message)
            return result;
        outgoing = null;
        if (message.Purpose != CodePurpose.NewDevice)
        {
            mailer.SendLater(message);
            return result;
        }
        return await mailer.Send(message, ct) ? result : new(503, new("service_unavailable"));
    }

    private async Task<VerificationCode?> Matching(User user, AuthRequest request, CodePurpose purpose)
    {
        var codes = await db.VerificationCodes.Where(c => c.UserId == user.Id && c.DeviceId == request.DeviceId && c.Purpose == purpose && !c.Consumed).ToListAsync();
        var code = codes.OrderByDescending(c => c.CreatedAt).FirstOrDefault();

        if (code is null || !code.IsUsable(clock.UtcNow)) return null;
        if (!CryptographicOperations.FixedTimeEquals(Convert.FromHexString(code.CodeHash), Convert.FromHexString(tokens.Hash(request.Code))))
        {
            code.RecordFailedAttempt();
            return null;
        }
        return code;
    }
    private async Task<bool> Consume(User user, AuthRequest request, CodePurpose purpose)
    {
        var code = await Matching(user, request, purpose);
        if (code is null) return false;
        code.Consume();
        return true;
    }

    public async Task<AuthResult> VerifyCode(AuthRequest request, CodePurpose purpose)
    {
        var user = await Find(request.PhoneNumber);
        var correctPurpose = purpose == CodePurpose.FirstSetup
            ? !user?.HasPin ?? false
            : user?.HasPin ?? false;
        if (!Active(user) || !correctPurpose || await Matching(user!, request, purpose) is null)
            return AuthResult.Failure();
        return new(200, new("code_verified"));
    }

    private async Task<OrganizationSecurityPolicy> Policy(Guid userId)
    {
        var organizationId = await db.Memberships.IgnoreQueryFilters().Where(x => x.UserId == userId && x.Active).Select(x => (Guid?)x.OrganizationId).SingleOrDefaultAsync();
        return organizationId is null ? new() : await PolicyOf(organizationId.Value);
    }

    private async Task<OrganizationSecurityPolicy> PolicyOf(Guid organizationId) => SecurityPolicyBounds.Clamp(
        await db.SecurityPolicies.IgnoreQueryFilters().AsNoTracking().SingleOrDefaultAsync(x => x.OrganizationId == organizationId)) ?? new();

    private async Task<AuthResult> IssueTokens(User user, string deviceId)
    {
        var membership = await db.Memberships
            .IgnoreQueryFilters()
            .SingleOrDefaultAsync(x => x.UserId == user.Id && x.Active);

        if (membership is not { Active: true })
            return AuthResult.Failure();

        var policy = await PolicyOf(membership.OrganizationId);
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
    public async Task<AuthResult> SignIn(AuthRequest request, CancellationToken ct)
    {
        var user = await Find(request.PhoneNumber);

        var correct = PinHasher.Verify(request.Pin, user?.PinHash ?? PinHasher.DummyHash);

        if (!Active(user) || !user!.HasPin)
            return AuthResult.Failure();

        if (user.PausedUntil is not null && clock.UtcNow >= user.PausedUntil)
            user.ClearLockout();

        if (user.IsPaused(clock.UtcNow))
            return await Paused(user, request.DeviceId);

        var isTrusted = await Trusted(user, request.DeviceId);

        if (!isTrusted && user.UntrustedFailedAttempts >= UntrustedAttemptLimit)
            return AuthResult.Failure();

        if (!correct)
        {
            if (isTrusted)
            {
                var policy = await Policy(user.Id);
                user.RecordFailedAttempt();
                if (user.FailedAttempts < policy.LockoutThreshold)
                    return AuthResult.Failure();
                user.Pause(clock.UtcNow.AddMinutes(policy.LockoutMinutes));
                return await Paused(user, request.DeviceId);
            }
            user.RecordUntrustedFailedAttempt();
            return AuthResult.Failure();
        }
        if (!isTrusted)
        {
            var code = await IssueCode(user, request.DeviceId, CodePurpose.NewDevice, ct);
            return new(202,
                new("verification_required",
                    DevelopmentCode: code,
                    MaskedEmail: MaskEmail(user.Email))
                );
        }
        user.ClearLockout();
        return await IssueTokens(user, request.DeviceId);
    }

    public async Task<AuthResult> VerifyDevice(AuthRequest request)
    {
        var user = await Find(request.PhoneNumber);
        if (!Active(user) || !user!.HasPin || user.IsPaused(clock.UtcNow))
            return AuthResult.Failure();

        if (!await Consume(user, request, CodePurpose.NewDevice))
            return AuthResult.Failure();

        user.ClearLockout();
        user.ClearUntrustedFailedAttempts();
        await Trust(user, request.DeviceId);

        return await IssueTokens(user, request.DeviceId);
    }
    public async Task<AuthResult> RequestPin(AuthRequest request, CodePurpose purpose, CancellationToken ct)
    {
        var user = await Find(request.PhoneNumber);
        string? code = null;
        if (Active(user) &&
            (purpose == CodePurpose.FirstSetup ? !user!.HasPin : user!.HasPin))
            code = await IssueCode(user!, request.DeviceId, purpose, ct);
        return new(202, new("check_email", DevelopmentCode: code));
    }

    private static string MaskEmail(string email)
    {
        var at = email.IndexOf('@');
        return at <= 0 ? "***" : $"{email[0]}***{email[at..]}";
    }
    public async Task<AuthResult> CompletePin(AuthRequest request, CodePurpose purpose)
    {
        if (!PinRules.IsValid(request.Pin)) return AuthResult.InvalidPin(PinRules.MinimumLength);

        var user = await Find(request.PhoneNumber);
        var correctPurpose = purpose == CodePurpose.FirstSetup
            ? !user?.HasPin ?? false
            : user?.HasPin ?? false;
        if (!Active(user) || !correctPurpose)
            return AuthResult.Failure();
        var policy = await Policy(user!.Id);
        if (request.Pin.Length < policy.PinLength)
            return await Matching(user, request, purpose) is null ?
                AuthResult.Failure() :
                AuthResult.InvalidPin(policy.PinLength);

        if (!await Consume(user, request, purpose))
            return AuthResult.Failure();

        user.SetPin(PinHasher.Hash(request.Pin));
        user.ClearLockout();
        await RevokeTokens(user.Id);
        foreach (var code in await db.VerificationCodes.Where(c => c.UserId == user.Id && !c.Consumed).ToListAsync())
            code.Consume();
        await Trust(user, request.DeviceId);

        return await IssueTokens(user, request.DeviceId);
    }
    private async Task RevokeTokens(Guid userId, string? deviceId = null)
    {
        var list = await db.RefreshTokens
            .Where(t => t.UserId == userId && !t.Revoked && (deviceId == null || t.DeviceId == deviceId))
            .ToListAsync();
        foreach (var token in list)
            token.Revoke();
    }
    public async Task<AuthResult> Refresh(AuthRequest request)
    {
        var hash = tokens.Hash(request.RefreshToken);
        var token = await db.RefreshTokens
            .SingleOrDefaultAsync(t => t.TokenHash == hash);

        if (token is null || token.DeviceId != request.DeviceId)
            return AuthResult.Failure();

        var user = await db.Users.FindAsync(token.UserId);

        if (!Active(user))
        {
            await RevokeTokens(token.UserId);
            return AuthResult.Failure();
        }
        if (token.Revoked)
        {
            await RevokeTokens(token.UserId, token.DeviceId);
            return AuthResult.Failure();
        }
        if (clock.UtcNow >= token.ExpiresAt || user!.IsPaused(clock.UtcNow) || !await Trusted(user, request.DeviceId))
            return AuthResult.Failure();

        token.Revoke();
        return await IssueTokens(user, request.DeviceId);
    }

    public async Task<AuthResult> SignOut(AuthRequest request)
    {
        var hash = tokens.Hash(request.RefreshToken);
        var token = await db.RefreshTokens
            .SingleOrDefaultAsync(t => t.TokenHash == hash && t.DeviceId == request.DeviceId);
        if (token is not null)
            await RevokeTokens(token.UserId, token.DeviceId);
        return new(200, new("signed_out"));
    }
    public async Task<AuthResult> RevokeDevice(Guid userId, string deviceId)
    {
        var device = await db.TrustedDevices
            .SingleOrDefaultAsync(d => d.UserId == userId && d.DeviceId == deviceId);
        if (device is not null)
            device.Revoke();

        await RevokeTokens(userId, deviceId);

        foreach (var code in await db.VerificationCodes.Where(c => c.UserId == userId && c.DeviceId == deviceId && !c.Consumed).ToListAsync())
            code.Consume();
        return new(200, new("device_revoked"));
    }
}
