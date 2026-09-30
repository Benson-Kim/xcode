using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Xunit;
using static Auth.Tests.RevenueTestData;

namespace Auth.Tests;

// A refused revenue save says which permission it needs, so the phone and the web can tell the person.
public sealed class RevenueRefusalTests : IDisposable
{
    private readonly AuthFactory app = new();

    private async Task<(DateOnly Today, Guid Vehicle)> Arrange()
    {
        await app.SeedDemo();
        var today = PinnedThursday(app);
        await SetBusinessDate(app, today);
        var company = await Company(app, "Refusal Fleet");
        var vehicle = await Vehicle(app, company, "KAA 401A", today.AddDays(-5));
        await Records(app, vehicle, today.AddDays(-5), today.AddDays(-2));
        await ScopeToCompany(app, Clerk, company);
        return (today, vehicle);
    }

    [Fact]
    public async Task ChangingAPastDayWithoutCorrectSaysSo()
    {
        var (today, vehicle) = await Arrange();
        using var clerk = await app.SignIn(Clerk);

        // "Replace with mine" after a conflict: the version is the saved one, and the day has passed.
        var response = await Put(clerk, vehicle, today.AddDays(-2), new { amount = 1500m, reason = (string?)null, note = (string?)null, version = 1L });
        await AssertRefused(response, "Changing a past day needs the permission \"Correct revenue after the day\".");
    }

    [Fact]
    public async Task ANoEarningsReasonWithoutThatPermissionSaysSo()
    {
        var (today, vehicle) = await Arrange();
        await Deny(app, Clerk, "revenue.no_earnings");
        using var clerk = await app.SignIn(Clerk);

        var response = await Put(clerk, vehicle, today.AddDays(-1), new { amount = (decimal?)null, reason = "Garage", note = (string?)null, version = (long?)null });
        await AssertRefused(response, "Recording a no-earnings reason needs the permission \"Record a no earnings reason\".");
    }

    [Fact]
    public async Task ADayWithNoRecordYetWithoutCaptureSaysSo()
    {
        var (today, vehicle) = await Arrange();
        // The office admin keeps revenue.correct, and loses capture (with no_earnings and the capture card).
        await Deny(app, Admin, "revenue.capture");
        using var corrector = await app.SignIn(Admin);

        var response = await Put(corrector, vehicle, today.AddDays(-1), new { amount = 900m, reason = (string?)null, note = (string?)null, version = (long?)null });
        await AssertRefused(response, "Recording a day that has no record yet needs the permission \"Capture revenue\".");
    }

    private static Task<HttpResponseMessage> Put(HttpClient client, Guid vehicle, DateOnly date, object body) =>
        client.PutAsJsonAsync($"/setup/revenue/{vehicle}/{date:yyyy-MM-dd}", body);

    private static async Task AssertRefused(HttpResponseMessage response, string detail)
    {
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
        var problem = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(detail, problem.GetProperty("detail").GetString());
    }

    public void Dispose() => app.Dispose();
}
