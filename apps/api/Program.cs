using System.Diagnostics;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Threading.RateLimiting;
using Auth.Api;
using Auth.Application;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Diagnostics.HealthChecks;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.AspNetCore.ResponseCompression;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Storage;
using Microsoft.IdentityModel.Tokens;

DotNetEnv.Env.NoClobber().TraversePath().Load();
var builder = WebApplication.CreateBuilder(args);
var options = builder.Configuration.GetSection("Auth").Get<AuthOptions>() ?? new();
if (string.IsNullOrEmpty(options.SigningKey) && (builder.Environment.IsDevelopment() || builder.Environment.IsEnvironment("Testing")))
    options.SigningKey = Convert.ToBase64String(RandomNumberGenerator.GetBytes(48));
if (Encoding.UTF8.GetByteCount(options.SigningKey) < 32) throw new InvalidOperationException("Set Auth__SigningKey to at least 32 random bytes.");
if (options.TrustLifetimeDays is <= 0) throw new InvalidOperationException("TrustLifetimeDays must be positive or null.");

// Guards dev-only features: Development + remote database must not activate DemoSeed or LogEmailSender.
static bool IsLocalDatabase(string? connectionString)
{
    if (string.IsNullOrEmpty(connectionString)) return true; // no connection string = in-memory or not yet configured
    var lower = connectionString.ToLowerInvariant();
    return lower.Contains("localhost") || lower.Contains("(localdb)") || lower.Contains("127.0.0.1")
        || lower.Contains("data source=:memory:") || lower.Contains(":memory:")
        || lower.Contains("mode=memory") || lower.Contains(".db");
}
var connectionString = builder.Configuration.GetConnectionString("Auth");
var isLocalDb = IsLocalDatabase(connectionString);
options.DevelopmentMode = builder.Environment.IsDevelopment() && isLocalDb;

// Production-critical settings are checked at startup, not on first use.
if (!builder.Environment.IsDevelopment() && !builder.Environment.IsEnvironment("Testing"))
{
    if (string.IsNullOrEmpty(builder.Configuration["Email:Host"])) throw new InvalidOperationException("Email:Host is required.");
    if (string.IsNullOrEmpty(builder.Configuration["Email:From"])) throw new InvalidOperationException("Email:From is required.");
    if (string.IsNullOrEmpty(connectionString)) throw new InvalidOperationException("ConnectionStrings:Auth is required.");
}

// Console logs outside Development are JSON with scopes, so the per-request RequestId reaches every line.
if (!builder.Environment.IsDevelopment())
    builder.Logging.AddJsonConsole(o =>
    {
        o.IncludeScopes = true;
        o.UseUtcTimestamp = true;
    });

builder.Services.AddSingleton(options);
builder.Services.AddSingleton<IClock, Auth.Infrastructure.SystemClock>();
builder.Services.AddSingleton<TokenIssuer>();
builder.Services.AddSingleton<AuthGate>();
builder.Services.AddHttpContextAccessor();
builder.Services.AddScoped<IOrganizationContext, organizationContext>();
builder.Services.AddScoped<IOrganizationRepository, OrganizationRepository>();
builder.Services.AddScoped<IUnitOfWork, UnitOfWork>();
builder.Services.AddSingleton<EffectiveSettingsResolver>();
builder.Services.AddSingleton<EffectivePermissionResolver>();
builder.Services.AddAuthServices();
builder.Services.AddSingleton<VerificationMailer>();
builder.Services.AddSetup();
builder.Services.AddRevenue();
builder.Services.AddPettyCash();
builder.Services.AddCentralExpenses();
builder.Services.AddReports();
builder.Services.AddOrganizationSettings();
if ((builder.Environment.IsDevelopment() || builder.Environment.IsEnvironment("Testing")) && isLocalDb) builder.Services.AddScoped<IEmailSender, LogEmailSender>();
else builder.Services.AddScoped<IEmailSender, SmtpEmailSender>();
builder.Services.AddDbContext<AuthDb>(o => o.UseSqlServer(connectionString, sql => sql.EnableRetryOnFailure(3, TimeSpan.FromSeconds(5), null)));
builder.Services.AddHealthChecks().AddCheck<DatabaseHealthCheck>("database", tags: ["ready"], timeout: TimeSpan.FromSeconds(10));
builder.Services.AddCors(o => o.AddDefaultPolicy(p => p.WithOrigins(builder.Configuration.GetSection("Cors:Origins").Get<string[]>() ?? []).AllowAnyHeader().AllowAnyMethod()));
// The web app's sign-ins all reach the API from its Next.js proxy, which names the browser's address in X-Forwarded-For.
// Only a configured proxy (ForwardedHeaders:KnownProxies, loopback when unset) is believed, so the rate limit below
// counts each client separately, and an X-Forwarded-For sent by anyone else is ignored.
var knownProxies = (builder.Configuration.GetSection("ForwardedHeaders:KnownProxies").Get<string[]>() is { Length: > 0 } configured ? configured : ["127.0.0.1", "::1"])
    .Select(x => IPAddress.TryParse(x, out var address) ? address : throw new InvalidOperationException($"ForwardedHeaders:KnownProxies has \"{x}\", which is not an IP address."))
    .ToArray();
