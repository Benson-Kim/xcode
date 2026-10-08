using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using Auth.Application;
using Auth.Application.Authentication;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace Auth.Tests;

public sealed class AuthTests : IDisposable
{
    private readonly AuthFactory app = new();
    private readonly HttpClient client;
    private const string Address = "person@example.com";
    public AuthTests() => client = app.CreateClient();
    private VerificationMailer Mailer => app.Services.GetRequiredService<VerificationMailer>();
    private AuthRequest Request(string phoneNumber = "+254712345678", string pin = "5826", string device = "phone", string code = "", string refresh = "") => new(PhoneNumber: phoneNumber, Pin: pin, DeviceId: device, Code: code, RefreshToken: refresh);
    private async Task<(HttpStatusCode Status, AuthResponse Body)> Post(string path, AuthRequest? request = null)
    {
        var response = await client.PostAsJsonAsync("/auth/" + path, request ?? Request());
        // Setup and reset codes go out after the reply; wait for them so the test sees what the person received.
        await Mailer.Idle();
        var body = await response.Content.ReadFromJsonAsync<AuthResponse>();
        Assert.NotNull(body);
        return (response.StatusCode, body);
    }
    // Five wrong PINs on the trusted phone: the fifth starts the pause, and already shows its timer.
    private async Task Pause(string path = "sign-in")
    {
        for (var i = 0; i < 4; i++) Assert.Equal(HttpStatusCode.Unauthorized, (await Post(path, Request(pin: "9998"))).Status);
        Assert.Equal((HttpStatusCode)423, (await Post(path, Request(pin: "9998"))).Status);
    }
    // Everything a caller can see of a response, to compare two byte for byte.
    private async Task<string> Seen(string path, AuthRequest request)
    {
        using var response = await client.PostAsJsonAsync("/auth/" + path, request);
        await Mailer.Idle();
        var headers = string.Join("; ", response.Headers.Concat(response.Content.Headers)
            .Where(x => x.Key is not ("Date" or "Content-Length" or "X-Request-ID")).OrderBy(x => x.Key).Select(x => $"{x.Key}={string.Join(",", x.Value)}"));
        return $"{(int)response.StatusCode} {headers} {await response.Content.ReadAsStringAsync()}";
    }
    private const string Unknown = "+254700000000";
    // Out-of-range values an earlier version could store (a lockout after one try, a day-long pause), written past the
    // database's own checks.
    private Task StoreOutOfRangePolicy() => app.WithDb(db => db.Database.ExecuteSqlRawAsync(
        "PRAGMA ignore_check_constraints = 1; " +
        "UPDATE \"SecurityPolicies\" SET \"LockoutThreshold\" = 1, \"LockoutMinutes\" = 1440, \"AccessTokenMinutes\" = 120, \"RefreshTokenDays\" = 365; " +
        "PRAGMA ignore_check_constraints = 0;"));

    [Fact]
    public async Task APauseLooksLikeAnUnknownNumberExceptOnATrustedDevice()
    {
        await app.Seed();
        await Pause();

        // On a device this account has not trusted, a paused account answers exactly like a number with no account,
        // whatever PIN is tried, on sign-in and unlock alike.
        foreach (var path in new[] { "sign-in", "unlock" })
            foreach (var pin in new[] { "5826", "9998" })
                Assert.Equal(await Seen(path, Request(phoneNumber: Unknown, pin: pin, device: "stranger")), await Seen(path, Request(pin: pin, device: "stranger")));
        await app.WithDb(async db => Assert.Equal(5, (await db.Users.SingleAsync()).FailedAttempts));

        // The phone the person already trusts keeps showing the timer (Phase 1 phones depend on it).
        var trusted = await Post("sign-in");
        Assert.Equal((HttpStatusCode)423, trusted.Status);
        Assert.Equal("paused", trusted.Body.Status);
        Assert.Equal(900, trusted.Body.RetryAfterSeconds);
        Assert.Equal((HttpStatusCode)423, (await Post("unlock")).Status);
    }

    [Theory]
    [InlineData("sign-in")]
    [InlineData("unlock")]
    public async Task TheWrongPinThatStartsAPauseShowsTheTimerOnATrustedDevice(string path)
    {
        await app.Seed();
        for (var i = 0; i < 4; i++) Assert.Equal(HttpStatusCode.Unauthorized, (await Post(path, Request(pin: "9998"))).Status);

        // The fifth wrong PIN starts the pause, and the person sees the timer now rather than on their next try.
        var paused = await Post(path, Request(pin: "9998"));
        Assert.Equal((HttpStatusCode)423, paused.Status);
        Assert.Equal("paused", paused.Body.Status);
        Assert.Equal(900, paused.Body.RetryAfterSeconds);
        await app.WithDb(async db => Assert.Equal(app.Clock.UtcNow.AddMinutes(15), (await db.Users.SingleAsync()).PausedUntil));
    }

    [Theory]
    [InlineData("sign-in")]
    [InlineData("unlock")]
    public async Task UntrustedDeviceWrongPinsDoNotLockTheAccount(string path)
    {
        await app.Seed();
        // Wrong PINs from an untrusted device are tracked for monitoring but do not lock the account.
        for (var i = 0; i < 10; i++) await Post(path, Request(pin: "9998", device: "stranger"));

        await app.WithDb(async db =>
        {
            var user = await db.Users.SingleAsync();
            Assert.Equal(0, user.FailedAttempts);
            Assert.Null(user.PausedUntil);
            Assert.Equal(10, user.UntrustedFailedAttempts);
        });

        // The legitimate user on their trusted device can still sign in.
        Assert.Equal(HttpStatusCode.OK, (await Post(path)).Status);
    }

