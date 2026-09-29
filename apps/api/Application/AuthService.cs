using System.Security.Cryptography;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Application;

public sealed class AuthService(AuthDb db, IClock clock, VerificationMailer mailer, TokenIssuer tokens, AuthOptions options, EffectivePermissionResolver permissionResolver, IHostEnvironment environment,
    IOrganizationContext context)
{
    // A code issued in this request, sent by Deliver only after the endpoint has committed it.
    private VerificationMailer.Message? outgoing;

    // Input that is not a phone number normalizes to "", which is also what accounts made before phone sign-in still
    // hold, so it must match no account at all.
    private Task<User?> Find(string phone) => PhoneNumber.Normalize(phone) is { Length: > 0 } number
        ? db.Users.SingleOrDefaultAsync(u => u.PhoneNumber == number)
        : Task.FromResult<User?>(null);
    private bool Active(User? user) => user is { Status: UserStatus.Active };
    private void ClearPause(User user)
    {
        user.FailedAttempts = 0;
        user.PausedUntil = null;
    }
    private async Task<bool> Trusted(User user, string deviceId)
    {
        var device = await db.TrustedDevices.SingleOrDefaultAsync(d => d.UserId == user.Id && d.DeviceId == deviceId);
        return device is { Revoked: false } && (device.TrustExpiresAt is null || clock.UtcNow < device.TrustExpiresAt);
    }
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
        device.Revoked = false;
        device.TrustExpiresAt = options.TrustLifetimeDays is int days ? clock.UtcNow.AddDays(days) : null;
    }

    private async Task<string?> IssueCode(User user, string deviceId, CodePurpose purpose, CancellationToken ct)
    {
        var existing = await db.VerificationCodes.Where(c => c.UserId == user.Id && c.Purpose == purpose).ToListAsync(ct);
        // Account-level resend cooldown; requesting on a different device cannot bypass it. A code withdrawn because
        // it could not be sent never reached anyone, so it does not start the cooldown.
        if (!environment.IsDevelopment() && existing.Any(c => !VerificationMailer.Withdrawn(c) && c.CreatedAt.AddMinutes(1) > clock.UtcNow)) return null;

        foreach (var old in existing) old.Consumed = true;
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
        return environment.IsDevelopment() ? code : null;
    }

    // Sends the code issued in this request. The endpoint calls this after the code is committed and the auth gate is
    // released, so a failed commit sends nothing and a slow mail server holds up no one else's sign-in. A code that
    // cannot be sent is withdrawn, so a retry can send a new one at once.
    // Setup and reset requests reply before the mail server is involved: anyone can make them for any number, and only
    // a real account sends mail, so waiting for it (or reporting its failure) would reveal which numbers have one.
    // Only a caller who has already proven the PIN (a new-device sign-in) waits, and is told if the service is down.
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
    // Every wrong guess counts, whether or not the check consumes the code, so each challenge allows five guesses in total.
    private async Task<VerificationCode?> Matching(User user, AuthRequest request, CodePurpose purpose)
    {
        var codes = await db.VerificationCodes.Where(c => c.UserId == user.Id && c.DeviceId == request.DeviceId && c.Purpose == purpose && !c.Consumed).ToListAsync();
        var code = codes.OrderByDescending(c => c.CreatedAt).FirstOrDefault();

        if (code is null || clock.UtcNow > code.ExpiresAt || code.FailedAttempts >= 5) return null;
        if (!CryptographicOperations.FixedTimeEquals(Convert.FromHexString(code.CodeHash), Convert.FromHexString(tokens.Hash(request.Code))))
        {
            code.FailedAttempts++;
            if (code.FailedAttempts >= 5) code.Consumed = true;
            return null;
        }
        return code;
    }
    private async Task<bool> Consume(User user, AuthRequest request, CodePurpose purpose)
    {
        var code = await Matching(user, request, purpose);
        if (code is null) return false;
        code.Consumed = true;
        return true;
    }

    // Pre-checks the code for the setup/reset screens; the complete step still needs it, so it is not consumed.
    public async Task<AuthResult> VerifyCode(AuthRequest request, CodePurpose purpose)
    {
        var user = await Find(request.PhoneNumber);
        var correctPurpose = purpose == CodePurpose.FirstSetup
            ? user?.PinHash is null
            : user?.PinHash is not null;
        if (!Active(user) || !correctPurpose || await Matching(user!, request, purpose) is null)
            return AuthResult.Failure();
        return new(200, new("code_verified"));
    }

    // The policy of the organization the person belongs to; defaults until they have a membership. A row saved under an
    // earlier version's wider bounds is enforced within the current ones.
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

        // The role's standard permissions come only from the catalog, as they do for request-time checks.
        var permissions = permissionResolver.Resolve(PermissionCatalog.DefaultsFor(role.Name), overrides, membership.Active);

        ClearPause(user);

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

        if (!Active(user) || user!.PinHash is null)
            return AuthResult.Failure();

        if (user.PausedUntil is not null && clock.UtcNow >= user.PausedUntil)
            ClearPause(user);

        // The timer is shown only on a device this account already trusts (Phase 1 phones rely on it). Anywhere else a
        // paused account answers exactly like a number with no account, or anyone could find which numbers exist.
        if (user.PausedUntil > clock.UtcNow)
            return await Trusted(user, request.DeviceId)
                ? new(423,
                    new("paused",
                        RetryAfterSeconds: (int)Math.Ceiling(
                            (user.PausedUntil.Value - clock.UtcNow).TotalSeconds)
                        ))
                : AuthResult.Failure();

        if (!correct)
        {
            var policy = await Policy(user.Id);
            user.FailedAttempts++;
            if (user.FailedAttempts >= policy.LockoutThreshold)
                user.PausedUntil = clock.UtcNow.AddMinutes(policy.LockoutMinutes);

            return AuthResult.Failure();
        }
        if (!await Trusted(user, request.DeviceId))
        {
            var code = await IssueCode(user, request.DeviceId, CodePurpose.NewDevice, ct);
            return new(202,
                new("verification_required",
                    DevelopmentCode: code,
                    MaskedEmail: MaskEmail(user.Email))
                );
        }
        return await IssueTokens(user, request.DeviceId);
    }

    public async Task<AuthResult> VerifyDevice(AuthRequest request)
    {
        var user = await Find(request.PhoneNumber);
        if (!Active(user) || user!.PinHash is null || user.PausedUntil > clock.UtcNow)
            return AuthResult.Failure();

        if (!await Consume(user, request, CodePurpose.NewDevice))
            return AuthResult.Failure();

        await Trust(user, request.DeviceId);

        return await IssueTokens(user, request.DeviceId);
    }
    public async Task<AuthResult> RequestPin(AuthRequest request, CodePurpose purpose, CancellationToken ct)
    {
        var user = await Find(request.PhoneNumber);
        string? code = null;
        if (Active(user) &&
            (purpose == CodePurpose.FirstSetup ? user!.PinHash is null : user!.PinHash is not null))
            code = await IssueCode(user!, request.DeviceId, purpose, ct);
        // Identical body/status for unknown, removed and existing accounts: no masked email here,
        // because anyone can call this with any number. (DevelopmentCode only exists in Development.)
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
            ? user?.PinHash is null
            : user?.PinHash is not null;
        if (!Active(user) || !correctPurpose)
            return AuthResult.Failure();
        // The organization's minimum is only disclosed to someone holding a valid code, so it cannot reveal which numbers are registered.
        var policy = await Policy(user!.Id);
        if (request.Pin.Length < policy.PinLength)
            return await Matching(user, request, purpose) is null ?
                AuthResult.Failure() :
                AuthResult.InvalidPin(policy.PinLength);

        if (!await Consume(user, request, purpose))
            return AuthResult.Failure();

        user!.PinHash = PinHasher.Hash(request.Pin);
        user.SecurityVersion++;
        ClearPause(user);
        await RevokeTokens(user.Id);
        // A reset invalidates any outstanding challenge created with the previous PIN.
        foreach (var code in await db.VerificationCodes.Where(c => c.UserId == user.Id && !c.Consumed).ToListAsync())
            code.Consumed = true;
        await Trust(user, request.DeviceId);

        return await IssueTokens(user, request.DeviceId);
    }
    private async Task RevokeTokens(Guid userId, string? deviceId = null)
    {
        var list = await db.RefreshTokens
            .Where(t => t.UserId == userId && !t.Revoked && (deviceId == null || t.DeviceId == deviceId))
            .ToListAsync();
        foreach (var token in list)
            token.Revoked = true;
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
            // Reuse of a rotated token revokes this device's session family.
            await RevokeTokens(token.UserId, token.DeviceId);
            return AuthResult.Failure();
        }
        if (clock.UtcNow >= token.ExpiresAt || user!.PausedUntil > clock.UtcNow || !await Trusted(user, request.DeviceId))
            return AuthResult.Failure();

        token.Revoked = true;
        // Refresh is not a PIN sign-in and must not clear accumulated PIN failures.
        var failures = user.FailedAttempts;
        var pause = user.PausedUntil;
        var result = await IssueTokens(user, request.DeviceId);
        user.FailedAttempts = failures;
        user.PausedUntil = pause;
        return result;
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
            device.Revoked = true;

        await RevokeTokens(userId, deviceId);

        foreach (var code in await db.VerificationCodes.Where(c => c.UserId == userId && c.DeviceId == deviceId && !c.Consumed).ToListAsync())
            code.Consumed = true;
        return new(200, new("device_revoked"));
    }
}