builder.Services.Configure<ForwardedHeadersOptions>(o =>
{
    o.ForwardedHeaders = ForwardedHeaders.XForwardedFor;
    o.KnownIPNetworks.Clear();
    o.KnownProxies.Clear();
    foreach (var proxy in knownProxies) o.KnownProxies.Add(proxy);
});
var authPermitLimit = builder.Configuration.GetValue<int?>("RateLimiting:AuthPermitLimit") ?? (builder.Environment.IsEnvironment("Testing") ? 10000 : 30);
if (authPermitLimit <= 0) throw new InvalidOperationException("RateLimiting:AuthPermitLimit must be positive.");
builder.Services.AddRateLimiter(o =>
{
    o.RejectionStatusCode = 429;
    o.AddPolicy("auth", context => RateLimitPartition.GetFixedWindowLimiter(context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions { PermitLimit = authPermitLimit, Window = TimeSpan.FromMinutes(1), QueueLimit = 0 }));
});
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme).AddJwtBearer(o =>
{
    o.MapInboundClaims = false;
    o.TokenValidationParameters = new()
    {
        ValidateIssuer = true,
        ValidateAudience = true,
        ValidateLifetime = true,
        ValidateIssuerSigningKey = true,
        ValidIssuer = options.Issuer,
        ValidAudience = options.Audience,
        IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(options.SigningKey)),
        ClockSkew = TimeSpan.Zero
    };
    o.Events = new JwtBearerEvents
    {
        OnTokenValidated = async context =>
    {
        if (!Guid.TryParse(context.Principal?.FindFirst("sub")?.Value, out var id)) { context.Fail("Invalid session"); return; }
        var version = context.Principal?.FindFirst("version")?.Value ?? "";
        var deviceId = context.Principal?.FindFirst("device")?.Value ?? "";
        var db = context.HttpContext.RequestServices.GetRequiredService<AuthDb>();
        var clock = context.HttpContext.RequestServices.GetRequiredService<IClock>();
        var user = await db.Users.FindAsync(id);
        var device = await db.TrustedDevices.SingleOrDefaultAsync(d => d.UserId == id && d.DeviceId == deviceId);
        var ok = user is { Status: UserStatus.Active } && user.SecurityVersion.ToString() == version &&
            device is { Revoked: false } && (device.TrustExpiresAt is null || clock.UtcNow < device.TrustExpiresAt);
        if (!ok) context.Fail("Invalid session");
    }
    };
});
builder.Services.AddAuthorization();
builder.Services.AddProblemDetails(o => o.CustomizeProblemDetails = ctx =>
{
    ctx.ProblemDetails.Extensions.Remove("exception");
    if (ctx.HttpContext.Items["RequestId"] is string id)
        ctx.ProblemDetails.Extensions["requestId"] = id;
});
builder.Services.AddOpenApi(OpenApiDocumentation.Configure);
// Setup lists are large and repetitive. Brotli is for browsers; gzip stays because React Native's fetch sends only gzip.
builder.Services.AddResponseCompression(o =>
{
    o.EnableForHttps = true;
    o.Providers.Add<BrotliCompressionProvider>();
    o.Providers.Add<GzipCompressionProvider>();
    o.MimeTypes = ResponseCompressionDefaults.MimeTypes.Append("application/problem+json");
});
builder.Services.Configure<BrotliCompressionProviderOptions>(o => o.Level = CompressionLevel.Optimal);
var app = builder.Build();
// Codes sent after their reply are still going out at shutdown; give them a moment rather than drop them.
app.Lifetime.ApplicationStopping.Register(() => app.Services.GetRequiredService<VerificationMailer>().Idle().Wait(TimeSpan.FromSeconds(10)));
app.UseForwardedHeaders();
app.Use(async (context, next) =>
{
    var id = context.Request.Headers["X-Request-ID"].FirstOrDefault()
        ?? Activity.Current?.Id ?? context.TraceIdentifier;
    context.Items["RequestId"] = id;
    context.Response.Headers["X-Request-ID"] = id;
    using (context.RequestServices.GetRequiredService<ILoggerFactory>()
        .CreateLogger("RequestPipeline").BeginScope(new Dictionary<string, object?> { ["RequestId"] = id }))
    {
        await next();
    }
});
app.UseExceptionHandler();
// Auth bodies carry tokens, which compression would expose to a length-based attack (BREACH), so they are never compressed.
app.UseWhen(context => context.Request.Path.StartsWithSegments("/setup"), setup => setup.UseResponseCompression());
app.UseCors();
app.UseRateLimiter();
app.UseAuthentication();
app.UseAuthorization();
app.MapAuth();
app.MapSetup();
app.MapRevenue();
app.MapPettyCash();
app.MapCentralExpenses();
app.MapReports();
app.MapOrganization();
app.MapHealthChecks("/health/live", new HealthCheckOptions { Predicate = _ => false });
app.MapHealthChecks("/health/ready", new HealthCheckOptions { Predicate = check => check.Tags.Contains("ready") });
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));
// The API description (/openapi/v1.json) is for developers and contract tests only; production does not serve it.
if (app.Environment.IsDevelopment() || app.Environment.IsEnvironment("Testing"))
    app.MapOpenApi();
