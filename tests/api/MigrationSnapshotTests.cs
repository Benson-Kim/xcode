using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
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

    [Fact]
    public void AccessIntegrityIsAMigration()
    {
        using var db = SqlServerModel();
        Assert.Contains("20260929200000_AccessIntegrity", db.Database.GetMigrations());
    }
}
