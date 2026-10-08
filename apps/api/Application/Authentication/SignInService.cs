using Auth.Domain;
using Auth.Infrastructure;

namespace Auth.Application.Authentication;

// Sign-in and unlock with a PIN, and the code check that makes a new device trusted.
public sealed class SignInService(AuthAccounts accounts, AuthDevices devices, AuthPolicy policies, AuthCodes codes, SessionTokens sessions, IClock clock)
{
    public const int UntrustedAttemptLimit = 10;

    public async Task<AuthResult> SignIn(AuthRequest request, CancellationToken ct)
    {
        var user = await accounts.Find(request.PhoneNumber);

        var correct = PinHasher.Verify(request.Pin, user?.PinHash ?? PinHasher.DummyHash);

        if (!AuthAccounts.Active(user) || !user!.HasPin)
            return AuthResult.Failure();

        if (user.PausedUntil is not null && clock.UtcNow >= user.PausedUntil)
            user.ClearLockout();

        if (user.IsPaused(clock.UtcNow))
            return await devices.Paused(user, request.DeviceId);

        var isTrusted = await devices.Trusted(user, request.DeviceId);

        if (!isTrusted && user.UntrustedFailedAttempts >= UntrustedAttemptLimit)
            return AuthResult.Failure();

        if (!correct)
        {
            if (isTrusted)
            {
                var policy = await policies.For(user.Id);
                user.RecordFailedAttempt();
                if (user.FailedAttempts < policy.LockoutThreshold)
                    return AuthResult.Failure();
                user.Pause(clock.UtcNow.AddMinutes(policy.LockoutMinutes));
                return await devices.Paused(user, request.DeviceId);
            }
            user.RecordUntrustedFailedAttempt();
            return AuthResult.Failure();
        }
        if (!isTrusted)
        {
            var issued = await codes.Issue(user, request.DeviceId, CodePurpose.NewDevice, ct);
            return new(202,
                new("verification_required",
                    DevelopmentCode: issued?.DevelopmentCode,
                    MaskedEmail: AuthAccounts.MaskEmail(user.Email)))
            { Mail = issued?.Mail };
        }
        user.ClearLockout();
        return await sessions.Issue(user, request.DeviceId);
    }

    public async Task<AuthResult> VerifyDevice(AuthRequest request)
    {
        var user = await accounts.Find(request.PhoneNumber);
        if (!AuthAccounts.Active(user) || !user!.HasPin || user.IsPaused(clock.UtcNow))
            return AuthResult.Failure();

        if (!await codes.Consume(user, request, CodePurpose.NewDevice))
            return AuthResult.Failure();

        user.ClearLockout();
        user.ClearUntrustedFailedAttempts();
        await devices.Trust(user, request.DeviceId);

        return await sessions.Issue(user, request.DeviceId);
    }
}
