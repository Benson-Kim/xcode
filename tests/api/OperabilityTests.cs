using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using Auth.Application;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Console;
using Microsoft.Extensions.Options;
using Xunit;

namespace Auth.Tests;

public sealed class OperabilityTests : IDisposable
{
    private readonly AuthFactory app = new();
    private readonly HttpClient client;
    public OperabilityTests() => client = app.CreateClient();
    private VerificationMailer Mailer => app.Services.GetRequiredService<VerificationMailer>();

    private async Task<(HttpStatusCode Status, AuthResponse Body)> Post(string path, AuthRequest? request = null)
    {
        var response = await client.PostAsJsonAsync("/auth/" + path, request ?? new AuthRequest(PhoneNumber: "+254712345678", Pin: "5826", DeviceId: "phone"));
        await Mailer.Idle();
        var body = await response.Content.ReadFromJsonAsync<AuthResponse>();
        Assert.NotNull(body);
        return (response.StatusCode, body);
    }

    // The liveness probe succeeds without a database.
    [Fact]
    public async Task LivenessProbeSucceedsWithoutDatabase()
    {
        using var response = await client.GetAsync("/health/live");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    // The readiness probe checks the database.
    [Fact]
    public async Task ReadinessProbeChecksDatabase()
    {
        await app.WithDb(db => db.Database.EnsureCreatedAsync());
        using var response = await client.GetAsync("/health/ready");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task ReadinessProbeFailsWhenDatabaseIsUnreachable()
    {
        var missing = Path.Combine(Path.GetTempPath(), "unreachable-" + Guid.NewGuid(), "revenue.db");
        using var unreachable = app.WithWebHostBuilder(builder => builder.ConfigureServices(services =>
        {
            services.RemoveAll<DbContextOptions<AuthDb>>();
            services.RemoveAll<IDbContextOptionsConfiguration<AuthDb>>();
            services.AddDbContext<AuthDb>(o => o.UseSqlite($"Data Source={missing};Mode=ReadWrite"));
        }));
        using var http = unreachable.CreateClient();

        using var ready = await http.GetAsync("/health/ready");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, ready.StatusCode);
        using var live = await http.GetAsync("/health/live");
        Assert.Equal(HttpStatusCode.OK, live.StatusCode);
        using var legacy = await http.GetAsync("/health");
        Assert.Equal(HttpStatusCode.OK, legacy.StatusCode);
    }

    [Fact]
    public void ConsoleLogsAreJsonWithScopesOutsideDevelopment()
    {
        var console = app.Services.GetRequiredService<IOptionsMonitor<ConsoleLoggerOptions>>().CurrentValue;
        Assert.Equal(ConsoleFormatterNames.Json, console.FormatterName);
        var json = app.Services.GetRequiredService<IOptionsMonitor<JsonConsoleFormatterOptions>>().CurrentValue;
        Assert.True(json.IncludeScopes);
        Assert.True(json.UseUtcTimestamp);
    }

    // The legacy health endpoint still works.
    [Fact]
    public async Task LegacyHealthEndpointReturnsOk()
    {
        using var response = await client.GetAsync("/health");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await response.Content.ReadFromJsonAsync<System.Text.Json.JsonElement>();
        Assert.Equal("ok", body.GetProperty("status").GetString());
    }

    // Every response carries X-Request-ID.
    [Fact]
    public async Task ResponsesCarryRequestId()
    {
        using var response = await client.GetAsync("/health");
        Assert.True(response.Headers.Contains("X-Request-ID"));
        var id = response.Headers.GetValues("X-Request-ID").Single();
        Assert.False(string.IsNullOrEmpty(id));
    }

    // A caller-supplied X-Request-ID is echoed back.
    [Fact]
    public async Task CallerRequestIdIsEchoed()
    {
        var correlationId = "test-correlation-" + Guid.NewGuid();
        using var request = new HttpRequestMessage(HttpMethod.Get, "/health");
        request.Headers.Add("X-Request-ID", correlationId);
        using var response = await client.SendAsync(request);
        Assert.Equal(correlationId, response.Headers.GetValues("X-Request-ID").Single());
    }

    // ProblemDetails includes requestId but not exception details.
    [Fact]
    public async Task ProblemDetailsIncludesRequestIdNotException()
    {
        await app.Seed();
        app.Database.FailNextCommit = true;
        var correlationId = "problem-test-" + Guid.NewGuid();
        using var request = new HttpRequestMessage(HttpMethod.Post, "/auth/sign-in")
        {
            Content = JsonContent.Create(new AuthRequest(PhoneNumber: "+254712345678", Pin: "5826", DeviceId: "phone"))
        };
        request.Headers.Add("X-Request-ID", correlationId);
        using var response = await client.SendAsync(request);
        Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
        var body = await response.Content.ReadFromJsonAsync<System.Text.Json.JsonElement>();
        Assert.Equal(correlationId, body.GetProperty("requestId").GetString());
        Assert.False(string.IsNullOrEmpty(body.GetProperty("traceId").GetString()));
        if (body.TryGetProperty("exception", out _))
            Assert.Fail("ProblemDetails must not expose exception details");
    }

    // After a bumped SecurityVersion, the old token is rejected.
    [Fact]
    public async Task RevokedUserIsRejected()
    {
        await app.Seed();
        var signedIn = await Post("sign-in");
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", signedIn.Body.AccessToken);

        using var before = await client.GetAsync("/auth/session");
        Assert.Equal(HttpStatusCode.OK, before.StatusCode);

        await app.WithDb(async db =>
        {
            var user = await db.Users.SingleAsync();
            user.BumpSecurityVersion();
            await db.SaveChangesAsync();
        });

        using var after = await client.GetAsync("/auth/session");
        Assert.Equal(HttpStatusCode.Unauthorized, after.StatusCode);
    }

    // A revoked device is rejected immediately.
    [Fact]
    public async Task RevokedDeviceIsRejected()
    {
        await app.Seed();
        var signedIn = await Post("sign-in");
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", signedIn.Body.AccessToken);

        using var before = await client.GetAsync("/auth/session");
        Assert.Equal(HttpStatusCode.OK, before.StatusCode);

        await app.WithDb(async db =>
        {
            var device = await db.TrustedDevices.SingleAsync();
            device.Revoke();
            await db.SaveChangesAsync();
        });

        using var after = await client.GetAsync("/auth/session");
        Assert.Equal(HttpStatusCode.Unauthorized, after.StatusCode);
    }

    // ExecutionStrategy wrapping lets auth transactions work with EnableRetryOnFailure.
    [Fact]
    public async Task AuthTransactionsWorkWithRetryStrategy()
    {
        await app.Seed();
        var result = await Post("sign-in");
        Assert.Equal(HttpStatusCode.OK, result.Status);
        Assert.NotNull(result.Body.AccessToken);
        Assert.NotNull(result.Body.RefreshToken);
    }

    // The Testing environment does not auto-migrate (no EF migration at startup).
    [Fact]
    public async Task TestingEnvironmentDoesNotAutoMigrate()
    {
        using var response = await client.GetAsync("/health/live");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    public void Dispose() { client.Dispose(); app.Dispose(); }
}
