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

public sealed class AuthTests : IDisposable
{
    private readonly AuthFactory app = new();
    private readonly HttpClient client;
    private const string Address = "person@example.com";
    public AuthTests() => client = app.CreateClient();
    private AuthRequest Request(string phoneNumber = "+254712345678", string pin = "5826", string device = "phone", string code = "", string refresh = "") => new(PhoneNumber: phoneNumber, Pin: pin, DeviceId: device, Code: code, RefreshToken: refresh);
    private async Task<(HttpStatusCode Status, AuthResponse Body)> Post(string path, AuthRequest? request = null)
    {
        var response = await client.PostAsJsonAsync("/auth/" + path, request ?? Request());
        var body = await response.Content.ReadFromJsonAsync<AuthResponse>();
        Assert.NotNull(body);
        return (response.StatusCode, body);
    }
    private async Task Pause(string path = "sign-in")
    {
        for (var i = 0; i < 5; i++) Assert.Equal(HttpStatusCode.Unauthorized, (await Post(path, Request(pin: "9998"))).Status);
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
    public void Dispose() { client.Dispose(); app.Dispose(); }
}
