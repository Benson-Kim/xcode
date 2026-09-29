using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application.Setup;
using Xunit;

namespace Auth.Tests;

// Contract C7 (addendum 1, section 2): keep the automatic reason, and ask for a typed one only where a person must say
// why, such as stopping a scheduled item. A reason that is typed is still checked and used.
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
        Assert.Equal(["Added scheduled expense Parking", "Changed the amount and vehicles of Parking", "Put money aside for the owner"],
            await Reasons(owner, "recurring"));

        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync($"/setup/recurring/{item}/stop", new { confirmed = true })).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync($"/setup/recurring/{item}/stop", new { confirmed = true, reason = "  " })).StatusCode);
        await Id(await owner.PostAsJsonAsync($"/setup/recurring/{item}/stop", new { confirmed = true, reason = "Parking moved into the SACCO fee" }));
    }

    [Fact]
    public async Task ATypedReasonIsStillCheckedAndUsed()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn("antony.maina@shamayah.co.ke");
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync("/setup/companies", new { name = "North Star", reason = new string('r', 501) })).StatusCode);
        await Id(await owner.PostAsJsonAsync("/setup/companies", new SaveCompany("North Star", "Signed with the SACCO")));
        Assert.Equal(["Signed with the SACCO"], await Reasons(owner, "companies"));
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
