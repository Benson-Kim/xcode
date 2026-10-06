using Auth.Domain;

namespace Auth.Application;

public interface IClock { DateTimeOffset UtcNow { get; } }
public interface IEmailSender
{
    Task SendCode(string email, string code, CodePurpose purpose, CancellationToken cancellationToken);
}
public sealed class AuthOptions
{
    public string SigningKey { get; set; } = "";
    public string Issuer { get; set; } = "xcode-api";
    public string Audience { get; set; } = "xcode-clients";
    public int? TrustLifetimeDays { get; set; }
    public bool DevelopmentMode { get; set; }
}
public sealed record AuthRequest(
    string Email = "",
    string PhoneNumber = "",
    string Pin = "",
    string DeviceId = "",
    string Code = "",
    string RefreshToken = ""
);

public sealed record AuthResponse(string Status, string? AccessToken = null, string? RefreshToken = null, int? RetryAfterSeconds = null, string? DevelopmentCode = null, string? MaskedEmail = null, int? MinimumPinLength = null);
public sealed record AuthSessionResponse(Guid UserId, string FirstName, string LastName, string Role, IReadOnlyList<string> Permissions);
public sealed record AuthResult(int HttpStatus, AuthResponse Body)
{
    public static AuthResult Failure() => new(401, new("authentication_failed"));
    public static AuthResult Accepted() => new(202, new("check_email"));
    public static AuthResult InvalidPin(int minimumLength) => new(400, new("invalid_pin", MinimumPinLength: minimumLength));
}

public static class PinRules
{
    public const int MinimumLength = 4;
    public const int MaximumLength = 8;
    // Four to eight ASCII digits. Reject all equal digits and full +/-1 sequences.
    // An organization's security policy may raise the minimum for new PINs.
    public static bool IsValid(string? pin)
    {
        if (pin is null || pin.Length is < MinimumLength or > MaximumLength || pin.Any(c => c is < '0' or > '9')) return false;
        if (pin.All(c => c == pin[0])) return false;
        var steps = pin.Zip(pin.Skip(1), (a, b) => b - a).ToArray();
        return !steps.All(d => d == 1) && !steps.All(d => d == -1);
    }
}
