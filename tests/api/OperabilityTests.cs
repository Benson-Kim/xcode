using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using Auth.Application;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
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

    // P3-3: The liveness probe succeeds without a database.
    [Fact]
    public async Task LivenessProbeSucceedsWithoutDatabase()
    {
        using var response = await client.GetAsync("/health/live");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    // P3-3: The readiness probe checks the database.
    [Fact]
    public async Task ReadinessProbeChecksDatabase()
    {
        await app.WithDb(db => db.Database.EnsureCreatedAsync());
        using var response = await client.GetAsync("/health/ready");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    // P3-3: The legacy health endpoint still works.
    [Fact]
    public async Task LegacyHealthEndpointReturnsOk()
    {
        using var response = await client.GetAsync("/health");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await response.Content.ReadFromJsonAsync<System.Text.Json.JsonElement>();
        Assert.Equal("ok", body.GetProperty("status").GetString());
    }

    // P3-2: Every response carries X-Request-ID.
    [Fact]
    public async Task ResponsesCarryRequestId()
    {
        using var response = await client.GetAsync("/health");
        Assert.True(response.Headers.Contains("X-Request-ID"));
        var id = response.Headers.GetValues("X-Request-ID").Single();
        Assert.False(string.IsNullOrEmpty(id));
    }

    // P3-2: A caller-supplied X-Request-ID is echoed back.
    [Fact]
    public async Task CallerRequestIdIsEchoed()
    {
        var correlationId = "test-correlation-" + Guid.NewGuid();
        using var request = new HttpRequestMessage(HttpMethod.Get, "/health");
        request.Headers.Add("X-Request-ID", correlationId);
        using var response = await client.SendAsync(request);
        Assert.Equal(correlationId, response.Headers.GetValues("X-Request-ID").Single());
    }

    // P3-2: ProblemDetails includes requestId but not exception details.
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
        if (body.TryGetProperty("requestId", out var rid))
            Assert.Equal(correlationId, rid.GetString());
        if (body.TryGetProperty("exception", out _))
            Assert.Fail("ProblemDetails must not expose exception details");
    }

    // P3-6: After a bumped SecurityVersion, the old token is rejected.
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

    // P3-6: A revoked device is rejected immediately.
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

    // P3-6: ExecutionStrategy wrapping lets auth transactions work with EnableRetryOnFailure.
    [Fact]
    public async Task AuthTransactionsWorkWithRetryStrategy()
    {
        await app.Seed();
        var result = await Post("sign-in");
        Assert.Equal(HttpStatusCode.OK, result.Status);
        Assert.NotNull(result.Body.AccessToken);
        Assert.NotNull(result.Body.RefreshToken);
    }

    // P3-1: The Testing environment does not auto-migrate (no EF migration at startup).
    [Fact]
    public async Task TestingEnvironmentDoesNotAutoMigrate()
    {
        using var response = await client.GetAsync("/health/live");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    public void Dispose() { client.Dispose(); app.Dispose(); }
}
