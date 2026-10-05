using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace Auth.Tests;

// The SQL Server model snapshot must describe the current model, or the next migration silently carries
// (or misses) someone else's schema change. No connection is opened: the check compares models only.
public sealed class SetupMigrationSnapshotTests
{
    [Fact]
    public void TheMigrationSnapshotMatchesTheModel()
    {
        var options = new DbContextOptionsBuilder<AuthDb>()
            .UseSqlServer("Server=(local);Database=snapshot_check;Trusted_Connection=True")
            .Options;
        using var db = new AuthDb(options);

        Assert.False(db.Database.HasPendingModelChanges(), "Add a migration: the model differs from AuthDbModelSnapshot.");
    }
}
