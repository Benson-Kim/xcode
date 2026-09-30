using System.Net;
using System.Net.Http.Json;
using Auth.Application;
using Auth.Application.Setup;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace Auth.Tests;

// Who may act on whom: Owners are protected from lower roles, and a person's sign-in details can only be
// rewritten by someone who could have granted them everything they hold.
public sealed class AccessLifecycleTests : IDisposable
{
    private readonly AuthFactory app = new();
    private const string Owner = "antony.maina@shamayah.co.ke";
    private const string OfficeAdmin = "peter.otieno@zurigenesis.co.ke";
    private const string RevenueClerk = "wanjiru.kamau@zurigenesis.co.ke";

    private static SavePerson Edit(PersonDto person, string? email = null, string? phoneNumber = null) =>
        new(person.FirstName, person.LastName, email ?? person.Email, phoneNumber ?? person.PhoneNumber, person.Role,
            "all", [], [], person.Permissions.ToList(), person.ApprovalLimit, person.Version);

    private static async Task<PersonDto> Find(HttpClient client, string email) =>
        (await client.GetFromJsonAsync<Page<PersonDto>>("/setup/people"))!.Items.Single(x => x.Email == email);

    private static async Task<Guid> Create(HttpClient owner, string email, string phoneNumber, IEnumerable<string> extra, decimal? approvalLimit = null)
    {
        var defaults = (await owner.GetFromJsonAsync<List<AccessRole>>("/setup/access/roles"))!.Single(x => x.Name == "Revenue clerk").Permissions;
        using var created = await owner.PostAsJsonAsync("/setup/people", new SavePerson("Jane", "Njeri", email, phoneNumber, "Revenue clerk", "all", [], [],
            defaults.Concat(extra).ToList(), approvalLimit));
        created.EnsureSuccessStatusCode();
        return (await created.Content.ReadFromJsonAsync<IdResponse>())!.Id;
    }

    private sealed record IdResponse(Guid Id);

    [Fact]
    public async Task OnlyOwnersCanDeactivateOrSignOutAnOwner()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        using var admin = await app.SignIn(OfficeAdmin);
        var ownerId = (await Find(admin, Owner)).Id;

