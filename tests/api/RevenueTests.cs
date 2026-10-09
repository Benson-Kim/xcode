using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace Auth.Tests;

public sealed class RevenueTests : IDisposable
{
    private readonly AuthFactory app = new();
    private const string Owner = "antony.maina@shamayah.co.ke";

    [Fact]
    public async Task RevenueCaptureTakesDaysInAnyOrderAndKeepsCorrectionHistory()
    {
        await app.SeedDemo();
        var calendarDate = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);
        // A pinned Thursday keeps the join date and the business date in the same Monday-first week on any run day.
        var businessDate = RevenueTestData.PinnedThursday(app);

        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var organization = await db.Organizations.IgnoreQueryFilters().SingleAsync();
            Assert.True(organization.ChangeBusinessDate(businessDate, calendarDate));
            await db.SaveChangesAsync();
            db.Provisioning = false;
        });

        using var client = await app.SignIn(Owner);
        var companyResponse = await client.PostAsJsonAsync(
            "/setup/companies",
            new { name = "Revenue Test Fleet", reason = "Create revenue test company" });
        companyResponse.EnsureSuccessStatusCode();
        var company = await companyResponse.Content.ReadFromJsonAsync<IdResponse>();
        Assert.NotNull(company);

        var joined = businessDate.AddDays(-2);
        var vehicleResponse = await client.PostAsJsonAsync(
            "/setup/vehicles",
            new
            {
                companyId = company!.Id,
                registration = "KQA 321M",
                joinedOn = joined,
                weeklyTarget = 7000m,
                reason = "Create revenue test vehicle"
            });
        vehicleResponse.EnsureSuccessStatusCode();
        var vehicle = await vehicleResponse.Content.ReadFromJsonAsync<IdResponse>();
        Assert.NotNull(vehicle);

        // Today first, with both earlier days still missing.
        var today = await client.PutAsJsonAsync(
            $"/setup/revenue/{vehicle!.Id}/{businessDate:yyyy-MM-dd}",
            new { amount = 1200m, reason = (string?)null, note = (string?)null });
        Assert.Equal(HttpStatusCode.OK, today.StatusCode);

        var firstDay = await client.PutAsJsonAsync(
            $"/setup/revenue/{vehicle.Id}/{joined:yyyy-MM-dd}",
            new { amount = 1000m, reason = (string?)null, note = (string?)null });
        Assert.Equal(HttpStatusCode.OK, firstDay.StatusCode);

        var invalidOther = await client.PutAsJsonAsync(
            $"/setup/revenue/{vehicle.Id}/{joined.AddDays(1):yyyy-MM-dd}",
            new { amount = (decimal?)null, reason = "Other", note = (string?)null });
        Assert.Equal(HttpStatusCode.BadRequest, invalidOther.StatusCode);

        var reason = await client.PutAsJsonAsync(
            $"/setup/revenue/{vehicle.Id}/{joined.AddDays(1):yyyy-MM-dd}",
            new { amount = (decimal?)null, reason = "Garage", note = (string?)null });
        Assert.Equal(HttpStatusCode.OK, reason.StatusCode);

        var correction = await client.PutAsJsonAsync(
            $"/setup/revenue/{vehicle.Id}/{joined:yyyy-MM-dd}",
            new { amount = 1500m, reason = (string?)null, note = (string?)null, version = 1L });
        Assert.Equal(HttpStatusCode.OK, correction.StatusCode);

        var week = await client.GetFromJsonAsync<RevenueWeekResponse>("/setup/revenue");
        Assert.NotNull(week);
        var row = Assert.Single(week!.Vehicles);
        Assert.Equal(vehicle.Id, row.Id);
        Assert.Equal(2700m, row.TotalAmount);
        Assert.Equal(3000m, row.TotalExpected);
        Assert.Equal(90, row.Percent);
        Assert.Equal("amount", row.Days.Single(x => x.Date == joined).Status);
        Assert.Equal("reason", row.Days.Single(x => x.Date == joined.AddDays(1)).Status);
        Assert.True(row.Days.Single(x => x.Date == joined).EditedAfterCapture);

        var dashboard = await client.GetFromJsonAsync<RevenueDashboardResponse>("/setup/revenue/dashboard?period=month");
        Assert.NotNull(dashboard);
        Assert.Equal(2700m, dashboard!.Revenue);
        Assert.Equal(3000m, dashboard.Expected);
        // The Owner role has no dash.capture, so the capture card's counts are left out.
        Assert.Null(dashboard.CapturedToday);
        Assert.Equal(0, dashboard.MissingDays);
        Assert.Equal(1, dashboard.EditedRecords);

        var history = await client.GetFromJsonAsync<HistoryPage>("/setup/history?pageSize=100");
        var revenueHistory = history!.Items.Where(x => x.Section == "revenue").ToList();
        // Newest first; each names the vehicle and the day, so the change log says which record changed.
        string Day(DateOnly date) => date.ToString("d MMM yyyy", CultureInfo.InvariantCulture);
        Assert.Equal([
            $"Corrected revenue for KQA 321M on {Day(joined)}",
            $"Recorded no revenue for KQA 321M on {Day(joined.AddDays(1))}: Garage",
            $"Recorded revenue for KQA 321M on {Day(joined)}",
            $"Recorded revenue for KQA 321M on {Day(businessDate)}"], revenueHistory.Select(x => x.Reason));
        Assert.True(revenueHistory[0] is { Before: not null, After: not null });
    }

    [Fact]
    public async Task AHugeRecordAgainstATinyTargetShowsAtTheLargestPercentInsteadOfFailingTheWeekAndDashboard()
    {
        await app.SeedDemo();
        var businessDate = RevenueTestData.PinnedThursday(app);
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var organization = await db.Organizations.IgnoreQueryFilters().SingleAsync();
            Assert.True(organization.ChangeBusinessDate(businessDate, DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime)));
            await db.SaveChangesAsync();
            db.Provisioning = false;
        });
        using var client = await app.SignIn(Owner);
        var company = await (await client.PostAsJsonAsync("/setup/companies", new { name = "Overflow Fleet", reason = "Create company" })).Content.ReadFromJsonAsync<IdResponse>();
        var created = await client.PostAsJsonAsync("/setup/vehicles",
            new { companyId = company!.Id, registration = "KQA 999Z", joinedOn = businessDate, weeklyTarget = 1m, reason = "Create vehicle" });
        created.EnsureSuccessStatusCode();
        var vehicle = await created.Content.ReadFromJsonAsync<IdResponse>();
        var saved = await client.PutAsJsonAsync($"/setup/revenue/{vehicle!.Id}/{businessDate:yyyy-MM-dd}",
            new { amount = 10_000_000m, reason = (string?)null, note = (string?)null });
        Assert.Equal(HttpStatusCode.OK, saved.StatusCode);

        var week = await client.GetAsync("/setup/revenue");
        Assert.Equal(HttpStatusCode.OK, week.StatusCode);
        var row = Assert.Single((await week.Content.ReadFromJsonAsync<RevenueWeekResponse>())!.Vehicles);
        Assert.Equal(int.MaxValue, row.Percent);
        var dashboard = await client.GetAsync("/setup/revenue/dashboard?period=week");
        Assert.Equal(HttpStatusCode.OK, dashboard.StatusCode);
        Assert.Equal(int.MaxValue, (await dashboard.Content.ReadFromJsonAsync<RevenueDashboardResponse>())!.Percent);
    }

    private sealed record IdResponse(Guid Id);

    private sealed record RevenueWeekResponse(
        DateOnly WeekStart,
        DateOnly WeekThrough,
        DateOnly BusinessDate,
        IReadOnlyList<RevenueVehicleResponse> Vehicles,
        decimal TotalAmount,
        decimal TotalExpected,
        int? Percent);

    private sealed record RevenueVehicleResponse(
        Guid Id,
        IReadOnlyList<RevenueDayResponse> Days,
        decimal TotalAmount,
        decimal TotalExpected,
        int? Percent);

    private sealed record RevenueDayResponse(
        DateOnly Date,
        string Status,
        bool EditedAfterCapture);

    private sealed record RevenueDashboardResponse(
        decimal Revenue,
        decimal Expected,
        int? CapturedToday,
        int MissingDays,
        int EditedRecords,
        int? Percent = null);

    private sealed record HistoryPage(IReadOnlyList<HistoryResponse> Items);

    private sealed record HistoryResponse(
        string Section,
        string Reason,
        string? Before,
        string? After);

    public void Dispose() => app.Dispose();
}
