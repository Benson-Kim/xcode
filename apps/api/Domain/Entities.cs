namespace Auth.Domain;

public enum UserStatus { Active, Removed }
public enum CodePurpose { FirstSetup, NewDevice, PinReset }

public sealed class User
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Email { get; set; } = "";
    public string PhoneNumber { get; set; } = "";
    public string? PinHash { get; set; }
    public UserStatus Status { get; set; }
    public int FailedAttempts { get; set; }
    public DateTimeOffset? PausedUntil { get; set; }
    public int SecurityVersion { get; set; }
}

public sealed class VerificationCode
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid UserId { get; set; }
    public string DeviceId { get; set; } = "";
    public CodePurpose Purpose { get; set; }
    public string CodeHash { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; }
    public DateTimeOffset ExpiresAt { get; set; }
    public bool Consumed { get; set; }
    public int FailedAttempts { get; set; }
}

public sealed class TrustedDevice
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid UserId { get; set; }
    public string DeviceId { get; set; } = "";
    public DateTimeOffset? TrustExpiresAt { get; set; }
    public bool Revoked { get; set; }
}

public sealed class RefreshToken
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid UserId { get; set; }
    public string DeviceId { get; set; } = "";
    public string TokenHash { get; set; } = "";
    public DateTimeOffset ExpiresAt { get; set; }
    public bool Revoked { get; set; }
}