        Assert.Equal(HttpStatusCode.Forbidden, (await admin.PostAsJsonAsync($"/setup/people/{ownerId}/deactivate", new { version = 1, reason = "Attempted removal" })).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await admin.PostAsync($"/setup/people/{ownerId}/sign-out", null)).StatusCode);

        // The Owner keeps access and their session; people managers still manage everyone else.
        Assert.True((await Find(owner, Owner)).Active);
        var clerk = await Find(admin, RevenueClerk);
        Assert.Equal(HttpStatusCode.OK, (await admin.PostAsync($"/setup/people/{clerk.Id}/sign-out", null)).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await admin.PostAsJsonAsync($"/setup/people/{clerk.Id}/deactivate", new { version = clerk.Version, reason = "No longer works here" })).StatusCode);
    }

    [Fact]
    public async Task StaleAccessFormsCannotOverwriteNewerChanges()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var id = await Create(owner, "jane.stale@example.com", "0711000006", []);
        var original = await Find(owner, "jane.stale@example.com");

        Assert.Equal(HttpStatusCode.OK,
            (await owner.PutAsJsonAsync($"/setup/people/{id}", Edit(original) with { FirstName = "First" })).StatusCode);
        Assert.Equal(HttpStatusCode.Conflict,
            (await owner.PutAsJsonAsync($"/setup/people/{id}", Edit(original) with { LastName = "Stale" })).StatusCode);

        var current = await Find(owner, "jane.stale@example.com");
        Assert.Equal(HttpStatusCode.Conflict,
            (await owner.PostAsJsonAsync($"/setup/people/{id}/deactivate",
                new { version = original.Version, reason = "Stale removal" })).StatusCode);
        Assert.True(current.Active);
    }

    // Phase 1's web posted activate and deactivate with no body and no content type. A tab still open from then must
    // get a problem it can show (reload), not a bare 400 or 415.
    [Fact]
    public async Task BodylessLifecycleCallsFromOlderClientsGetAReloadProblem()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var id = await Create(owner, "jane.bodyless@example.com", "0711000007", []);
        async Task AssertReloadProblem(string action, HttpContent? content)
        {
            using var response = await owner.PostAsync($"/setup/people/{id}/{action}", content);
            Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
            Assert.Equal("application/problem+json", response.Content.Headers.ContentType?.MediaType);
            var problem = await response.Content.ReadFromJsonAsync<Microsoft.AspNetCore.Mvc.ProblemDetails>();
            Assert.Contains("Reload before saving", problem!.Title);
        }

        await AssertReloadProblem("deactivate", null);
        await AssertReloadProblem("deactivate", new ByteArrayContent([]));
        Assert.True((await Find(owner, "jane.bodyless@example.com")).Active);

        var person = await Find(owner, "jane.bodyless@example.com");
        (await owner.PostAsJsonAsync($"/setup/people/{id}/deactivate", new { version = person.Version, reason = "Left the organization" })).EnsureSuccessStatusCode();
        await AssertReloadProblem("activate", null);
        await AssertReloadProblem("activate", new ByteArrayContent([]));
        Assert.False((await Find(owner, "jane.bodyless@example.com")).Active);
    }

    [Fact]
    public async Task SignInDetailsOfSomeoneHoldingMoreThanTheEditorCanGrantNeedAnOwner()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        await Create(owner, "jane.one@example.com", "0711000001", ["organization.manage"]);
        await Create(owner, "jane.two@example.com", "0711000002", [], approvalLimit: 5000m);

        using var admin = await app.SignIn(OfficeAdmin);
        var elevated = await Find(admin, "jane.one@example.com");
        var approver = await Find(admin, "jane.two@example.com");
        Assert.Equal(HttpStatusCode.Forbidden, (await admin.PutAsJsonAsync($"/setup/people/{elevated.Id}", Edit(elevated, email: "peter.alias@example.com"))).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await admin.PutAsJsonAsync($"/setup/people/{approver.Id}", Edit(approver, phoneNumber: "0799000111"))).StatusCode);

        // Other edits to the same person are still a people manager's job.
        Assert.Equal(HttpStatusCode.OK, (await admin.PutAsJsonAsync($"/setup/people/{elevated.Id}", Edit(elevated) with { FirstName = "Janet" })).StatusCode);
        // The rename moved the person's version on, so the Owner edits from a fresh read.
        var renamed = await Find(owner, "jane.one@example.com");
        Assert.Equal(HttpStatusCode.OK, (await owner.PutAsJsonAsync($"/setup/people/{elevated.Id}", Edit(renamed, email: "jane.new@example.com"))).StatusCode);
        Assert.Equal("jane.new@example.com", (await Find(owner, "jane.new@example.com")).Email);
    }

    [Fact]
    public async Task ChangingSignInDetailsEndsSessionsButKeepsThePin()
    {
        await app.SeedDemo();
        using var clerk = await app.SignIn(RevenueClerk);
        Assert.Equal(HttpStatusCode.OK, (await clerk.GetAsync("/setup/access/catalog")).StatusCode);

        // An Office admin does not capture revenue (Web v2.8), so they cannot take over a clerk's sign-in: only an Owner can.
        using var admin = await app.SignIn(OfficeAdmin);
        var person = await Find(admin, RevenueClerk);
        Assert.Equal(HttpStatusCode.Forbidden, (await admin.PutAsJsonAsync($"/setup/people/{person.Id}", Edit(person, phoneNumber: "0799000111"))).StatusCode);
        using var owner = await app.SignIn(Owner);
        Assert.Equal(HttpStatusCode.OK, (await owner.PutAsJsonAsync($"/setup/people/{person.Id}", Edit(person, phoneNumber: "0799000111"))).StatusCode);

        Assert.Equal(HttpStatusCode.Unauthorized, (await clerk.GetAsync("/setup/access/catalog")).StatusCode);

        // The new number and the existing PIN sign in, after a device code sent to the email on file
        // (past the one-minute resend cooldown left by the earlier sign-in).
        app.Clock.Advance(TimeSpan.FromMinutes(1));
        using var fresh = app.CreateClient();
        var device = "test-" + Guid.NewGuid();
        using var signIn = await fresh.PostAsJsonAsync("/auth/sign-in", new AuthRequest(PhoneNumber: "0799000111", Pin: "2580", DeviceId: device));
        Assert.Equal(HttpStatusCode.Accepted, signIn.StatusCode);
        using var verify = await fresh.PostAsJsonAsync("/auth/verify-device", new AuthRequest(PhoneNumber: "0799000111", DeviceId: device, Code: app.Email.Codes[RevenueClerk]));
        Assert.Equal(HttpStatusCode.OK, verify.StatusCode);

        await app.WithDb(async db =>
        {
            var audit = await db.AuditEvents.IgnoreQueryFilters().SingleAsync(x => x.Action == "person.sign_in_details_changed");
            Assert.Contains("254712345678", audit.Before);
            Assert.Contains("254799000111", audit.After);
        });
    }

    [Fact]
    public async Task ChangingSomeonesAccessRenewsTheirTokenWithoutSigningThemOut()
    {
        await app.SeedDemo();
        // The clerk signs in on a new device, keeping both tokens.
        using var browser = app.CreateClient();
        var device = "test-" + Guid.NewGuid();
        (await browser.PostAsJsonAsync("/auth/sign-in", new AuthRequest(PhoneNumber: "0712345678", Pin: "2580", DeviceId: device))).EnsureSuccessStatusCode();
        using var verify = await browser.PostAsJsonAsync("/auth/verify-device", new AuthRequest(PhoneNumber: "0712345678", DeviceId: device, Code: app.Email.Codes[RevenueClerk]));
        var tokens = (await verify.Content.ReadFromJsonAsync<AuthResponse>())!;
        async Task<HttpResponseMessage> Session(string accessToken)
        {
            using var request = new HttpRequestMessage(HttpMethod.Get, "/auth/session");
            request.Headers.Authorization = new("Bearer", accessToken);
            return await browser.SendAsync(request);
        }

        using var owner = await app.SignIn(Owner);
        var clerk = await Find(owner, RevenueClerk);
        // A save that changes nothing their token carries (here only their data scope) leaves the token alone.
        (await owner.PutAsJsonAsync($"/setup/people/{clerk.Id}", Edit(clerk))).EnsureSuccessStatusCode();
        Assert.Equal(HttpStatusCode.OK, (await Session(tokens.AccessToken!)).StatusCode);

        // That save moved the person's version on, so the next edit starts from a fresh read.
        clerk = await Find(owner, RevenueClerk);
        (await owner.PutAsJsonAsync($"/setup/people/{clerk.Id}", Edit(clerk) with { Permissions = [.. clerk.Permissions, "reports.view"] })).EnsureSuccessStatusCode();
        Assert.Equal(HttpStatusCode.Unauthorized, (await Session(tokens.AccessToken!)).StatusCode);

        // Their refresh token still works and brings the new permissions.
        using var refreshed = await browser.PostAsJsonAsync("/auth/refresh", new AuthRequest(DeviceId: device, RefreshToken: tokens.RefreshToken!));
        Assert.Equal(HttpStatusCode.OK, refreshed.StatusCode);
        var renewed = (await refreshed.Content.ReadFromJsonAsync<AuthResponse>())!;
        var session = await (await Session(renewed.AccessToken!)).Content.ReadFromJsonAsync<AuthSessionResponse>();
        Assert.Contains("reports.view", session!.Permissions);
    }

    public void Dispose() => app.Dispose();
}
