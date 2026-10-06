using System.Diagnostics.CodeAnalysis;
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using Auth.Application;
using Auth.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;

namespace Auth.Infrastructure;

public sealed class SystemClock : IClock { public DateTimeOffset UtcNow => DateTimeOffset.UtcNow; }

public readonly record struct PolicyBound(string Column, int Min, int Max)
{
    public int Clamp(int value) => Math.Clamp(value, Min, Max);
}

// The numeric bounds of an organization's security policy, as OrganizationSecurityPolicy.Validate enforces them when a
// policy is saved. Earlier versions allowed wider ones (a lockout after one try, a pause of up to a day), so the
// database checks these too (migration NormalizeSecurityPolicy), and everything that reads a policy clamps to them.
public static class SecurityPolicyBounds
{
    public static readonly PolicyBound PasswordMinLength = new(nameof(OrganizationSecurityPolicy.PasswordMinLength), 12, 128);
    public static readonly PolicyBound PasswordHistory = new(nameof(OrganizationSecurityPolicy.PasswordHistory), 0, 24);
    public static readonly PolicyBound PinLength = new(nameof(OrganizationSecurityPolicy.PinLength), 4, 8);
    public static readonly PolicyBound LockoutThreshold = new(nameof(OrganizationSecurityPolicy.LockoutThreshold), 3, 10);
    public static readonly PolicyBound LockoutMinutes = new(nameof(OrganizationSecurityPolicy.LockoutMinutes), 1, 60);
    public static readonly PolicyBound AccessTokenMinutes = new(nameof(OrganizationSecurityPolicy.AccessTokenMinutes), 1, 15);
    public static readonly PolicyBound RefreshTokenDays = new(nameof(OrganizationSecurityPolicy.RefreshTokenDays), 1, 90);
    public static readonly PolicyBound IdleUnlockSeconds = new(nameof(OrganizationSecurityPolicy.IdleUnlockSeconds), 30, 3600);

    public static readonly IReadOnlyList<PolicyBound> All =
        [PasswordMinLength, PasswordHistory, PinLength, LockoutThreshold, LockoutMinutes, AccessTokenMinutes, RefreshTokenDays, IdleUnlockSeconds];

    // Brings a policy into bounds in place. Pass only a policy read without tracking, so the change is never saved.
    [return: NotNullIfNotNull(nameof(policy))]
    public static OrganizationSecurityPolicy? Clamp(OrganizationSecurityPolicy? policy)
    {
        if (policy is null)
            return null;
        policy.PasswordMinLength = PasswordMinLength.Clamp(policy.PasswordMinLength);
        policy.PasswordHistory = PasswordHistory.Clamp(policy.PasswordHistory);
        policy.PinLength = PinLength.Clamp(policy.PinLength);
        policy.LockoutThreshold = LockoutThreshold.Clamp(policy.LockoutThreshold);
        policy.LockoutMinutes = LockoutMinutes.Clamp(policy.LockoutMinutes);
        policy.AccessTokenMinutes = AccessTokenMinutes.Clamp(policy.AccessTokenMinutes);
        policy.RefreshTokenDays = RefreshTokenDays.Clamp(policy.RefreshTokenDays);
        policy.IdleUnlockSeconds = IdleUnlockSeconds.Clamp(policy.IdleUnlockSeconds);
        return policy;
    }
}

public static class PinHasher
{
    private const int Iterations = 210_000;
    // Also used for nonexistent users to avoid a cheap account-discovery timing path.
    public static readonly string DummyHash = Hash("5826");
    public static string Hash(string pin)
    {
        var salt = RandomNumberGenerator.GetBytes(16);
        var hash = Rfc2898DeriveBytes.Pbkdf2(pin, salt, Iterations, HashAlgorithmName.SHA256, 32);
        return $"{Convert.ToBase64String(salt)}.{Convert.ToBase64String(hash)}";
    }
    public static bool Verify(string pin, string hash)
    {
        var parts = hash.Split('.');
        var actual = Rfc2898DeriveBytes.Pbkdf2(pin, Convert.FromBase64String(parts[0]), Iterations, HashAlgorithmName.SHA256, 32);
        return CryptographicOperations.FixedTimeEquals(actual, Convert.FromBase64String(parts[1]));
    }
}

