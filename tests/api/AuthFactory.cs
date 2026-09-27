using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
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
            await AddOrganization(db);
            // Provisioning gives the person the membership and role that token issuance requires.
            var user = await UserProvisioning.Provision(db, new("person@example.com", "+254712345678", "Revenue clerk"));
            user.PinHash = withPin ? PinHasher.Hash("5826") : null;
            if (trusted) db.TrustedDevices.Add(new() { UserId = user.Id, DeviceId = "phone" });
            await db.SaveChangesAsync();
        });
    }
    // Invariant globalization (see Auth.Tests.csproj) cannot resolve IANA zones such as Africa/Nairobi on Windows,
    // so test organizations use UTC.
    public static async Task AddOrganization(AuthDb db)
    {
        db.Provisioning = true;
        var organization = new Organization { Slug = "demo-fleet", Name = "Demo Fleet" };
        db.Organizations.Add(organization);
        db.Localizations.Add(new OrganizationLocalization { OrganizationId = organization.Id, TimeZone = "UTC" });
        db.Brandings.Add(new OrganizationBranding { OrganizationId = organization.Id });
        db.SecurityPolicies.Add(new OrganizationSecurityPolicy { OrganizationId = organization.Id });
        await db.SaveChangesAsync();
        db.Provisioning = false;
    }
    public Task SeedDemo() => WithDb(async db =>
    {
        await db.Database.EnsureCreatedAsync();
        await AddOrganization(db);
        await DemoSeed.Run(db);
    });
    // Signs a demo login in on a fresh device through the real sign-in and email-code flow.
    public async Task<HttpClient> SignIn(string email)
    {
        var (phoneNumber, _, pin) = DemoSeed.Logins.Single(x => x.Email == email);
        var client = CreateClient();
        var device = "test-" + Guid.NewGuid();
        using var signIn = await client.PostAsJsonAsync("/auth/sign-in", new AuthRequest(PhoneNumber: phoneNumber, Pin: pin!, DeviceId: device));
        if (signIn.StatusCode != HttpStatusCode.Accepted) throw new InvalidOperationException($"Sign-in for {email} returned {signIn.StatusCode}.");
        using var verify = await client.PostAsJsonAsync("/auth/verify-device", new AuthRequest(PhoneNumber: phoneNumber, DeviceId: device, Code: Email.Codes[email]));
        verify.EnsureSuccessStatusCode();
        var tokens = await verify.Content.ReadFromJsonAsync<AuthResponse>();
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", tokens!.AccessToken);
        return client;
    }
    public Task Policy(Action<OrganizationSecurityPolicy> change) => WithDb(async db =>
    {
        db.Provisioning = true;
        change(await db.SecurityPolicies.IgnoreQueryFilters().SingleAsync());
        await db.SaveChangesAsync();
    });
    public async Task WithDb(Func<AuthDb, Task> action)
    {
        using var scope = Services.CreateScope();
        await action(scope.ServiceProvider.GetRequiredService<AuthDb>());
    }
    protected override void Dispose(bool disposing) { base.Dispose(disposing); if (disposing) connection.Dispose(); }
}
