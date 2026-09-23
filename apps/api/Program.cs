using System.Security.Cryptography;
using System.Text;
using System.Threading.RateLimiting;
using Auth.Api;
using Auth.Application;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;

var builder = WebApplication.CreateBuilder(args);
var options = builder.Configuration.GetSection("Auth").Get<AuthOptions>() ?? new();
if (string.IsNullOrEmpty(options.SigningKey) && (builder.Environment.IsDevelopment() || builder.Environment.IsEnvironment("Testing")))
    options.SigningKey = Convert.ToBase64String(RandomNumberGenerator.GetBytes(48));
if (Encoding.UTF8.GetByteCount(options.SigningKey) < 32) throw new InvalidOperationException("Set Auth__SigningKey to at least 32 random bytes.");
if (options.TrustLifetimeDays is <= 0) throw new InvalidOperationException("TrustLifetimeDays must be positive or null.");

builder.Services.AddSingleton(options);
builder.Services.AddSingleton<IClock, Auth.Infrastructure.SystemClock>();
builder.Services.AddSingleton<TokenIssuer>();
builder.Services.AddSingleton<AuthGate>();
builder.Services.AddScoped<AuthService>();
if (builder.Environment.IsDevelopment() || builder.Environment.IsEnvironment("Testing")) builder.Services.AddScoped<IEmailSender, LogEmailSender>();
else builder.Services.AddScoped<IEmailSender, SmtpEmailSender>();
builder.Services.AddDbContext<AuthDb>(o => o.UseSqlServer(builder.Configuration.GetConnectionString("Auth")));
builder.Services.AddCors(o => o.AddDefaultPolicy(p => p.WithOrigins(builder.Configuration.GetSection("Cors:Origins").Get<string[]>() ?? []).AllowAnyHeader().AllowAnyMethod()));
builder.Services.AddRateLimiter(o =>
{
    o.RejectionStatusCode = 429;
    o.AddPolicy("auth", context => RateLimitPartition.GetFixedWindowLimiter(context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions { PermitLimit = builder.Environment.IsEnvironment("Testing") ? 10000 : 30, Window = TimeSpan.FromMinutes(1), QueueLimit = 0 }));
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
        var db = context.HttpContext.RequestServices.GetRequiredService<AuthDb>();
        var clock = context.HttpContext.RequestServices.GetRequiredService<IClock>();
        if (!Guid.TryParse(context.Principal?.FindFirst("sub")?.Value, out var id)) { context.Fail("Invalid session"); return; }
        var user = await db.Users.FindAsync(id);
        var deviceId = context.Principal?.FindFirst("device")?.Value;
        var device = await db.TrustedDevices.SingleOrDefaultAsync(d => d.UserId == id && d.DeviceId == deviceId);
        if (user is not { Status: UserStatus.Active } || user.SecurityVersion.ToString() != context.Principal?.FindFirst("version")?.Value ||
            device is not { Revoked: false } || (device.TrustExpiresAt is not null && clock.UtcNow >= device.TrustExpiresAt)) context.Fail("Invalid session");
    }
    };
});
builder.Services.AddAuthorization();
builder.Services.AddProblemDetails();
var app = builder.Build();
app.UseExceptionHandler();
app.UseCors();
app.UseRateLimiter();
app.UseAuthentication();
app.UseAuthorization();
app.MapAuth();
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));
if (!app.Environment.IsEnvironment("Testing"))
{
    await using var scope = app.Services.CreateAsyncScope();
    var db = scope.ServiceProvider.GetRequiredService<AuthDb>();
    await db.Database.MigrateAsync();
    if (app.Environment.IsDevelopment()) await DemoSeed.Run(db);
    var provision = Array.IndexOf(args, "--provision-user");
    var remove = Array.IndexOf(args, "--remove-user");
    if (provision >= 0 || remove >= 0)
    {
        var index = Math.Max(provision, remove);
        if (index + 1 >= args.Length || !System.Net.Mail.MailAddress.TryCreate(args[index + 1], out _)) throw new ArgumentException("A valid email is required");
        var address = args[index + 1].Trim().ToLowerInvariant();
        var user = await db.Users.SingleOrDefaultAsync(u => u.Email == address);
        if (provision >= 0 && user is null) db.Users.Add(new User { Email = address });
        if (remove >= 0 && user is not null)
        {
            user.Status = UserStatus.Removed;
            user.SecurityVersion++;
            foreach (var token in await db.RefreshTokens.Where(t => t.UserId == user.Id).ToListAsync()) token.Revoked = true;
        }
        await db.SaveChangesAsync();
        return;
    }
}
app.Run();
public partial class Program { }
