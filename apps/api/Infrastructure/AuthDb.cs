using Auth.Domain;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

public sealed class AuthDb(DbContextOptions<AuthDb> options) : DbContext(options)
{
    public DbSet<User> Users => Set<User>();
    public DbSet<VerificationCode> VerificationCodes => Set<VerificationCode>();
    public DbSet<TrustedDevice> TrustedDevices => Set<TrustedDevice>();
    public DbSet<RefreshToken> RefreshTokens => Set<RefreshToken>();

    protected override void OnModelCreating(ModelBuilder model)
    {
        model.Entity<User>().Property(x => x.Email).HasMaxLength(320);
        model.Entity<User>().HasIndex(x => x.Email).IsUnique();

        model.Entity<User>().Property(x => x.PhoneNumber).HasMaxLength(13);
        model.Entity<User>().HasIndex(x => x.PhoneNumber).IsUnique();

        model.Entity<User>().Property(x => x.PinHash).HasMaxLength(256);

        model.Entity<TrustedDevice>().Property(x => x.DeviceId).HasMaxLength(128);
        model.Entity<TrustedDevice>().HasIndex(x => new { x.UserId, x.DeviceId }).IsUnique();

        model.Entity<VerificationCode>().Property(x => x.DeviceId).HasMaxLength(128);
        model.Entity<VerificationCode>().Property(x => x.CodeHash).HasMaxLength(64);
        model.Entity<VerificationCode>().HasIndex(x => new { x.UserId, x.Purpose });

        model.Entity<RefreshToken>().Property(x => x.DeviceId).HasMaxLength(128);
        model.Entity<RefreshToken>().Property(x => x.TokenHash).HasMaxLength(64);
        model.Entity<RefreshToken>().HasIndex(x => x.TokenHash).IsUnique();

        model.Entity<TrustedDevice>().HasOne<User>().WithMany().HasForeignKey(x => x.UserId);
        model.Entity<VerificationCode>().HasOne<User>().WithMany().HasForeignKey(x => x.UserId);
        model.Entity<RefreshToken>().HasOne<User>().WithMany().HasForeignKey(x => x.UserId);
    }
}
