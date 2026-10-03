using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application;
using Auth.Application.Setup;
using Xunit;

namespace Auth.Tests;

// Contract C7 (addendum 1, section 2): keep the automatic reason, and ask for a typed one only where a person must say
// why, such as stopping a scheduled item. A reason that is typed is still checked, and follows the automatic one.
public sealed class AutomaticReasonTests : IDisposable
{
    private readonly AuthFactory app = new();

    [Fact]
    public async Task CompanyChangesWithoutAReasonGetAnAutomaticOne()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn("antony.maina@shamayah.co.ke");
        var company = await Id(await owner.PostAsJsonAsync("/setup/companies", new { name = "North Star" }));
        await Id(await owner.PutAsJsonAsync($"/setup/companies/{company}", new { name = "North Line", reason = " " }));
        await Id(await owner.PostAsJsonAsync($"/setup/companies/{company}/archive", new { }));
        await Id(await owner.PostAsJsonAsync($"/setup/companies/{company}/restore", new { reason = (string?)null }));

        Assert.Equal(["Added company North Star", "Renamed company North Star to North Line", "Archived company North Line", "Restored company North Line"],
            await Reasons(owner, "companies"));
    }

    [Fact]
    public async Task VehicleChangesWithoutAReasonSayWhatChanged()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn("antony.maina@shamayah.co.ke");
        var today = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);
        var north = await Id(await owner.PostAsJsonAsync("/setup/companies", new { name = "North Star" }));
        var south = await Id(await owner.PostAsJsonAsync("/setup/companies", new { name = "South Line" }));
        var vehicle = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new { companyId = north, registration = "KDA 482M", joinedOn = "2026-01-01", weeklyTarget = 15000m }));
        await Id(await owner.PutAsJsonAsync($"/setup/vehicles/{vehicle}", new { companyId = north, registration = "KDA 482M", joinedOn = "2026-01-01", weeklyTarget = 5000m }));
        await Id(await owner.PutAsJsonAsync($"/setup/vehicles/{vehicle}", new { companyId = south, registration = "KDA 482M", joinedOn = "2026-01-05", weeklyTarget = 5000m }));
        await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/retire", new { leftOn = today.ToString("yyyy-MM-dd") }));
        await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/restore", new { }));

        var date = today.ToString("yyyy-MM-dd");
        Assert.Equal([
            "Added vehicle KDA 482M to North Star with a weekly target of KES 15,000 from 2026-01-01",
            $"Changed the weekly target of KDA 482M to KES 5,000 from {date}",
            "Moved KDA 482M to South Line; changed when KDA 482M joined the fleet to 2026-01-05",
            $"Vehicle KDA 482M left the fleet on {date}",
            "Vehicle KDA 482M returned to the fleet"], await Reasons(owner, "vehicles"));
    }

    [Fact]
    public async Task ScheduledItemsSayWhatChangedButStoppingStillNeedsATypedReason()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn("antony.maina@shamayah.co.ke");
        var today = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);
        var company = await Id(await owner.PostAsJsonAsync("/setup/companies", new { name = "North Star" }));
        var first = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new { companyId = company, registration = "KDA 482M", joinedOn = "2026-01-01", weeklyTarget = 15000m }));
        var second = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new { companyId = company, registration = "KDB 111A", joinedOn = "2026-01-01", weeklyTarget = 15000m }));
        var parking = await ExpenseItemTestData.Id(owner, "Parking");
        object Parking(decimal amount, params object[] allocations) => new
        {
            kind = 1, amount, frequency = 2, day = 1, lastDay = false, start = today.ToString("yyyy-MM-dd"), allocations, expenseItemId = parking
        };

        var item = await Id(await owner.PostAsJsonAsync("/setup/recurring", Parking(700m, new { vehicleId = first, amount = 700m })));
        await Id(await owner.PutAsJsonAsync($"/setup/recurring/{item}", Parking(1400m, new { vehicleId = first, amount = 700m }, new { vehicleId = second, amount = 700m })));
        await Id(await owner.PostAsJsonAsync("/setup/recurring", new
        {
            name = "Owner savings", kind = 2, amount = 500m, frequency = 3, day = 1, lastDay = false, start = today.ToString("yyyy-MM-dd"),
            allocations = new[] { new { vehicleId = first, amount = 500m } }, reason = "Put money aside for the owner"
        }));
        Assert.Equal(["Added scheduled expense Parking", "Changed the amount and vehicles of Parking", "Added scheduled saving Owner savings. Reason: Put money aside for the owner."],
            await Reasons(owner, "recurring"));

        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync($"/setup/recurring/{item}/stop", new { confirmed = true })).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync($"/setup/recurring/{item}/stop", new { confirmed = true, reason = "  " })).StatusCode);
        await Id(await owner.PostAsJsonAsync($"/setup/recurring/{item}/stop", new { confirmed = true, reason = "Parking moved into the SACCO fee" }));
        // The typed reason follows the automatic one; it does not replace it.
        Assert.Equal($"Stopped Parking from {today:yyyy-MM-dd}. Reason: Parking moved into the SACCO fee.", (await Reasons(owner, "recurring"))[^1]);

        // Stopped on another business date: stopping again is refused rather than reported as done.
        app.Clock.Advance(TimeSpan.FromDays(-3));
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync($"/setup/recurring/{item}/stop", new { confirmed = true, reason = "Again" })).StatusCode);
    }

    [Fact]
    public async Task ATypedReasonIsStillCheckedAndUsed()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn("antony.maina@shamayah.co.ke");
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync("/setup/companies", new { name = "North Star", reason = new string('r', 501) })).StatusCode);
        await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North Star", "Signed with the SACCO")));
        Assert.Equal(["Added company North Star. Reason: Signed with the SACCO."], await Reasons(owner, "companies"));
    }

    // Build notes: "Keep the automatic reason. Ask for a typed reason in four places." The typed reason is added after
    // the automatic one, so the change log still says who or what changed.
    [Fact]
    public async Task ATypedReasonFollowsTheAutomaticOne()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn("antony.maina@shamayah.co.ke");
        var roles = (await owner.GetFromJsonAsync<List<AccessRole>>("/setup/access/roles"))!;
        var grace = await Id(await owner.PostAsJsonAsync("/setup/people", new SavePerson("Grace", "Achieng", "grace.achieng@example.com", "0711000002",
            "Revenue clerk", "all", [], [], roles.Single(x => x.Name == "Revenue clerk").Permissions.ToList(), null)));
        var version = (await owner.GetFromJsonAsync<PersonDto>($"/setup/people/{grace}"))!.Version;
        await Id(await owner.PostAsJsonAsync($"/setup/people/{grace}/deactivate", new { version, reason = "Moved to another SACCO" }));
        Assert.Equal("Removed access for Grace Achieng. Reason: Moved to another SACCO.", (await Reasons(owner, "people"))[^1]);

        var today = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);
        var company = await Id(await owner.PostAsJsonAsync("/setup/companies", new { name = "North Star" }));
        var vehicle = await Id(await owner.PostAsJsonAsync("/setup/vehicles", new { companyId = company, registration = "KDA 482M", joinedOn = "2026-01-01", weeklyTarget = 15000m }));
        await Id(await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/retire", new { leftOn = today.ToString("yyyy-MM-dd"), reason = "Sold to the SACCO." }));
        Assert.Equal($"Vehicle KDA 482M left the fleet on {today:yyyy-MM-dd}. Reason: Sold to the SACCO.", (await Reasons(owner, "vehicles"))[^1]);
    }

    [Fact]
    public void ATypedReasonIsKeptWholeWithinTheChangeLogsLimit()
    {
        Assert.Equal("Removed access for Grace Achieng", SetupPagination.Automatic("Removed access for Grace Achieng", null));
        Assert.Equal("Removed access for Grace Achieng. Reason: Moved to another SACCO.", SetupPagination.Automatic("Removed access for Grace Achieng", "Moved to another SACCO"));
        Assert.Equal("Removed the logo. Reason: Is it withdrawn?", SetupPagination.Automatic("Removed the logo", "Is it withdrawn?"));

        // Together they fit the change log's 500 characters: the automatic part is shortened first.
        var typed = new string('t', 300);
        var combined = SetupPagination.Automatic(new string('a', 400), typed);
        Assert.Equal(500, combined.Length);
        Assert.EndsWith($"... Reason: {typed}.", combined);
        Assert.Equal(500, SetupPagination.Automatic(new string('a', 400), new string('t', 500)).Length);
    }

    // Oldest first, as the changes were made.
    private static async Task<List<string>> Reasons(HttpClient client, string section) =>
        [.. (await client.GetFromJsonAsync<Page<HistoryEntry>>("/setup/history?pageSize=100"))!.Items
            .Where(x => x.Section == section).OrderBy(x => x.Version).Select(x => x.Reason)];

    private static async Task<Guid> Id(HttpResponseMessage response)
    {
        using (response)
        {
            Assert.True(response.IsSuccessStatusCode, await response.Content.ReadAsStringAsync());
            return (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetGuid();
        }
    }

    public void Dispose() => app.Dispose();
}