public sealed class TokenIssuer(AuthOptions options, IClock clock)
{
    public string Hash(string value) => Convert.ToHexString(HMACSHA256.HashData(Encoding.UTF8.GetBytes(options.SigningKey), Encoding.UTF8.GetBytes(value)));
    public string Access(User user, string deviceId, Guid organizationId, string role, string firstName, string lastName, IEnumerable<string> permissions, TimeSpan lifetime)
    {
        var claims = new List<Claim>
        {
            new("sub", user.Id.ToString()), new("device", deviceId), new("version", user.SecurityVersion.ToString()),
            new("org", organizationId.ToString()), new("role", role), new("first_name", firstName), new("last_name", lastName)
        };
        claims.AddRange(permissions.Select(permission => new Claim("permission", permission)));
        var jwt = new JwtSecurityToken(options.Issuer, options.Audience,
            claims,
            clock.UtcNow.UtcDateTime, clock.UtcNow.Add(lifetime).UtcDateTime,
            new SigningCredentials(new SymmetricSecurityKey(Encoding.UTF8.GetBytes(options.SigningKey)), SecurityAlgorithms.HmacSha256));
        return new JwtSecurityTokenHandler().WriteToken(jwt);
    }
}

// Development only: never register this sender in production.
public sealed class LogEmailSender(ILogger<LogEmailSender> logger) : IEmailSender
{
    public Task SendCode(string email, string code, CodePurpose purpose, CancellationToken cancellationToken)
    {
        logger.LogInformation("DEV EMAIL to {Email}: {Purpose} verification code {Code} (10 minutes)", email, purpose, code);
        return Task.CompletedTask;
    }
}

public sealed class SmtpEmailSender(IConfiguration config) : IEmailSender
{
    public async Task SendCode(string email, string code, CodePurpose purpose, CancellationToken cancellationToken)
    {
        using var client = new System.Net.Mail.SmtpClient(config["Email:Host"] ?? throw new InvalidOperationException("Email:Host required"), config.GetValue("Email:Port", 587));
        client.EnableSsl = true;
        client.Credentials = new System.Net.NetworkCredential(config["Email:Username"], config["Email:Password"]);
        using var message = new System.Net.Mail.MailMessage(config["Email:From"] ?? throw new InvalidOperationException("Email:From required"), email,
            "Your verification code", $"Your {purpose} code is {code}. It expires in 10 minutes.");
        await client.SendMailAsync(message, cancellationToken);
    }
}

// Sends verification codes, each in a scope of its own. A code that cannot be sent is withdrawn: consumed, and valid for
// no time at all, so it can never be used and does not start the resend cooldown. SendLater sends after the reply has
// gone, so how long a setup or reset request takes does not reveal whether the number has an account.
public sealed class VerificationMailer(IServiceScopeFactory scopes, ILogger<VerificationMailer> logger)
{
    public sealed record Message(Guid CodeId, Guid UserId, string Email, string Code, CodePurpose Purpose, string CorrelationId);

    private readonly Lock gate = new();
    private readonly HashSet<Task> sending = [];

    public static bool Withdrawn(VerificationCode code) => code.IsWithdrawn;

    // Sends now. False when the code could not be sent, and has been withdrawn.
    public async Task<bool> Send(Message message, CancellationToken ct)
    {
        await using var scope = scopes.CreateAsyncScope();
        try
        {
            await scope.ServiceProvider.GetRequiredService<IEmailSender>().SendCode(message.Email, message.Code, message.Purpose, ct);
            return true;
        }
        catch (Exception error)
        {
            logger.LogError(error, "A {Purpose} code for user {UserId} could not be sent and was withdrawn (correlation {CorrelationId}).",
                message.Purpose, message.UserId, message.CorrelationId);
            await Withdraw(scope.ServiceProvider.GetRequiredService<AuthDb>(), message);
            return false;
        }
    }

    public void SendLater(Message message)
    {
        Task task;
        // The send outlives the request, so it must not carry the request's context (HttpContext and so on) with it.
        using (ExecutionContext.SuppressFlow())
            task = Task.Run(() => Send(message, CancellationToken.None));
        lock (gate) sending.Add(task);
        _ = task.ContinueWith(done => { lock (gate) sending.Remove(done); }, TaskScheduler.Default);
    }

    // Completes once every code handed to SendLater so far has been sent or withdrawn (shutdown and tests wait on it).
    public Task Idle()
    {
        lock (gate) return Task.WhenAll(sending);
    }

    private async Task Withdraw(AuthDb db, Message message)
    {
        try
        {
            var code = await db.VerificationCodes.SingleOrDefaultAsync(x => x.Id == message.CodeId);
            if (code is null)
                return;
            code.Withdraw();
            await db.SaveChangesAsync();
        }
        catch (Exception error)
        {
            logger.LogError(error, "A {Purpose} code for user {UserId} could not be withdrawn (correlation {CorrelationId}).",
                message.Purpose, message.UserId, message.CorrelationId);
        }
    }
}
