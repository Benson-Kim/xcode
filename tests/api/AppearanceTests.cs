using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Xunit;

namespace Auth.Tests;

public sealed class AppearanceTests : IDisposable
{
    private readonly AuthFactory app = new();
    private const string Owner = "antony.maina@shamayah.co.ke";
    private const string RevenueClerk = "wanjiru.kamau@zurigenesis.co.ke";
    // A valid 1x1 PNG.
    private const string Png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";

    private static object Branding(string displayName, string primary) => new
    {
        value = new { displayName, legalName = "North Star Fleet Ltd", logoAlt = displayName, primary, secondary = "#14213D", accent = "#1E6B3A" },
        reason = "Update brand",
    };

    [Fact]
    public async Task EveryMemberSeesTheOrganizationsSavedBrandingAndFormats()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        (await owner.PutAsJsonAsync("/setup/organization/settings/branding", Branding("North Star", "#1647A6"))).EnsureSuccessStatusCode();

        using var clerk = await app.SignIn(RevenueClerk);
        var appearance = await clerk.GetFromJsonAsync<JsonElement>("/setup/appearance");
        Assert.Equal("Demo Fleet", appearance.GetProperty("organizationName").GetString());
        Assert.Equal("North Star", appearance.GetProperty("branding").GetProperty("displayName").GetString());
        Assert.Equal("#1647A6", appearance.GetProperty("branding").GetProperty("primary").GetString());
        Assert.Equal(JsonValueKind.Null, appearance.GetProperty("branding").GetProperty("logo").ValueKind);
        Assert.Equal("KES", appearance.GetProperty("formats").GetProperty("currency").GetString());
        Assert.False(appearance.GetProperty("reducedMotion").GetBoolean());
    }

    // The phone enforces the organization's wrong-PIN policy offline, so every member can read it.
    [Fact]
    public async Task EveryMemberSeesTheWrongPinPolicy()
    {
        await app.SeedDemo();
        using var clerk = await app.SignIn(RevenueClerk);
        var defaults = await clerk.GetFromJsonAsync<JsonElement>("/setup/appearance");
        Assert.Equal((5, 15), (defaults.GetProperty("lockoutThreshold").GetInt32(), defaults.GetProperty("lockoutMinutes").GetInt32()));

        using var owner = await app.SignIn(Owner);
        (await owner.PutAsJsonAsync("/setup/organization/settings/securityPolicy", new { value = new { lockoutThreshold = 3, lockoutMinutes = 60 } })).EnsureSuccessStatusCode();
        var changed = await clerk.GetFromJsonAsync<JsonElement>("/setup/appearance");
        Assert.Equal((3, 60), (changed.GetProperty("lockoutThreshold").GetInt32(), changed.GetProperty("lockoutMinutes").GetInt32()));
    }

    [Fact]
    public async Task LogoUploadsAreCheckedRecordedAndShownToMembers()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);

        using var uploaded = await owner.PutAsJsonAsync("/setup/organization/logo", new { dataUrl = Png });
        Assert.Equal(HttpStatusCode.OK, uploaded.StatusCode);
        using var clerk = await app.SignIn(RevenueClerk);
        var appearance = await clerk.GetFromJsonAsync<JsonElement>("/setup/appearance");
        Assert.Equal(Png, appearance.GetProperty("branding").GetProperty("logo").GetString());

        var disguised = "data:image/png;base64," + Convert.ToBase64String("<script>alert(1)</script>"u8.ToArray());
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PutAsJsonAsync("/setup/organization/logo", new { dataUrl = disguised })).StatusCode);
        var svg = "data:image/svg+xml;base64," + Convert.ToBase64String("<svg xmlns='http://www.w3.org/2000/svg'/>"u8.ToArray());
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PutAsJsonAsync("/setup/organization/logo", new { dataUrl = svg })).StatusCode);
        var oversized = new byte[300 * 1024];
        Convert.FromBase64String(Png["data:image/png;base64,".Length..]).CopyTo(oversized, 0);
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PutAsJsonAsync("/setup/organization/logo", new { dataUrl = "data:image/png;base64," + Convert.ToBase64String(oversized) })).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await clerk.PutAsJsonAsync("/setup/organization/logo", new { dataUrl = Png })).StatusCode);

        (await owner.DeleteAsync("/setup/organization/logo")).EnsureSuccessStatusCode();
        appearance = await clerk.GetFromJsonAsync<JsonElement>("/setup/appearance");
        Assert.Equal(JsonValueKind.Null, appearance.GetProperty("branding").GetProperty("logo").ValueKind);

        // Contract C7: no typed reason is asked for, but one that is given is checked and kept.
        (await owner.PutAsJsonAsync("/setup/organization/logo", new { dataUrl = Png, reason = "New brand for 2027" })).EnsureSuccessStatusCode();
        (await owner.DeleteAsync("/setup/organization/logo?reason=Brand%20withdrawn")).EnsureSuccessStatusCode();
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PutAsJsonAsync("/setup/organization/logo", new { dataUrl = Png, reason = new string('r', 501) })).StatusCode);

        var history = await owner.GetFromJsonAsync<JsonElement>("/setup/history");
        var reasons = history.GetProperty("items").EnumerateArray().Select(entry => entry.GetProperty("reason").GetString()).Reverse().ToList();
        Assert.Equal(["Uploaded a new logo", "Removed the logo", "Uploaded a new logo. Reason: New brand for 2027.", "Removed the logo. Reason: Brand withdrawn."], reasons.Skip(reasons.Count - 4));
    }

    public void Dispose() => app.Dispose();
}
