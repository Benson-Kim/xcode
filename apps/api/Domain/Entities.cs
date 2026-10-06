namespace Auth.Domain;

public enum UserStatus { Active, Removed }
public enum CodePurpose { FirstSetup, NewDevice, PinReset }

public sealed class User
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Email { get; set; } = "";
    public string PhoneNumber { get; set; } = "";
    public string? PinHash { get; private set; }
    public UserStatus Status { get; set; }
    public int FailedAttempts { get; private set; }
    public DateTimeOffset? PausedUntil { get; private set; }
    public int SecurityVersion { get; private set; }
    public int UntrustedFailedAttempts { get; private set; }
    public long Version { get; private set; }

    public bool HasPin => PinHash is not null;
    public bool IsPaused(DateTimeOffset now) => PausedUntil is not null && now < PausedUntil;

    public void SetPin(string hash)
    {
        PinHash = hash;
        UntrustedFailedAttempts = 0;
        SecurityVersion++;
    }

    public void ClearLockout()
    {
        FailedAttempts = 0;
        PausedUntil = null;
    }

    public void RecordFailedAttempt() => FailedAttempts++;

    public void RecordUntrustedFailedAttempt() => UntrustedFailedAttempts++;

    public void ClearUntrustedFailedAttempts() => UntrustedFailedAttempts = 0;

    public void Pause(DateTimeOffset until) => PausedUntil = until;

    public void BumpSecurityVersion() => SecurityVersion++;

    public void Remove()
    {
        Status = UserStatus.Removed;
        SecurityVersion++;
    }
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
    public bool Consumed { get; private set; }
    public int FailedAttempts { get; private set; }

    public bool IsUsable(DateTimeOffset now) => !Consumed && now <= ExpiresAt && FailedAttempts < 5;

    public void RecordFailedAttempt()
    {
        FailedAttempts++;
        if (FailedAttempts >= 5) Consumed = true;
    }

    public void Consume() => Consumed = true;

    public void Withdraw()
    {
        Consumed = true;
        ExpiresAt = CreatedAt;
    }

    public bool IsWithdrawn => Consumed && ExpiresAt <= CreatedAt;
}

public sealed class TrustedDevice
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid UserId { get; set; }
    public string DeviceId { get; set; } = "";
    public DateTimeOffset? TrustExpiresAt { get; private set; }
    public bool Revoked { get; private set; }

    public bool IsValid(DateTimeOffset now) => !Revoked && (TrustExpiresAt is null || now < TrustExpiresAt);

    public void Revoke() => Revoked = true;

    public void Trust(DateTimeOffset? expiresAt)
    {
        Revoked = false;
        TrustExpiresAt = expiresAt;
    }
}

public sealed class RefreshToken
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid UserId { get; set; }
    public string DeviceId { get; set; } = "";
    public string TokenHash { get; set; } = "";
    public DateTimeOffset ExpiresAt { get; set; }
    public bool Revoked { get; private set; }
    public long Version { get; private set; }

    public void Revoke() => Revoked = true;
}
