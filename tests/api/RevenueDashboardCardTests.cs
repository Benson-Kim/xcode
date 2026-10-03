using System.Net.Http.Json;
using System.Text.Json;
using Xunit;
using static Auth.Tests.RevenueTestData;

namespace Auth.Tests;

// Each dashboard card has its own permission, and its figures reach only the people who hold it.
public sealed class RevenueDashboardCardTests : IDisposable
{
    private static readonly string[] Cards = ["dash.capture", "dash.revenue", "dash.gaps", "dash.edits"];

    private static readonly IReadOnlyDictionary<string, string[]> FiguresOf = new Dictionary<string, string[]>
    {
        ["dash.capture"] = ["capturedToday", "vehiclesToday"],
        ["dash.revenue"] = ["revenue", "expected", "percent"],
        ["dash.gaps"] = ["missingDays", "missingVehicles"],
        ["dash.edits"] = ["editedRecords"]
    };

    private readonly AuthFactory app = new();

    [Theory]
    [InlineData("dash.capture")]
    [InlineData("dash.revenue")]
    [InlineData("dash.gaps")]
    [InlineData("dash.edits")]
    public async Task EachCardsFiguresNeedThatCardsOwnPermission(string card)
    {
        await app.SeedDemo();
        var today = PinnedThursday(app);
        await SetBusinessDate(app, today);
        var company = await Company(app, "Dashboard Cards Fleet");
        var vehicle = await Vehicle(app, company, "KAA 301A", today.AddDays(-10));
        await Records(app, vehicle, today.AddDays(-10), today, skip: [today.AddDays(-2)]);
        // The office admin holds all four cards; each run keeps one of them.
        foreach (var other in Cards.Where(x => x != card))
            await Deny(app, Admin, other);
        using var admin = await app.SignIn(Admin);

        foreach (var period in new[] { "today", "week", "month" })
        {
            var dashboard = await admin.GetFromJsonAsync<JsonElement>($"/setup/revenue/dashboard?period={period}");
            foreach (var (owner, figures) in FiguresOf)
                foreach (var figure in figures)
                    Assert.True((dashboard.GetProperty(figure).ValueKind == JsonValueKind.Null) != (owner == card),
                        $"{figure} ({owner}) with only {card}, {period}: {dashboard.GetProperty(figure)}");
        }
    }

    [Fact]
    public async Task TheRevenueClerksCaptureCardDoesNotRevealRevenueTotals()
    {
        await app.SeedDemo();
        var today = PinnedThursday(app);
        await SetBusinessDate(app, today);
        var company = await Company(app, "Clerk Cards Fleet");
        var vehicle = await Vehicle(app, company, "KAA 302A", today.AddDays(-10));
        await Records(app, vehicle, today.AddDays(-10), today.AddDays(-2));
        await ScopeToCompany(app, Clerk, company);
        using var clerk = await app.SignIn(Clerk);

        // The default Revenue clerk has dash.capture and dash.gaps, not dash.revenue or dash.edits.
        var dashboard = await clerk.GetFromJsonAsync<JsonElement>("/setup/revenue/dashboard?period=week");
        Assert.Equal(0, dashboard.GetProperty("capturedToday").GetInt32());
        Assert.Equal(1, dashboard.GetProperty("vehiclesToday").GetInt32());
        Assert.Equal(1, dashboard.GetProperty("missingDays").GetInt32());
        Assert.Equal(1, dashboard.GetProperty("missingVehicles").GetInt32());
        foreach (var hidden in new[] { "revenue", "expected", "percent", "editedRecords" })
            Assert.Equal(JsonValueKind.Null, dashboard.GetProperty(hidden).ValueKind);
    }

    public void Dispose() => app.Dispose();
}