    [Fact]
    public async Task PastTheAccountLimitAnUntrustedDeviceLearnsNothingFromThePin()
    {
        await app.Seed();
        for (var i = 0; i < SignInService.UntrustedAttemptLimit; i++)
            Assert.Equal(HttpStatusCode.Unauthorized, (await Post("sign-in", Request(pin: "9998", device: $"stranger-{i}"))).Status);

        Assert.Equal(await Post("sign-in", Request(phoneNumber: Unknown, device: "stranger")), await Post("sign-in", Request(device: "stranger")));
        Assert.Equal(0, app.Email.Count);

        Assert.Equal(HttpStatusCode.OK, (await Post("sign-in")).Status);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("sign-in", Request(device: "stranger"))).Status);

        Assert.Equal(HttpStatusCode.Accepted, (await Post("pin-reset/request", Request(device: "stranger"))).Status);
        Assert.Equal(HttpStatusCode.OK, (await Post("pin-reset/complete", Request(pin: "4719", device: "stranger", code: app.Email.Codes[Address]))).Status);
        Assert.Equal(HttpStatusCode.Accepted, (await Post("sign-in", Request(pin: "4719", device: "another"))).Status);
    }

    [Fact]
    public async Task AStaleWriteToAPersonOrTheirSessionConflictsRatherThanOverwrites()
    {
        await app.Seed();
        Assert.Equal(HttpStatusCode.OK, (await Post("sign-in")).Status);
        await Stale(db => db.Users.SingleAsync(), user => user.RecordFailedAttempt());
        await Stale(db => db.RefreshTokens.SingleAsync(), token => token.Revoke());
    }

    private Task Stale<T>(Func<AuthDb, Task<T>> load, Action<T> change) => app.WithDb(first => app.WithDb(async second =>
    {
        var stale = await load(first);
        change(await load(second));
        await second.SaveChangesAsync();
        change(stale);
        await Assert.ThrowsAsync<DbUpdateConcurrencyException>(() => first.SaveChangesAsync());
    }));

    [Fact]
    public async Task ANumberThatIsNotAPhoneNumberReachesNoAccount()
    {
        // Accounts made before phone sign-in have no number yet. Input that is not a phone number normalizes to
        // nothing, and must not reach them.
        await app.WithDb(async db =>
        {
            await db.Database.EnsureCreatedAsync();
            await AuthFactory.AddOrganization(db);
            db.Users.Add(new User { Email = "legacy.one@example.com" });
            await db.SaveChangesAsync();
        });
        Assert.Equal(await Seen("setup-pin/request", Request(phoneNumber: Unknown)), await Seen("setup-pin/request", Request(phoneNumber: "not a number")));
        Assert.Equal(0, app.Email.Count);

        // With two such accounts the lookup used to fail with a 500.
        await app.WithDb(async db => { db.Users.Add(new User { Email = "legacy.two@example.com" }); await db.SaveChangesAsync(); });
        foreach (var path in new[] { "sign-in", "setup-pin/request", "setup-pin/verify", "setup-pin/complete", "verify-device" })
            Assert.Equal(await Seen(path, Request(phoneNumber: Unknown, pin: "6942")), await Seen(path, Request(phoneNumber: "not a number", pin: "6942")));
        Assert.Equal(0, app.Email.Count);
    }

    [Fact]
    public async Task ACodeRequestDoesNotWaitForTheMailServer()
    {
        // Only a real account's request sends an email, so waiting for the mail server would tell callers which
        // numbers have accounts. The reply goes first; the code follows.
        await app.Seed();
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        app.Email.BeforeSend = _ => release.Task;
        try
        {
            var request = client.PostAsJsonAsync("/auth/pin-reset/request", Request());
            Assert.Same(request, await Task.WhenAny(request, Task.Delay(TimeSpan.FromSeconds(20))));
            Assert.Equal(HttpStatusCode.Accepted, (await request).StatusCode);
            Assert.Equal(0, app.Email.Count);
        }
        finally { release.TrySetResult(); }
        for (var wait = 0; app.Email.Count == 0 && wait < 200; wait++) await Task.Delay(50);
        Assert.Equal(1, app.Email.Count);
        Assert.Equal(HttpStatusCode.OK, (await Post("pin-reset/complete", Request(pin: "6942", code: app.Email.Codes[Address]))).Status);
    }

    [Fact]
    public async Task AStoredPolicyOutsideTheBoundsIsEnforcedWithinThem()
    {
        await app.Seed();
        await StoreOutOfRangePolicy();

        // Access tokens last at most 15 minutes and refresh tokens at most 90 days.
        var signedIn = await Post("sign-in");
        var jwt = new System.IdentityModel.Tokens.Jwt.JwtSecurityTokenHandler().ReadJwtToken(signedIn.Body.AccessToken);
        Assert.Equal(TimeSpan.FromMinutes(15), jwt.ValidTo - jwt.ValidFrom);
        await app.WithDb(async db => Assert.Equal(app.Clock.UtcNow.AddDays(90), (await db.RefreshTokens.SingleAsync()).ExpiresAt));

        // One wrong PIN no longer pauses the account: it takes at least three.
        await Post("sign-in", Request(pin: "9998"));
        await app.WithDb(async db => Assert.Null((await db.Users.SingleAsync()).PausedUntil));
        await Post("sign-in", Request(pin: "9998"));
        await Post("sign-in", Request(pin: "9998"));

        // And the pause lasts at most an hour, not a day.
        var paused = await Post("sign-in");
        Assert.Equal((HttpStatusCode)423, paused.Status);
        Assert.Equal(3600, paused.Body.RetryAfterSeconds);
    }
    [Fact]
    public async Task AUTH01_TrustedSignInIssuesTokens_And_OPEN05_ResetsFailures()
    {
        await app.Seed();
        await Post("sign-in", Request(pin: "9998"));
        var result = await Post("sign-in");
        Assert.Equal(HttpStatusCode.OK, result.Status);
        Assert.Equal(3, result.Body.AccessToken!.Split('.').Length);
        Assert.NotEmpty(result.Body.RefreshToken!);
        await app.WithDb(async db =>
        {
            Assert.Equal(0, (await db.Users.SingleAsync()).FailedAttempts);
            Assert.NotEqual(result.Body.RefreshToken, (await db.RefreshTokens.SingleAsync()).TokenHash);
        });
    }
    [Fact]
    public async Task AUTH02_WrongPinIncrementsAndUsesGenericFailure()
    {
        await app.Seed();
        var wrong = await Post("sign-in", Request(pin: "9998"));
        var unknown = await Post("sign-in", Request(pin: "9998") with { PhoneNumber = "+254700000000" });
        Assert.Equal(unknown, wrong);
        await app.WithDb(async db => Assert.Equal(1, (await db.Users.SingleAsync()).FailedAttempts));
    }
    [Fact]
    public async Task AUTH03_FifthFailurePauses_AUTH04_ExpiryResetsAtFifteenMinutes()
    {
        await app.Seed();
        await Pause();
        var paused = await Post("sign-in");
        Assert.Equal((HttpStatusCode)423, paused.Status);
        Assert.Equal(900, paused.Body.RetryAfterSeconds);
        app.Clock.Advance(TimeSpan.FromMinutes(15) - TimeSpan.FromTicks(1));
        Assert.Equal((HttpStatusCode)423, (await Post("sign-in")).Status);
        app.Clock.Advance(TimeSpan.FromTicks(1));
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("sign-in", Request(pin: "9998"))).Status);
        await app.WithDb(async db => { var u = await db.Users.SingleAsync(); Assert.Equal(1, u.FailedAttempts); Assert.Null(u.PausedUntil); });
        Assert.Equal(HttpStatusCode.OK, (await Post("sign-in")).Status);
    }
    [Fact]
    public async Task AUTH05_ResetClearsPause_AUTH14_ChangesPinAndInvalidatesOldTokens()
    {
        await app.Seed();
        var old = await Post("sign-in");
        await Pause();
        Assert.Equal(HttpStatusCode.Accepted, (await Post("pin-reset/request")).Status);
        var reset = await Post("pin-reset/complete", Request(pin: "6942", code: app.Email.Codes[Address]));
        Assert.Equal(HttpStatusCode.OK, reset.Status);
        await app.WithDb(async db => { var u = await db.Users.SingleAsync(); Assert.Equal(0, u.FailedAttempts); Assert.Null(u.PausedUntil); Assert.True(PinHasher.Verify("6942", u.PinHash!)); });
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("refresh", Request(refresh: old.Body.RefreshToken!))).Status);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("sign-in")).Status);
        Assert.Equal(HttpStatusCode.OK, (await Post("sign-in", Request(pin: "6942"))).Status);
        client.DefaultRequestHeaders.Authorization = new("Bearer", old.Body.AccessToken);
        Assert.Equal(HttpStatusCode.Unauthorized, (await client.PostAsJsonAsync("/auth/devices/phone/revoke", new { })).StatusCode);
    }
    [Theory]
    [InlineData(0, true)]
    [InlineData(1, false)]
    public async Task AUTH06_CodeExpiry_OPEN04_InclusiveBoundary(long ticksAfterExpiry, bool valid)
    {
        await app.Seed(withPin: false, trusted: false);
        await Post("setup-pin/request");
        app.Clock.Advance(TimeSpan.FromMinutes(10) + TimeSpan.FromTicks(ticksAfterExpiry));
        var result = await Post("setup-pin/complete", Request(code: app.Email.Codes[Address]));
        Assert.Equal(valid ? HttpStatusCode.OK : HttpStatusCode.Unauthorized, result.Status);
    }
    [Fact]
    public async Task AUTH07_WrongCodeDoesNotTrustAndFiveWrongCodesInvalidateChallenge()
    {
        await app.Seed(trusted: false);
        await Post("sign-in");
        var correct = app.Email.Codes[Address];
        var wrong = correct == "000000" ? "000001" : "000000";
        for (var i = 0; i < 5; i++) Assert.Equal(HttpStatusCode.Unauthorized, (await Post("verify-device", Request(code: wrong))).Status);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("verify-device", Request(code: correct))).Status);
        await app.WithDb(async db => { Assert.Empty(await db.TrustedDevices.ToListAsync()); Assert.Empty(await db.RefreshTokens.ToListAsync()); });
    }
    [Fact]
    public async Task AUTH08_FirstPinRequired_AUTH09_SetupRequiresEmailCode()
    {
        await app.Seed(withPin: false, trusted: false);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("sign-in")).Status);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("setup-pin/complete")).Status);
        await Post("setup-pin/request");
        var code = app.Email.Codes[Address];
        Assert.Equal(HttpStatusCode.OK, (await Post("setup-pin/complete", Request(code: code))).Status);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("setup-pin/complete", Request(code: code))).Status);
        Assert.Equal(HttpStatusCode.OK, (await Post("sign-in")).Status);
    }
    [Theory]
    [InlineData("1111")]
    [InlineData("0000")]
    [InlineData("1234")]
    [InlineData("4321")]
    [InlineData("01234567")]
    [InlineData("87654321")]
    [InlineData("123")]
    [InlineData("123456789")]
    [InlineData("１２３４")]
    [InlineData("58a6")]
    public async Task AUTH10_AUTH11_WeakPinsRejectedOnSetupAndReset(string pin)
    {
        Assert.False(PinRules.IsValid(pin));
        await app.Seed(withPin: false);
        await Post("setup-pin/request");
        Assert.Equal(HttpStatusCode.BadRequest, (await Post("setup-pin/complete", Request(pin: pin, code: app.Email.Codes[Address]))).Status);
        await Post("pin-reset/request");
        Assert.Equal(HttpStatusCode.BadRequest, (await Post("pin-reset/complete", Request(pin: pin, code: app.Email.Codes[Address]))).Status);
        await app.WithDb(async db => Assert.Null((await db.Users.SingleAsync()).PinHash));
    }
    [Fact]
    public async Task PinResetCannotCreateTheFirstPin()
    {
        await app.Seed(withPin: false);
        Assert.Equal(HttpStatusCode.Accepted, (await Post("pin-reset/request")).Status);
        Assert.Empty(app.Email.Codes);

        var result = await Post("pin-reset/complete", Request(pin: "6942", code: "000000"));
        Assert.Equal(HttpStatusCode.Unauthorized, result.Status);
        await app.WithDb(async db => Assert.Null((await db.Users.SingleAsync()).PinHash));
    }
    [Fact]
    public async Task DeviceCannotRevokeAnotherDevice()
    {
        await app.Seed();
        var signedIn = await Post("sign-in");
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", signedIn.Body.AccessToken);

        Assert.Equal(HttpStatusCode.Forbidden,
            (await client.PostAsJsonAsync("/auth/devices/another-device/revoke", new { })).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await Post("refresh", Request(refresh: signedIn.Body.RefreshToken!))).Status);
    }
    [Fact]
    public async Task AUTH12_RemovedUserCannotSignInRefreshOrUseAccessToken()
    {
        await app.Seed();
        var signedIn = await Post("sign-in");
        await app.WithDb(async db => { (await db.Users.SingleAsync()).Status = UserStatus.Removed; await db.SaveChangesAsync(); });
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("sign-in")).Status);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("refresh", Request(refresh: signedIn.Body.RefreshToken!))).Status);
        await app.WithDb(async db => Assert.All(await db.RefreshTokens.ToListAsync(), t => Assert.True(t.Revoked)));
        client.DefaultRequestHeaders.Authorization = new("Bearer", signedIn.Body.AccessToken);
        Assert.Equal(HttpStatusCode.Unauthorized, (await client.PostAsJsonAsync("/auth/devices/phone/revoke", new { })).StatusCode);
    }
    [Fact]
    public async Task AUTH13_NewDevice_OPEN01_VerificationPersistsTrustAndConsumesCode()
    {
        await app.Seed(trusted: false);
        var challenge = await Post("sign-in");
        Assert.Equal("verification_required", challenge.Body.Status);
        Assert.Null(challenge.Body.AccessToken);
        var code = app.Email.Codes[Address];
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("verify-device", Request(device: "different", code: code))).Status);
        Assert.Equal(HttpStatusCode.OK, (await Post("verify-device", Request(code: code))).Status);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("verify-device", Request(code: code))).Status);
        Assert.Equal(HttpStatusCode.OK, (await Post("sign-in")).Status);
        Assert.Equal(1, app.Email.Count);
        await app.WithDb(async db => Assert.False((await db.TrustedDevices.SingleAsync()).Revoked));
    }
    [Fact]
    public async Task AUTH15_TrustedUnlock_OPEN03_SharesFailedAttemptCounter()
    {
        await app.Seed();
        Assert.Equal(HttpStatusCode.OK, (await Post("unlock")).Status);
        Assert.Equal(0, app.Email.Count);
        for (var i = 0; i < 4; i++) await Post("unlock", Request(pin: "9998"));
        await Post("sign-in", Request(pin: "9998"));
        Assert.Equal((HttpStatusCode)423, (await Post("unlock")).Status);
        Assert.Equal((HttpStatusCode)423, (await Post("sign-in")).Status);
    }
    [Fact]
    public async Task OPEN02_RevocationInvalidatesRefreshAndRequiresVerificationAgain()
    {
        await app.Seed();
        var signedIn = await Post("sign-in");
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", signedIn.Body.AccessToken);
        Assert.Equal(HttpStatusCode.OK, (await client.PostAsJsonAsync("/auth/devices/phone/revoke", new { })).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("refresh", Request(refresh: signedIn.Body.RefreshToken!))).Status);
        Assert.Equal("verification_required", (await Post("unlock")).Body.Status);
    }
    [Fact]
    public async Task OPEN02_ConfiguredTrustExpiryRequiresVerificationAtExpiry()
    {
        await app.Seed(trusted: false);
        app.Services.GetRequiredService<AuthOptions>().TrustLifetimeDays = 1;
        await Post("sign-in");
        await Post("verify-device", Request(code: app.Email.Codes[Address]));
        await app.WithDb(async db => Assert.Equal(app.Clock.UtcNow.AddDays(1), (await db.TrustedDevices.SingleAsync()).TrustExpiresAt));
        app.Clock.Advance(TimeSpan.FromDays(1));
        Assert.Equal("verification_required", (await Post("unlock")).Body.Status);
    }
    [Fact]
    public async Task RefreshRotatesRejectsReplayAndSignOutRevokesSession()
    {
        await app.Seed();
        var first = await Post("sign-in");
        await Post("sign-in", Request(pin: "9998"));
        var rotated = await Post("refresh", Request(refresh: first.Body.RefreshToken!));
        Assert.Equal(HttpStatusCode.OK, rotated.Status);
        Assert.NotEqual(first.Body.RefreshToken, rotated.Body.RefreshToken);
        await app.WithDb(async db => Assert.Equal(1, (await db.Users.SingleAsync()).FailedAttempts));
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("refresh", Request(refresh: first.Body.RefreshToken!))).Status);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("refresh", Request(refresh: rotated.Body.RefreshToken!))).Status);
        var next = await Post("sign-in");
        Assert.Equal(HttpStatusCode.OK, (await Post("sign-out", Request(refresh: next.Body.RefreshToken!))).Status);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("refresh", Request(refresh: next.Body.RefreshToken!))).Status);
    }
    [Fact]
    public async Task PurposeBindingGenericRequestsAndResendCooldown()
    {
        await app.Seed();
        var known = await Post("pin-reset/request");
        var unknown = await Post("pin-reset/request", Request() with { PhoneNumber = "+254700000000" });
        Assert.Equal(known, unknown);
        await Post("pin-reset/request");
        Assert.Equal(1, app.Email.Count);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("verify-device", Request(code: app.Email.Codes[Address]))).Status);
        Assert.Equal(HttpStatusCode.OK, (await Post("pin-reset/complete", Request(pin: "6942", code: app.Email.Codes[Address]))).Status);
    }
    [Fact]
    public async Task ConcurrentFailuresCannotLoseAttempts()
    {
        await app.Seed();
        await Task.WhenAll(Enumerable.Range(0, 5).Select(_ => Post("sign-in", Request(pin: "9998"))));
        await app.WithDb(async db => Assert.Equal(5, (await db.Users.SingleAsync()).FailedAttempts));
        Assert.Equal((HttpStatusCode)423, (await Post("sign-in")).Status);
    }
    [Fact]
    public async Task SetupAndResetCodeChecksCountFailedAttempts()
    {
        await app.Seed(withPin: false, trusted: false);
        await Post("setup-pin/request");
        var correct = app.Email.Codes[Address];
        var wrong = correct == "000000" ? "000001" : "000000";
        for (var i = 0; i < 5; i++) Assert.Equal(HttpStatusCode.Unauthorized, (await Post("setup-pin/verify", Request(code: wrong))).Status);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("setup-pin/verify", Request(code: correct))).Status);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("setup-pin/complete", Request(pin: "6942", code: correct))).Status);
    }
    [Fact]
    public async Task CorrectCodeCheckDoesNotConsumeTheCode()
    {
        await app.Seed(withPin: false, trusted: false);
        await Post("setup-pin/request");
        var code = app.Email.Codes[Address];
        Assert.Equal("code_verified", (await Post("setup-pin/verify", Request(code: code))).Body.Status);
        Assert.Equal(HttpStatusCode.OK, (await Post("setup-pin/complete", Request(pin: "6942", code: code))).Status);
    }
    [Fact]
    public async Task SavedSecurityPolicyControlsLockoutAndTokenLifetimes()
    {
        await app.Seed();
        await app.Policy(p => { p.LockoutThreshold = 3; p.LockoutMinutes = 2; p.AccessTokenMinutes = 5; p.RefreshTokenDays = 7; });
        var signedIn = await Post("sign-in");
        var jwt = new System.IdentityModel.Tokens.Jwt.JwtSecurityTokenHandler().ReadJwtToken(signedIn.Body.AccessToken);
        Assert.Equal(TimeSpan.FromMinutes(5), jwt.ValidTo - jwt.ValidFrom);
        await app.WithDb(async db => Assert.Equal(app.Clock.UtcNow.AddDays(7), (await db.RefreshTokens.SingleAsync()).ExpiresAt));

        for (var i = 0; i < 3; i++) await Post("sign-in", Request(pin: "9998"));
        var paused = await Post("sign-in");
        Assert.Equal((HttpStatusCode)423, paused.Status);
        Assert.Equal(120, paused.Body.RetryAfterSeconds);
    }
    [Fact]
    public async Task PolicyPinLengthAppliesToNewPinsAndIsOnlyDisclosedWithAValidCode()
    {
        await app.Seed();
        await app.Policy(p => p.PinLength = 6);
        Assert.Equal(HttpStatusCode.OK, (await Post("sign-in")).Status); // existing four-digit PIN still works
        await Post("pin-reset/request");
        var code = app.Email.Codes[Address];
        var wrong = code == "000000" ? "000001" : "000000";
        Assert.Equal(HttpStatusCode.Unauthorized, (await Post("pin-reset/complete", Request(pin: "6942", code: wrong))).Status);
        var tooShort = await Post("pin-reset/complete", Request(pin: "6942", code: code));
        Assert.Equal(HttpStatusCode.BadRequest, tooShort.Status);
        Assert.Equal(6, tooShort.Body.MinimumPinLength);
        Assert.Equal(HttpStatusCode.OK, (await Post("pin-reset/complete", Request(pin: "694213", code: code))).Status);
    }
    [Fact]
    public async Task ReprovisioningAnExistingAccountRevokesItsOldSession()
    {
        await app.Seed();
        var signedIn = await Post("sign-in");

        // Repeating the same provisioning changes nothing, so the session is kept (provisioning is idempotent).
        await app.WithDb(async db =>
            await UserProvisioning.Provision(db, new(Address, "0712345678", "Revenue clerk")));
        var kept = await Post("refresh", Request(refresh: signedIn.Body.RefreshToken!));
        Assert.Equal(HttpStatusCode.OK, kept.Status);

        // A new role must take effect on every device, so every earlier credential is revoked.
        await app.WithDb(async db =>
            await UserProvisioning.Provision(db, new(Address, "0712345678", "Fleet manager")));
        Assert.Equal(HttpStatusCode.Unauthorized,
            (await Post("refresh", Request(refresh: kept.Body.RefreshToken!))).Status);
    }

    [Fact]
    public async Task AnEmailResetLiftsTheLongestPause()
    {
        await app.Seed();
        // Addendum 1: at least three tries, a pause of at most one hour, and a reset by email still lifts it.
        await Assert.ThrowsAsync<ArgumentException>(() => app.Policy(p => p.LockoutThreshold = 2));
        await Assert.ThrowsAsync<ArgumentException>(() => app.Policy(p => p.LockoutMinutes = 61));
        await app.Policy(p => { p.LockoutThreshold = 3; p.LockoutMinutes = 60; });

        for (var i = 0; i < 2; i++) Assert.Equal(HttpStatusCode.Unauthorized, (await Post("sign-in", Request(pin: "9998"))).Status);
        Assert.Equal((HttpStatusCode)423, (await Post("sign-in", Request(pin: "9998"))).Status);
        var paused = await Post("sign-in");
        Assert.Equal((HttpStatusCode)423, paused.Status);
        Assert.Equal(3600, paused.Body.RetryAfterSeconds);

        Assert.Equal(HttpStatusCode.Accepted, (await Post("pin-reset/request")).Status);
        Assert.Equal(HttpStatusCode.OK, (await Post("pin-reset/complete", Request(pin: "6942", code: app.Email.Codes[Address]))).Status);
        Assert.Equal(HttpStatusCode.OK, (await Post("sign-in", Request(pin: "6942"))).Status);
    }

    [Fact]
    public async Task AFailedCommitSendsNoEmail()
    {
        await app.Seed(trusted: false);
        app.Database.FailNextCommit = true;

        using var response = await client.PostAsJsonAsync("/auth/sign-in", Request());

        Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
        Assert.Equal(0, app.Email.Count);
        await app.WithDb(async db => Assert.Empty(await db.VerificationCodes.ToListAsync()));
    }

    [Fact]
    public async Task ACodeFromARolledBackAttemptIsNeverSent()
    {
        await app.Seed(trusted: false);
        app.ExecutionStrategy = d => new RetryOnSimulatedFailure(d);
        app.Database.FailNextCommit = true;
        // The retry finds the person removed, so it issues no code of its own.
        app.Database.BetweenAttempts("UPDATE \"Users\" SET \"Status\" = 1");
        app.Database.Reset();

        var (status, _) = await Post("sign-in");

        Assert.Equal(HttpStatusCode.Unauthorized, status);
        Assert.Equal(2, app.Database.Transactions);
        Assert.Equal(0, app.Email.Count);
        await app.WithDb(async db => Assert.Empty(await db.VerificationCodes.ToListAsync()));
    }

    [Fact]
    public async Task ARetriedAttemptStartsFromTheDatabase()
    {
        await app.Seed();
        app.ExecutionStrategy = d => new RetryOnSimulatedFailure(d);
        app.Database.FailNextCommit = true;
        app.Database.Reset();

        var (status, _) = await Post("sign-in", Request(pin: "9998"));

        Assert.Equal(HttpStatusCode.Unauthorized, status);
        Assert.Equal(2, app.Database.Transactions);
        await app.WithDb(async db => Assert.Equal(1, (await db.Users.SingleAsync()).FailedAttempts));
    }

    [Fact]
    public async Task RevokingADeviceWaitsForTheAccountsOtherAuthWork()
    {
        await app.Seed();
        var signedIn = await Post("sign-in");
        client.DefaultRequestHeaders.Authorization = new("Bearer", signedIn.Body.AccessToken);
        var account = app.Services.GetRequiredService<AuthGate>().For(PhoneNumber.Normalize("+254712345678"));
        await account.WaitAsync();

        var revoking = client.PostAsJsonAsync("/auth/devices/phone/revoke", new { });
        await Task.WhenAny(revoking, Task.Delay(TimeSpan.FromSeconds(2)));
        Assert.False(revoking.IsCompleted);

        account.Release();
        using var response = await revoking;
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task ASlowEmailDoesNotHoldUpOtherSignIns()
    {
        await app.SeedDemo();
        const string owner = "antony.maina@shamayah.co.ke";
        var sending = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        app.Email.BeforeSend = email =>
        {
            if (email != owner) return Task.CompletedTask;
            sending.TrySetResult();
            return release.Task;
        };
        try
        {
            // The Owner signs in on a new device and the mail server stalls on their code.
            var slow = client.PostAsJsonAsync("/auth/sign-in", new AuthRequest(PhoneNumber: "0733520614", Pin: "4826", DeviceId: "owner-phone"));
            await sending.Task.WaitAsync(TimeSpan.FromSeconds(30));

            // Meanwhile the clerk's sign-in completes.
            using var other = app.CreateClient();
            var clerk = other.PostAsJsonAsync("/auth/sign-in", new AuthRequest(PhoneNumber: "0712345678", Pin: "2580", DeviceId: "clerk-phone"));
            Assert.Same(clerk, await Task.WhenAny(clerk, Task.Delay(TimeSpan.FromSeconds(20))));
            Assert.Equal(HttpStatusCode.Accepted, (await clerk).StatusCode);
            Assert.False(slow.IsCompleted);

            release.SetResult();
            Assert.Equal(HttpStatusCode.Accepted, (await slow).StatusCode);
            Assert.True(app.Email.Codes.ContainsKey(owner));
        }
        finally { release.TrySetResult(); }
    }

    // Anyone can call these with any number, so a failed delivery must look exactly like a request for a number with
    // no account: the same 202 check_email. The failure is logged and the code withdrawn, so a retry sends a new one.
    [Theory]
    [InlineData("setup-pin/request", false)]
    [InlineData("pin-reset/request", true)]
    public async Task ACodeRequestWhoseEmailFailsLooksLikeAnyOtherRequest(string path, bool withPin)
    {
        await app.Seed(withPin: withPin, trusted: false);
        var noAccount = await Post(path, Request(phoneNumber: "+254700000000"));
        app.Email.BeforeSend = _ => throw new System.Net.Mail.SmtpException("Mail server unavailable");

        var failed = await Post(path);
        Assert.Equal(noAccount, failed);
        Assert.Equal(HttpStatusCode.Accepted, failed.Status);
        Assert.Equal(new AuthResponse("check_email"), failed.Body);
        await app.WithDb(async db => Assert.True((await db.VerificationCodes.SingleAsync()).Consumed));
        var logged = Assert.Single(app.Logs.Errors, x => x.Category == typeof(VerificationMailer).FullName);
        Assert.IsType<Guid>(logged.Values["UserId"]);
        Assert.False(string.IsNullOrEmpty(logged.Values["CorrelationId"]?.ToString()));

        app.Email.BeforeSend = null;
        Assert.Equal(HttpStatusCode.Accepted, (await Post(path)).Status);
        Assert.Equal(1, app.Email.Count);
    }

    [Fact]
    public async Task AnUndeliveredCodeIsWithdrawnSoARetryCanSendAnother()
    {
        await app.Seed(trusted: false);
        app.Email.BeforeSend = _ => throw new System.Net.Mail.SmtpException("Mail server unavailable");

        // The caller has already proven they know the PIN, so saying the service is unavailable reveals nothing.
        var failed = await Post("sign-in");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, failed.Status);
        Assert.Equal(new AuthResponse("service_unavailable"), failed.Body);
        await app.WithDb(async db => Assert.True((await db.VerificationCodes.SingleAsync()).Consumed));
        var logged = Assert.Single(app.Logs.Errors, x => x.Category == typeof(VerificationMailer).FullName);
        Assert.False(string.IsNullOrEmpty(logged.Values["CorrelationId"]?.ToString()));

        // The one-minute resend cooldown ignores codes that never went out, so a retry right away sends a new one.
        app.Email.BeforeSend = null;
        Assert.Equal(HttpStatusCode.Accepted, (await Post("sign-in")).Status);
        Assert.Equal(HttpStatusCode.OK, (await Post("verify-device", Request(code: app.Email.Codes[Address]))).Status);
        // A delivered code still starts the cooldown.
        Assert.Equal(HttpStatusCode.Accepted, (await Post("pin-reset/request")).Status);
        Assert.Equal(HttpStatusCode.Accepted, (await Post("pin-reset/request")).Status);
        Assert.Equal(2, app.Email.Count);
    }

    [Fact]
    public async Task ProvisionedPeopleCanSetAPinAndSignIn_AndReprovisioningKeepsTheirRole()
    {
        await app.WithDb(async db =>
        {
            await db.Database.EnsureCreatedAsync();
            await AuthFactory.AddOrganization(db);
            // Legacy email-only accounts have no number yet; the filtered unique index allows several of them.
            db.Users.AddRange(new User { Email = "legacy.one@example.com" }, new User { Email = "legacy.two@example.com" });
            await db.SaveChangesAsync();
            await UserProvisioning.Provision(db, new("new.person@example.com", "0722 000 111"));
        });
        var request = Request(phoneNumber: "0722000111", pin: "6942");
        Assert.Equal(HttpStatusCode.Accepted, (await Post("setup-pin/request", request)).Status);
        Assert.Equal(HttpStatusCode.OK, (await Post("setup-pin/complete", request with { Code = app.Email.Codes["new.person@example.com"] })).Status);

        await app.WithDb(async db =>
        {
            async Task<string> RoleOf(Guid userId) => await db.PersonRoles.IgnoreQueryFilters().Where(x => x.UserId == userId)
                .Join(db.Roles.IgnoreQueryFilters(), link => link.RoleId, role => role.Id, (_, role) => role.Name).SingleAsync();
            var user = await UserProvisioning.Provision(db, new("new.person@example.com", "0722000111"));
            Assert.Equal("Owner", await RoleOf(user.Id));
            await UserProvisioning.Provision(db, new("new.person@example.com", "0722000111", "Revenue clerk"));
            Assert.Equal("Revenue clerk", await RoleOf(user.Id));
            await Assert.ThrowsAsync<ArgumentException>(() => UserProvisioning.Provision(db, new("someone.else@example.com", "0722000111")));
        });
    }
    [Fact]
    public async Task DevelopmentCodeIsNullInTestingEnvironment()
    {
        // In Testing, DevelopmentMode is false by default (AuthFactory doesn't set it), so sign-in on an
        // untrusted device returns verification_required with no plaintext code.
        await app.Seed(trusted: false);
        var result = await Post("sign-in");
        Assert.Equal("verification_required", result.Body.Status);
        Assert.Null(result.Body.DevelopmentCode);
        // The code still arrives by email.
        Assert.Equal(1, app.Email.Count);
    }

    [Fact]
    public async Task TwoDifferentPhoneNumbersCanSignInConcurrently()
    {
        await app.SeedDemo();
        using var c1 = app.CreateClient();
        using var c2 = app.CreateClient();
        var r1 = await c1.PostAsJsonAsync("/auth/sign-in", new AuthRequest(PhoneNumber: "0733520614", Pin: "4826", DeviceId: "device-a"));
        var r2 = await c2.PostAsJsonAsync("/auth/sign-in", new AuthRequest(PhoneNumber: "0712345678", Pin: "2580", DeviceId: "device-b"));
        Assert.True(r1.StatusCode is HttpStatusCode.OK or HttpStatusCode.Accepted, $"Expected 200 or 202, got {r1.StatusCode}");
        Assert.True(r2.StatusCode is HttpStatusCode.OK or HttpStatusCode.Accepted, $"Expected 200 or 202, got {r2.StatusCode}");
    }

    [Fact]
    public async Task HourlyCodeIssuanceLimitPreventsExcessiveCodes()
    {
        await app.Seed();
        // Issue codes up to the hourly limit.
        for (var i = 0; i < AuthCodes.HourlyCodeLimit; i++)
        {
            app.Clock.Advance(TimeSpan.FromMinutes(2)); // past the 1-minute resend cooldown
            Assert.Equal(HttpStatusCode.Accepted, (await Post("pin-reset/request")).Status);
        }
        var countBefore = app.Email.Count;

        // The next request within the hour should be silently throttled (no new email).
        app.Clock.Advance(TimeSpan.FromMinutes(2));
        Assert.Equal(HttpStatusCode.Accepted, (await Post("pin-reset/request")).Status);
        Assert.Equal(countBefore, app.Email.Count);

        // After an hour elapses, codes can be issued again.
        app.Clock.Advance(TimeSpan.FromHours(1));
        Assert.Equal(HttpStatusCode.Accepted, (await Post("pin-reset/request")).Status);
        Assert.Equal(countBefore + 1, app.Email.Count);
    }

    [Fact]
    public async Task DailyCodeIssuanceLimitPreventsExcessiveCodes()
    {
        await app.Seed();
        // Issue codes up to the daily limit, spacing them past the hourly window.
        for (var i = 0; i < AuthCodes.DailyCodeLimit; i++)
        {
            app.Clock.Advance(TimeSpan.FromHours(2)); // past resend cooldown and spread across hours
            Assert.Equal(HttpStatusCode.Accepted, (await Post("pin-reset/request")).Status);
        }
        var countBefore = app.Email.Count;

        // The next request within 24 hours should be silently throttled.
        app.Clock.Advance(TimeSpan.FromHours(2));
        Assert.Equal(HttpStatusCode.Accepted, (await Post("pin-reset/request")).Status);
        Assert.Equal(countBefore, app.Email.Count);

        // After 24 hours elapse from the first code, codes can be issued again.
        app.Clock.Advance(TimeSpan.FromHours(24));
        Assert.Equal(HttpStatusCode.Accepted, (await Post("pin-reset/request")).Status);
        Assert.Equal(countBefore + 1, app.Email.Count);
    }

    [Fact]
    public async Task TrustedDeviceWrongPinsStillLockTheAccount()
    {
        await app.Seed();
        // Trusted device failures still cause lockout (preserving existing behavior).
        await Pause();
        await app.WithDb(async db =>
        {
            var user = await db.Users.SingleAsync();
            Assert.Equal(5, user.FailedAttempts);
            Assert.NotNull(user.PausedUntil);
        });
        Assert.Equal((HttpStatusCode)423, (await Post("sign-in")).Status);
    }

    [Fact]
    public async Task PinLongerThanMaximumIsRejectedBeforeHashing()
    {
        await app.Seed();
        // A PIN longer than 8 digits is rejected at the endpoint level with 400, not 401.
        var result = await Post("sign-in", Request(pin: "123456789"));
        Assert.Equal(HttpStatusCode.BadRequest, result.Status);
        Assert.Equal("invalid_request", result.Body.Status);
    }

    public void Dispose() { client.Dispose(); app.Dispose(); }
}
