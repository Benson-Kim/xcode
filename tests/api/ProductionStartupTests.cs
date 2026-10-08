using Auth.Infrastructure;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace Auth.Tests;

public sealed class ProductionStartupTests : IDisposable
{
    private readonly AuthFactory app = new();

    private static readonly Dictionary<string, string> Complete = new()
    {
        ["Auth:SigningKey"] = "production-test-signing-key-0123456789-abcdef",
        ["Email:Host"] = "smtp.example.com",
        ["Email:From"] = "noreply@example.com",
        ["ConnectionStrings:Auth"] = "Server=unused;Database=unused",
    };

    private WebApplicationFactory<Program> Production(params (string Key, string Value)[] changes)
    {
        var settings = new Dictionary<string, string>(Complete);
        foreach (var (key, value) in changes) settings[key] = value;
        return app.WithWebHostBuilder(builder =>
        {
            builder.UseEnvironment("Production");
            foreach (var (key, value) in settings) builder.UseSetting(key, value);
        });
    }

    [Fact]
    public void ProductionRefusesToStartWithoutEmailHost()
    {
        using var host = Production(("Email:Host", ""));
        var failure = Assert.Throws<InvalidOperationException>(() => host.CreateClient());
        Assert.Equal("Email:Host is required.", failure.Message);
    }

    [Fact]
    public void ProductionRefusesToStartWithoutEmailFrom()
    {
        using var host = Production(("Email:From", ""));
        var failure = Assert.Throws<InvalidOperationException>(() => host.CreateClient());
        Assert.Equal("Email:From is required.", failure.Message);
    }

    [Fact]
    public void ProductionRefusesToStartWithoutConnectionString()
    {
        using var host = Production(("ConnectionStrings:Auth", ""));
        var failure = Assert.Throws<InvalidOperationException>(() => host.CreateClient());
        Assert.Equal("ConnectionStrings:Auth is required.", failure.Message);
    }

    [Fact]
    public async Task ProductionStartupDoesNotCreateOrMigrateTheSchema()
    {
        using var host = Production();
        var startup = Record.Exception(() => host.CreateClient());
        Assert.Contains("no such table", startup?.ToString());
        Assert.Contains(app.Database.Sql, sql => sql.Contains("\"Users\"", StringComparison.Ordinal));
        Assert.DoesNotContain(app.Database.Sql, sql => sql.Contains("CREATE TABLE", StringComparison.OrdinalIgnoreCase) || sql.Contains("__EFMigrationsHistory", StringComparison.Ordinal));
        await app.WithDb(async db =>
        {
            var connection = (SqliteConnection)db.Database.GetDbConnection();
            using var command = connection.CreateCommand();
            command.CommandText = "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'";
            Assert.Equal(0L, await command.ExecuteScalarAsync());
        });
    }

    public void Dispose() => app.Dispose();
}
