using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
using Microsoft.Extensions.Configuration;

namespace Auth.Infrastructure;

public sealed class AuthDbDesignFactory : IDesignTimeDbContextFactory<AuthDb>
{
    public AuthDb CreateDbContext(string[] args)
    {
        var configuration = new ConfigurationBuilder()
            .SetBasePath(Directory.GetCurrentDirectory())
            .AddJsonFile("appsettings.json", optional: false)
            .AddEnvironmentVariables()
            .Build();
        var options = new DbContextOptionsBuilder<AuthDb>()
            .UseSqlServer(configuration.GetConnectionString("Auth"))
            .Options;
        return new AuthDb(options);
    }
}