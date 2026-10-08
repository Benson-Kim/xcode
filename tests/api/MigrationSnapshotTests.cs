using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using Xunit;

namespace Auth.Tests;

// The migrations snapshot must describe the current SQL Server model; otherwise a schema change reaches no database,
// or the next migration picks up changes nobody meant to make. Building the model opens no connection.
public sealed class MigrationSnapshotTests
{
    private static AuthDb SqlServerModel() => new(new DbContextOptionsBuilder<AuthDb>()
        .UseSqlServer("Server=(local);Database=snapshot_check;Trusted_Connection=True")
        .Options);

    [Fact]
    public void TheSnapshotMatchesTheModel()
    {
        using var db = SqlServerModel();
        Assert.False(db.Database.HasPendingModelChanges());
    }

    // Each organization's saved grouping choice survives the spelling fix: the column is renamed in place, never dropped.
    [Fact]
    public void TheGroupingColumnIsRenamedInPlace()
    {
        using var db = SqlServerModel();
        var migrations = db.Database.GetMigrations().ToList();
        var rename = migrations.FindIndex(x => x.EndsWith("_RenameUseGrouping", StringComparison.Ordinal));
        Assert.True(rename > 0, string.Join(", ", migrations));
        var migrator = db.GetService<IMigrator>();
        var up = migrator.GenerateScript(migrations[rename - 1], migrations[rename]);
        Assert.Contains("EXEC sp_rename N'[Localizations].[UseGroupping]', N'UseGrouping', 'COLUMN';", up);
        Assert.DoesNotContain("DROP", up, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("ADD", up, StringComparison.Ordinal);
        var down = migrator.GenerateScript(migrations[rename], migrations[rename - 1]);
        Assert.Contains("EXEC sp_rename N'[Localizations].[UseGrouping]', N'UseGroupping', 'COLUMN';", down);
    }

    [Fact]
    public void AccessMigrationsRunInOrder()
    {
        using var db = SqlServerModel();
        var migrations = db.Database.GetMigrations().ToList();
        var integrity = migrations.IndexOf("20260929200000_AccessIntegrity");
        var policy = migrations.IndexOf("20260929200500_NormalizeSecurityPolicy");
        Assert.True(integrity >= 0 && policy == integrity + 1, string.Join(", ", migrations));
        // Before the settings branch's 20260929210000_ExpenseCatalogAndInvestment.
        Assert.True(string.CompareOrdinal("20260929200500_NormalizeSecurityPolicy", "20260929210000") < 0);
    }

    // The migration's own clamp, run on a policy saved under an earlier version's wider bounds: afterwards every value
    // sits within what a save accepts today, at the nearest edge.
    [Fact]
    public async Task NormalizingBringsAnOlderPolicyIntoTheCurrentBounds()
    {
        using var app = new AuthFactory();
        await app.Seed();
        await app.WithDb(async db =>
        {
            await db.Database.ExecuteSqlRawAsync(
                "PRAGMA ignore_check_constraints = 1; " +
                "UPDATE \"SecurityPolicies\" SET \"PasswordMinLength\" = 4, \"PasswordHistory\" = 99, \"PinLength\" = 2, \"LockoutThreshold\" = 1, " +
                "\"LockoutMinutes\" = 1440, \"AccessTokenMinutes\" = 0, \"RefreshTokenDays\" = 365, \"IdleUnlockSeconds\" = 5; " +
                "PRAGMA ignore_check_constraints = 0;");
            await db.Database.ExecuteSqlRawAsync(Auth.Api.Infrastructure.Migrations.NormalizeSecurityPolicy.ClampSql);

            var policy = await db.SecurityPolicies.IgnoreQueryFilters().AsNoTracking().SingleAsync();
            policy.Validate();
            Assert.Equal((12, 24, 4, 3, 60, 1, 90, 30), (policy.PasswordMinLength, policy.PasswordHistory, policy.PinLength, policy.LockoutThreshold,
                policy.LockoutMinutes, policy.AccessTokenMinutes, policy.RefreshTokenDays, policy.IdleUnlockSeconds));
        });
    }

    // With the checks in place, not even a direct write can store an out-of-range policy.
    [Fact]
    public async Task TheDatabaseRefusesAnOutOfRangePolicy()
    {
        using var app = new AuthFactory();
        await app.Seed();
        await app.WithDb(async db => await Assert.ThrowsAnyAsync<Exception>(() =>
            db.Database.ExecuteSqlRawAsync("UPDATE \"SecurityPolicies\" SET \"LockoutMinutes\" = 1440")));
    }
}
