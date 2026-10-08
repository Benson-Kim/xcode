using Auth.Domain;
using Auth.Infrastructure;

namespace Auth.Application.Authentication;

// Emailed codes for a first PIN or a PIN reset, and setting the PIN once the code checks out.
public sealed class PinSetupService(AuthAccounts accounts, AuthDevices devices, AuthPolicy policies, AuthCodes codes, SessionTokens sessions)
{
    // Answers the same whether or not the number has an account.
    public async Task<AuthResult> Request(AuthRequest request, CodePurpose purpose, CancellationToken ct)
    {
        var user = await accounts.Find(request.PhoneNumber);
        var issued = AuthAccounts.ReadyFor(user, purpose) ? await codes.Issue(user!, request.DeviceId, purpose, ct) : null;
        return new(202, new("check_email", DevelopmentCode: issued?.DevelopmentCode)) { Mail = issued?.Mail };
    }

    public async Task<AuthResult> VerifyCode(AuthRequest request, CodePurpose purpose)
    {
        var user = await accounts.Find(request.PhoneNumber);
        if (!AuthAccounts.ReadyFor(user, purpose) || await codes.Matching(user!, request, purpose) is null)
            return AuthResult.Failure();
        return new(200, new("code_verified"));
    }

    public async Task<AuthResult> CompletePin(AuthRequest request, CodePurpose purpose)
    {
        if (!PinRules.IsValid(request.Pin)) return AuthResult.InvalidPin(PinRules.MinimumLength);

        var user = await accounts.Find(request.PhoneNumber);
        if (!AuthAccounts.ReadyFor(user, purpose))
            return AuthResult.Failure();
        var policy = await policies.For(user!.Id);
        if (request.Pin.Length < policy.PinLength)
            return await codes.Matching(user, request, purpose) is null ?
                AuthResult.Failure() :
                AuthResult.InvalidPin(policy.PinLength);

        if (!await codes.Consume(user, request, purpose))
            return AuthResult.Failure();

        user.SetPin(PinHasher.Hash(request.Pin));
        user.ClearLockout();
        await sessions.Revoke(user.Id);
        await codes.ConsumeAll(user.Id);
        await devices.Trust(user, request.DeviceId);

        return await sessions.Issue(user, request.DeviceId);
    }
}
