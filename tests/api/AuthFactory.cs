using System.Collections.Concurrent;
using Auth.Application;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace Auth.Tests;

public sealed class TestClock : IClock
{
    public DateTimeOffset UtcNow { get; set; } = DateTimeOffset.UtcNow;
    public void Advance(TimeSpan duration) => UtcNow += duration;
}
public sealed class TestEmail : IEmailSender
{
    public ConcurrentDictionary<string, string> Codes { get; } = new();
    public int Count { get; private set; }
    public Task SendCode(string email, string code, CodePurpose purpose, CancellationToken cancellationToken)
    { Codes[email] = code; Count++; return Task.CompletedTask; }
}
public sealed class AuthFactory : WebApplicationFactory<Program>
{
    private readonly SqliteConnection connection = new("Data Source=:memory:");
    public TestClock Clock { get; } = new();
    public TestEmail Email { get; } = new();
    public AuthFactory() => connection.Open();
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Testing");
        builder.ConfigureServices(services =>
        {
            services.RemoveAll<DbContextOptions<AuthDb>>();
            services.RemoveAll<IDbContextOptionsConfiguration<AuthDb>>();
            services.AddDbContext<AuthDb>(o => o.UseSqlite(connection));
            services.RemoveAll<IClock>();
            services.AddSingleton<IClock>(Clock);
            services.RemoveAll<IEmailSender>();
            services.AddSingleton<IEmailSender>(Email);
        });
    }
    public async Task Seed(bool withPin = true, bool trusted = true)
    {
        await WithDb(async db =>
        {
            await db.Database.EnsureCreatedAsync();
            var user = new User { Email = "person@example.com", PhoneNumber = "+254712345678", PinHash = withPin ? PinHasher.Hash("5826") : null };
            db.Users.Add(user);
            if (trusted) db.TrustedDevices.Add(new() { UserId = user.Id, DeviceId = "phone" });
            await db.SaveChangesAsync();
        });
    }
    public async Task WithDb(Func<AuthDb, Task> action)
    {
        using var scope = Services.CreateScope();
        await action(scope.ServiceProvider.GetRequiredService<AuthDb>());
    }
    protected override void Dispose(bool disposing) { base.Dispose(disposing); if (disposing) connection.Dispose(); }
}
