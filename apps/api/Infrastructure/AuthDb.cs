using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

public sealed partial class AuthDb(DbContextOptions<AuthDb> options, Auth.Application.IOrganizationContext? organizationContext = null) : DbContext(options)
{
    public Guid CurrentOganizationId => organizationContext?.OrganizationId ?? Guid.Empty;
    public bool Provisioning { get; set; }
    public DbSet<Organization> Organizations => Set<Organization>();
    public DbSet<OrganizationMembership> Memberships => Set<OrganizationMembership>();
    public DbSet<OrganizationLocalization> Localizations => Set<OrganizationLocalization>();
    public DbSet<OrganizationBranding> Brandings => Set<OrganizationBranding>();
    public DbSet<OrganizationLogo> Logos => Set<OrganizationLogo>();
    public DbSet<OrganizationSecurityPolicy> SecurityPolicies => Set<OrganizationSecurityPolicy>();
    public DbSet<UserPreference> UserPreferences => Set<UserPreference>();
    public DbSet<Role> Roles => Set<Role>();
    public DbSet<RolePermission> RolePermissions => Set<RolePermission>();
    public DbSet<PersonRole> PersonRoles => Set<PersonRole>();
    public DbSet<PersonPermissionOverride> PermissionOverrides => Set<PersonPermissionOverride>();
    public DbSet<SetupDataScope> SetupDataScopes => Set<SetupDataScope>();
    public DbSet<SetupCompanyScope> SetupCompanyScopes => Set<SetupCompanyScope>();
    public DbSet<SetupVehicleScope> SetupVehicleScopes => Set<SetupVehicleScope>();
    public DbSet<AuditEvent> AuditEvents => Set<AuditEvent>();
    public DbSet<User> Users => Set<User>();
    public DbSet<VerificationCode> VerificationCodes => Set<VerificationCode>();
    public DbSet<TrustedDevice> TrustedDevices => Set<TrustedDevice>();
    public DbSet<RefreshToken> RefreshTokens => Set<RefreshToken>();
    public DbSet<RevenueRecord> RevenueRecords => Set<RevenueRecord>();
    public DbSet<PettyCashEntry> PettyCashEntries => Set<PettyCashEntry>();
    public DbSet<CentralExpense> CentralExpenses => Set<CentralExpense>();

    protected override void OnModelCreating(ModelBuilder model)
    {
        ConfigureOrganizations(model);
        ConfigureSetup(model);
        ConfigureRevenue(model);
        ConfigurePettyCash(model);
        ConfigureCentralExpenses(model);

        model.Entity<User>().Property(x => x.Email).HasMaxLength(320);
        model.Entity<User>().HasIndex(x => x.Email).IsUnique();

        model.Entity<User>().Property(x => x.PhoneNumber).HasMaxLength(13);
        // Users provisioned before phone sign-in have no number yet; only real numbers must be unique.
        model.Entity<User>().HasIndex(x => x.PhoneNumber).IsUnique().HasFilter("[PhoneNumber] <> ''");

        model.Entity<User>().Property(x => x.PinHash).HasMaxLength(256);
        model.Entity<User>().Property(x => x.Version).IsConcurrencyToken();

        model.Entity<TrustedDevice>().Property(x => x.DeviceId).HasMaxLength(128);
        model.Entity<TrustedDevice>().HasIndex(x => new { x.UserId, x.DeviceId }).IsUnique();

        model.Entity<VerificationCode>().Property(x => x.DeviceId).HasMaxLength(128);
        model.Entity<VerificationCode>().Property(x => x.CodeHash).HasMaxLength(64);
        model.Entity<VerificationCode>().HasIndex(x => new { x.UserId, x.Purpose });

        model.Entity<RefreshToken>().Property(x => x.DeviceId).HasMaxLength(128);
        model.Entity<RefreshToken>().Property(x => x.TokenHash).HasMaxLength(64);
        model.Entity<RefreshToken>().HasIndex(x => x.TokenHash).IsUnique();
        model.Entity<RefreshToken>().Property(x => x.Version).IsConcurrencyToken();

        model.Entity<TrustedDevice>().HasOne<User>().WithMany().HasForeignKey(x => x.UserId);
        model.Entity<VerificationCode>().HasOne<User>().WithMany().HasForeignKey(x => x.UserId);
        model.Entity<RefreshToken>().HasOne<User>().WithMany().HasForeignKey(x => x.UserId);
    }

    private void BumpVersions()
    {
        foreach (var entry in ChangeTracker.Entries().Where(x => x.State == EntityState.Modified && x.Entity is User or RefreshToken))
        {
            var version = entry.Property("Version");
            version.CurrentValue = (long)version.OriginalValue! + 1;
        }
    }
}
