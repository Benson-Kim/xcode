using System.Collections.Concurrent;
using System.Data.Common;
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
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;

namespace Auth.Tests;

public sealed class TestClock : IClock
{
    public DateTimeOffset UtcNow { get; set; } = DateTimeOffset.UtcNow;
    public void Advance(TimeSpan duration) => UtcNow += duration;
}
public sealed class TestEmail : IEmailSender
{
    private int count;
    public ConcurrentDictionary<string, string> Codes { get; } = new();
    public int Count => count;
    // Lets a test hold up or fail a delivery, for example to one address.
    public Func<string, Task>? BeforeSend { get; set; }
    public async Task SendCode(string email, string code, CodePurpose purpose, CancellationToken cancellationToken)
    {
        if (BeforeSend is not null) await BeforeSend(email);
        Codes[email] = code;
        Interlocked.Increment(ref count);
    }
}
// Watches what the API asks of the database: commands run, rows read and transactions opened. A test can also make
// the next commit fail, or slip another writer's change in just before the API's own update of a table.
public sealed class DatabaseProbe : IDbCommandInterceptor, IDbTransactionInterceptor
{
    private int commands, rows, transactions;
    private (string Table, string Sql)? interleave;
    private int interleaveTimes;
    public int Commands => commands;
    public int Rows => rows;
    public int Transactions => transactions;
    public ConcurrentQueue<string> Sql { get; } = new();
    public bool FailNextCommit { get; set; }
    public void Reset()
    {
        commands = rows = transactions = 0;
        Sql.Clear();
    }

    // Runs sql just before each of the next `times` commands that update table: another writer's change landing
    // between the API's read and its write.
    public void Interleave(string table, string sql, int times = 1)
    {
        interleave = (table, sql);
        interleaveTimes = times;
    }

    private string? betweenAttempts;
    private int startsSinceArmed;

    // Runs sql, committed on its own, just before the second transaction opened from now on: another writer's change
    // landing after a unit of work's first attempt rolled back and before it tries again.
    public void BetweenAttempts(string sql)
    {
        betweenAttempts = sql;
        startsSinceArmed = 0;
    }

    public ValueTask<InterceptionResult<DbTransaction>> TransactionStartingAsync(DbConnection connection, TransactionStartingEventData eventData, InterceptionResult<DbTransaction> result, CancellationToken cancellationToken = default)
    {
        if (betweenAttempts is { } sql && ++startsSinceArmed == 2)
        {
            betweenAttempts = null;
            using var change = connection.CreateCommand();
            change.CommandText = sql;
            change.ExecuteNonQuery();
        }
        return ValueTask.FromResult(result);
    }

    private void Executing(DbCommand command)
    {
        Interlocked.Increment(ref commands);
        Sql.Enqueue(command.CommandText);
        if (interleave is not { } other || interleaveTimes == 0 || !command.CommandText.Contains($"UPDATE \"{other.Table}\"", StringComparison.Ordinal))
            return;
        if (--interleaveTimes == 0)
            interleave = null;
        using var change = command.Connection!.CreateCommand();
        change.Transaction = command.Transaction;
        change.CommandText = other.Sql;
        change.ExecuteNonQuery();
    }

    public InterceptionResult<DbDataReader> ReaderExecuting(DbCommand command, CommandEventData eventData, InterceptionResult<DbDataReader> result)
    { Executing(command); return result; }
    public ValueTask<InterceptionResult<DbDataReader>> ReaderExecutingAsync(DbCommand command, CommandEventData eventData, InterceptionResult<DbDataReader> result, CancellationToken cancellationToken = default)
    { Executing(command); return ValueTask.FromResult(result); }
    public InterceptionResult<object> ScalarExecuting(DbCommand command, CommandEventData eventData, InterceptionResult<object> result)
    { Executing(command); return result; }
    public ValueTask<InterceptionResult<object>> ScalarExecutingAsync(DbCommand command, CommandEventData eventData, InterceptionResult<object> result, CancellationToken cancellationToken = default)
    { Executing(command); return ValueTask.FromResult(result); }
    public InterceptionResult<int> NonQueryExecuting(DbCommand command, CommandEventData eventData, InterceptionResult<int> result)
    { Executing(command); return result; }
    public ValueTask<InterceptionResult<int>> NonQueryExecutingAsync(DbCommand command, CommandEventData eventData, InterceptionResult<int> result, CancellationToken cancellationToken = default)
    { Executing(command); return ValueTask.FromResult(result); }
    public InterceptionResult DataReaderDisposing(DbCommand command, DataReaderDisposingEventData eventData, InterceptionResult result)
    { Interlocked.Add(ref rows, eventData.ReadCount); return result; }

    public DbTransaction TransactionStarted(DbConnection connection, TransactionEndEventData eventData, DbTransaction result)
    { Interlocked.Increment(ref transactions); return result; }
    public ValueTask<DbTransaction> TransactionStartedAsync(DbConnection connection, TransactionEndEventData eventData, DbTransaction result, CancellationToken cancellationToken = default)
    { Interlocked.Increment(ref transactions); return ValueTask.FromResult(result); }
    public ValueTask<InterceptionResult> TransactionCommittingAsync(DbTransaction transaction, TransactionEventData eventData, InterceptionResult result, CancellationToken cancellationToken = default)
    {
        if (!FailNextCommit) return ValueTask.FromResult(result);
        FailNextCommit = false;
        throw new InvalidOperationException("Simulated commit failure.");
    }
}
// Keeps error logs with their structured values, so a test can check what an operator would see.
public sealed class TestLogs : ILoggerProvider
{
    public ConcurrentQueue<(string Category, IReadOnlyDictionary<string, object?> Values)> Errors { get; } = new();
    public ILogger CreateLogger(string categoryName) => new Logger(this, categoryName);
    public void Dispose() { }

    private sealed class Logger(TestLogs logs, string category) : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
        public bool IsEnabled(LogLevel logLevel) => logLevel >= LogLevel.Error;
        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            if (IsEnabled(logLevel))
                logs.Errors.Enqueue((category, state is IEnumerable<KeyValuePair<string, object?>> values ? values.ToDictionary() : new()));
        }
    }
}
public sealed class AuthFactory : WebApplicationFactory<Program>
{
    private readonly SqliteConnection connection = new("Data Source=:memory:");
    public TestClock Clock { get; } = new();
    public TestEmail Email { get; } = new();
    public DatabaseProbe Database { get; } = new();
    public TestLogs Logs { get; } = new();
    public AuthFactory() => connection.Open();
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Testing");
        builder.ConfigureLogging(logging => logging.AddProvider(Logs));
        builder.ConfigureServices(services =>
        {
            services.RemoveAll<DbContextOptions<AuthDb>>();
            services.RemoveAll<IDbContextOptionsConfiguration<AuthDb>>();
            services.AddDbContext<AuthDb>(o => o.UseSqlite(connection).AddInterceptors(Database));
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
    // Test organizations use UTC, so results do not depend on the test machine's time zone data.
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
