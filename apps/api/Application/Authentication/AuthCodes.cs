using System.Security.Cryptography;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Application.Authentication;

// The code and the message that carries it. The message is sent only if the attempt that issued the code commits.
public sealed record IssuedCode(string? DevelopmentCode, VerificationMailer.Message Mail);

public sealed class AuthCodes(AuthDb db, IClock clock, TokenIssuer tokens, AuthOptions options, IOrganizationContext context)
{
    public const int HourlyCodeLimit = 5;
    public const int DailyCodeLimit = 10;

    // Null when a code went out less than a minute ago or the hourly or daily cap is reached.
    public async Task<IssuedCode?> Issue(User user, string deviceId, CodePurpose purpose, CancellationToken ct)
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
        return new(options.DevelopmentMode ? code : null, new(issued.Id, user.Id, user.Email, code, purpose, context.CorrelationId));
    }

    public async Task<VerificationCode?> Matching(User user, AuthRequest request, CodePurpose purpose)
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

    public async Task<bool> Consume(User user, AuthRequest request, CodePurpose purpose)
    {
        var code = await Matching(user, request, purpose);
        if (code is null) return false;
        code.Consume();
        return true;
    }

    public async Task ConsumeAll(Guid userId, string? deviceId = null)
    {
        foreach (var code in await db.VerificationCodes.Where(c => c.UserId == userId && (deviceId == null || c.DeviceId == deviceId) && !c.Consumed).ToListAsync())
            code.Consume();
    }
}