if (!app.Environment.IsEnvironment("Testing"))
{
    await using var scope = app.Services.CreateAsyncScope();
    var db = scope.ServiceProvider.GetRequiredService<AuthDb>();
    string? Option(string name) => Array.IndexOf(args, name) is var at and >= 0 && at + 1 < args.Length && !args[at + 1].StartsWith("--") ? args[at + 1] : null;

    // --migrate: apply pending migrations and exit. Run this once per deployment before starting replicas.
    if (args.Contains("--migrate"))
    {
        if (await db.Database.GetService<IRelationalDatabaseCreator>().ExistsAsync())
            await db.Database.ExecuteSqlRawAsync("""
                IF OBJECT_ID(N'[__EFMigrationsHistory]') IS NOT NULL
                    UPDATE [__EFMigrationsHistory] SET [MigrationId] = N'20260924172309_OrganizationsAndFleet'
                    WHERE [MigrationId] = N'20260924172309_Phase1Setup'
                """);
        await db.Database.MigrateAsync();
        app.Logger.LogInformation("Migrations applied.");
        return;
    }

    // Development auto-migrates the local database for convenience; production must use --migrate.
    if (options.DevelopmentMode)
    {
        if (await db.Database.GetService<IRelationalDatabaseCreator>().ExistsAsync())
            await db.Database.ExecuteSqlRawAsync("""
                IF OBJECT_ID(N'[__EFMigrationsHistory]') IS NOT NULL
                    UPDATE [__EFMigrationsHistory] SET [MigrationId] = N'20260924172309_OrganizationsAndFleet'
                    WHERE [MigrationId] = N'20260924172309_Phase1Setup'
                """);
        await db.Database.MigrateAsync();
        if (string.Equals(Environment.GetEnvironmentVariable("ALLOW_DEMO_SEED"), "true", StringComparison.OrdinalIgnoreCase))
            await DemoSeed.Run(db);
    }

    if (args.Contains("--provision-user"))
    {
        var user = await UserProvisioning.Provision(db, new(
            Option("--provision-user") ?? throw new ArgumentException("A valid email is required"),
            Option("--phone") ?? throw new ArgumentException("--phone <mobile number> is required"),
            Option("--role"), Option("--first-name"), Option("--last-name"), Option("--organization-name")));
        app.Logger.LogInformation("Provisioned {Email}; they can now set a PIN with an email code.", user.Email);
        return;
    }
    if (args.Contains("--remove-user"))
    {
        var address = Option("--remove-user")?.Trim().ToLowerInvariant();
        if (address is null || !System.Net.Mail.MailAddress.TryCreate(address, out _)) throw new ArgumentException("A valid email is required");
        var user = await db.Users.SingleOrDefaultAsync(u => u.Email == address);
        if (user is not null)
        {
            user.Remove();
            foreach (var token in await db.RefreshTokens.Where(t => t.UserId == user.Id).ToListAsync()) token.Revoke();
        }
        await db.SaveChangesAsync();
        return;
    }
    var unassigned = await db.Users.CountAsync(u => u.Status == UserStatus.Active && !db.Memberships.IgnoreQueryFilters().Any(m => m.UserId == u.Id && m.Active));
    if (unassigned > 0)
        app.Logger.LogWarning("{Count} active users have no organization membership and cannot sign in. Run --provision-user <email> --phone <mobile> [--role <role>] for each.", unassigned);
}
app.Run();
public partial class Program { }
