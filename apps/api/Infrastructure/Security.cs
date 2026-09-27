using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using Auth.Application;
using Auth.Domain;
using Microsoft.IdentityModel.Tokens;

namespace Auth.Infrastructure;

public sealed class SystemClock : IClock { public DateTimeOffset UtcNow => DateTimeOffset.UtcNow; }

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
