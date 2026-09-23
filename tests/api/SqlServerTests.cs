using Auth.Infrastructure;
using Microsoft.Data.SqlClient;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace Auth.Tests;

public sealed class SqlServerTests
{
    [Fact]
    public async Task SqlServerDriverCanInitializeInConfiguredRuntime()
    {
        // No local SQL Server required: connecting to a closed port must fail as a network
        // error, not because the runtime globalization configuration is incompatible.
        await using var connection = new SqlConnection("Server=127.0.0.1,1;User Id=sa;Password=not-a-real-password;Connect Timeout=1;Encrypt=False");
        await Assert.ThrowsAsync<SqlException>(() => connection.OpenAsync());
    }

    [Fact]
    [Trait("Category", "SqlServer")]
    public async Task SqlServerMigrationsApplyWhenCiProvidesServer()
    {
        var connectionString = Environment.GetEnvironmentVariable("SQLSERVER_TEST_CONNECTION");
        Assert.False(string.IsNullOrEmpty(connectionString), "SQLSERVER_TEST_CONNECTION is required for the SQL Server test category.");
        await using var db = new AuthDb(new DbContextOptionsBuilder<AuthDb>().UseSqlServer(connectionString).Options);
        await db.Database.MigrateAsync();
        Assert.Empty(await db.Database.GetPendingMigrationsAsync());
        Assert.True(await db.Database.CanConnectAsync());
    }
}
