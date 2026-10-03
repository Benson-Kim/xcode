using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Xunit;
using static Auth.Tests.RevenueTestData;

namespace Auth.Tests;

// The business date T is a pinned Thursday, so the Monday-first week runs from T-3 to T+3.
public sealed class RevenueCaptureTests : IDisposable
{
    private readonly AuthFactory app = new();

    private async Task<(DateOnly Today, Guid Company)> Arrange()
    {
        await app.SeedDemo();
        var today = PinnedThursday(app);
        await SetBusinessDate(app, today);
        return (today, await Company(app, "Revenue Rules Fleet"));
    }

    [Fact]
    public async Task EarliestMissingComesFromTheWholeHistoryAndLaterMissingDaysCannotBeOpened()
    {
        var (today, company) = await Arrange();
        var joined = today.AddDays(-20);
        var monday = today.AddDays(-3);
        var complete = await Vehicle(app, company, "KAA 101A", joined);
        await Records(app, complete, joined, today.AddDays(-1));
        var behind = await Vehicle(app, company, "KAA 102A", joined);
        await Records(app, behind, joined, monday.AddDays(-3));
        var holed = await Vehicle(app, company, "KAA 103A", joined);
        await Records(app, holed, joined, today.AddDays(-1), skip: [joined.AddDays(5)]);
        var midweek = await Vehicle(app, company, "KAA 104A", today.AddDays(-1));
        var left = await Vehicle(app, company, "KAA 105A", joined, leftOn: today.AddDays(-1));
        await Records(app, left, joined, today.AddDays(-2));

        using var owner = await app.SignIn(Owner);
        var week = await GetWeek(owner, $"?companyId={company}");
        Row Of(Guid id) => week.Vehicles.Single(x => x.Id == id);

        Assert.Null(Of(complete).EarliestMissing);
        Assert.True(Of(complete).On(today).CanEdit);
        Assert.Equal(1L, Of(complete).On(monday).Version);
        Assert.Null(Of(complete).On(today).Version);

        Assert.Equal(monday.AddDays(-2), Of(behind).EarliestMissing);
        Assert.All(Of(behind).Days.Where(x => x.Date <= today), x => Assert.False(x.CanEdit));

        Assert.Equal(joined.AddDays(5), Of(holed).EarliestMissing);
        Assert.False(Of(holed).On(today).CanEdit);

        Assert.Equal(today.AddDays(-1), Of(midweek).EarliestMissing);
        Assert.Equal("none", Of(midweek).On(monday).Status);
        Assert.Equal(0m, Of(midweek).On(monday).Expected);
        Assert.True(Of(midweek).On(today.AddDays(-1)).CanEdit);
        Assert.False(Of(midweek).On(today).CanEdit);
        Assert.Equal(1000m, Of(midweek).TotalExpected);

        Assert.Null(Of(left).EarliestMissing);
        Assert.Equal("none", Of(left).On(today.AddDays(-1)).Status);
    }

    [Fact]
    public async Task TheGridListsOnlyVehiclesActiveThatWeekButTheDetailShowsAnyVehicleInScope()
    {
        var (today, company) = await Arrange();
        var monday = today.AddDays(-3);
        var active = await Vehicle(app, company, "KAA 111A", today.AddDays(-30));
        var gone = await Vehicle(app, company, "KAA 112A", today.AddDays(-30), leftOn: monday);
        var newcomer = await Vehicle(app, company, "KAA 113A", monday);

        using var owner = await app.SignIn(Owner);
        var week = await GetWeek(owner, $"?companyId={company}");
        Assert.Equal([active, newcomer], week.Vehicles.Select(x => x.Id).ToArray());

        var lastWeek = await GetWeek(owner, $"?companyId={company}&weekStart={monday.AddDays(-7):yyyy-MM-dd}");
        Assert.Equal([active, gone], lastWeek.Vehicles.Select(x => x.Id).ToArray());

        var detail = await GetWeek(owner, $"?vehicleId={gone}");
        var row = Assert.Single(detail.Vehicles);
        Assert.Equal(gone, row.Id);
        Assert.All(row.Days, x => Assert.Equal("none", x.Status));
    }

    [Fact]
    public async Task SavingPastAGapIsRefusedWithTheEarliestMissingDay()
    {
        var (today, company) = await Arrange();
        var monday = today.AddDays(-3);
        var vehicle = await Vehicle(app, company, "KAA 121A", today.AddDays(-20));
        await Records(app, vehicle, today.AddDays(-20), monday.AddDays(-3));

        using var owner = await app.SignIn(Owner);
        var skipped = await Put(owner, vehicle, today, amount: 1000m);
        Assert.Equal(HttpStatusCode.BadRequest, skipped.StatusCode);
        var problem = await Body(skipped);
        Assert.Equal("Invalid setup change", problem.GetProperty("title").GetString());
        Assert.False(string.IsNullOrWhiteSpace(problem.GetProperty("detail").GetString()));
        Assert.Equal($"{monday.AddDays(-2):yyyy-MM-dd}", problem.GetProperty("earliestMissing").GetString());

        Assert.Equal(HttpStatusCode.OK, (await Put(owner, vehicle, monday.AddDays(-2), amount: 1000m)).StatusCode);
        var row = Assert.Single((await GetWeek(owner, $"?vehicleId={vehicle}")).Vehicles);
        Assert.Equal(monday.AddDays(-1), row.EarliestMissing);
    }

    [Fact]
    public async Task ChangingARecordNeedsItsCurrentVersionAndAnIdenticalReplayIsIdempotent()
    {
        var (today, company) = await Arrange();
        var vehicle = await Vehicle(app, company, "KAA 131A", today.AddDays(-10));
        await Records(app, vehicle, today.AddDays(-10), today.AddDays(-1));
        using var owner = await app.SignIn(Owner);

        var first = await Put(owner, vehicle, today, amount: 1500m);
        Assert.Equal(HttpStatusCode.OK, first.StatusCode);
        var saved = await Body(first);
        Assert.Equal(["id", "version"], saved.EnumerateObject().Select(x => x.Name).ToArray());
        var id = saved.GetProperty("id").GetGuid();
        Assert.Equal(1, saved.GetProperty("version").GetInt64());

        var replay = await Body(await Put(owner, vehicle, today, amount: 1500m));
        Assert.Equal(id, replay.GetProperty("id").GetGuid());
        Assert.Equal(1, replay.GetProperty("version").GetInt64());

        var blind = await Put(owner, vehicle, today, amount: 1600m);
        Assert.Equal(HttpStatusCode.Conflict, blind.StatusCode);
        var conflict = await Body(blind);
        Assert.Equal(409, conflict.GetProperty("status").GetInt32());
        Assert.False(string.IsNullOrWhiteSpace(conflict.GetProperty("title").GetString()));
        Assert.False(string.IsNullOrWhiteSpace(conflict.GetProperty("detail").GetString()));
        var current = conflict.GetProperty("current");
        Assert.Equal($"{today:yyyy-MM-dd}", current.GetProperty("date").GetString());
        Assert.Equal("amount", current.GetProperty("status").GetString());
        Assert.Equal(1000m, current.GetProperty("expected").GetDecimal());
        Assert.Equal(1500m, current.GetProperty("amount").GetDecimal());
        Assert.Equal(JsonValueKind.Null, current.GetProperty("reason").ValueKind);
        Assert.True(current.GetProperty("canEdit").GetBoolean());
        Assert.False(current.GetProperty("editedAfterCapture").GetBoolean());
        Assert.Equal(1, current.GetProperty("version").GetInt64());

        var update = await Body(await Put(owner, vehicle, today, amount: 1600m, version: 1));
        Assert.Equal(id, update.GetProperty("id").GetGuid());
        Assert.Equal(2, update.GetProperty("version").GetInt64());

        var stale = await Put(owner, vehicle, today, amount: 1700m, version: 1);
        Assert.Equal(HttpStatusCode.Conflict, stale.StatusCode);
        var latest = (await Body(stale)).GetProperty("current");
        Assert.Equal(1600m, latest.GetProperty("amount").GetDecimal());
        Assert.Equal(2, latest.GetProperty("version").GetInt64());

        var cell = Assert.Single((await GetWeek(owner, $"?vehicleId={vehicle}")).Vehicles).On(today);
        Assert.Equal(1600m, cell.Amount);
        Assert.Equal(2L, cell.Version);
    }

    [Fact]
    public async Task OnlyAChangeToAPastDayIsAnEditAfterCapture()
    {
        var (today, company) = await Arrange();
        var vehicle = await Vehicle(app, company, "KAA 141A", today.AddDays(-10));
        await Records(app, vehicle, today.AddDays(-10), today.AddDays(-1));
        using var owner = await app.SignIn(Owner);

        Assert.Equal(HttpStatusCode.OK, (await Put(owner, vehicle, today, amount: 1500m)).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await Put(owner, vehicle, today, amount: 1600m, version: 1)).StatusCode);
        var afterUpdate = Assert.Single((await GetWeek(owner, $"?vehicleId={vehicle}")).Vehicles);
        Assert.False(afterUpdate.On(today).EditedAfterCapture);
        Assert.Equal(0, (await Dashboard(owner, "week")).GetProperty("editedRecords").GetInt32());

        Assert.Equal(HttpStatusCode.OK, (await Put(owner, vehicle, today.AddDays(-1), amount: 900m, version: 1)).StatusCode);
        var afterCorrection = Assert.Single((await GetWeek(owner, $"?vehicleId={vehicle}")).Vehicles);
        Assert.True(afterCorrection.On(today.AddDays(-1)).EditedAfterCapture);
        Assert.False(afterCorrection.On(today).EditedAfterCapture);
        Assert.Equal(1, (await Dashboard(owner, "week")).GetProperty("editedRecords").GetInt32());

        var history = await owner.GetFromJsonAsync<JsonElement>("/setup/history?pageSize=100");
        var reasons = history.GetProperty("items").EnumerateArray()
            .Where(x => x.GetProperty("section").GetString() == "revenue")
            .Select(x => x.GetProperty("reason").GetString()!)
            .ToArray();
        string Day(DateOnly date) => date.ToString("d MMM yyyy", CultureInfo.InvariantCulture);
        Assert.Equal([$"Corrected revenue for KAA 141A on {Day(today.AddDays(-1))}", $"Updated revenue for KAA 141A on {Day(today)}",
            $"Recorded revenue for KAA 141A on {Day(today)}"], reasons);
    }

    [Fact]
    public async Task AClerksOfflineReplayIsAcceptedOrShownAsAConflictNeverRefused()
    {
        var (today, company) = await Arrange();
        var vehicle = await Vehicle(app, company, "KAA 151A", today.AddDays(-10));
        await Records(app, vehicle, today.AddDays(-10), today.AddDays(-1));
        await ScopeToCompany(app, Clerk, company);
        using var clerk = await app.SignIn(Clerk);
        using var admin = await app.SignIn(Admin);

        var captured = await Body(await Put(clerk, vehicle, today, amount: 1500m));
        await SetBusinessDate(app, today.AddDays(1));

        // The phone lost the first response and replays the same entry after the day has closed.
        var replay = await Put(clerk, vehicle, today, amount: 1500m);
        Assert.Equal(HttpStatusCode.OK, replay.StatusCode);
        Assert.Equal(captured.GetProperty("id").GetGuid(), (await Body(replay)).GetProperty("id").GetGuid());

        Assert.Equal(HttpStatusCode.OK, (await Put(admin, vehicle, today, amount: 1400m, version: 1)).StatusCode);
        var stale = await Put(clerk, vehicle, today, amount: 1500m);
        Assert.Equal(HttpStatusCode.Conflict, stale.StatusCode);
        var current = (await Body(stale)).GetProperty("current");
        Assert.Equal(1400m, current.GetProperty("amount").GetDecimal());
        Assert.Equal(2, current.GetProperty("version").GetInt64());
        Assert.True(current.GetProperty("editedAfterCapture").GetBoolean());
        Assert.False(current.GetProperty("canEdit").GetBoolean());

        Assert.Equal(HttpStatusCode.Forbidden, (await Put(clerk, vehicle, today, amount: 1500m, version: 2)).StatusCode);
    }

    [Fact]
    public async Task TwoClerksCapturingTheSameDayAtOnceGetAConflictNotAServerError()
    {
        var (today, company) = await Arrange();
        var vehicle = await Vehicle(app, company, "KAA 161A", today);
        using var owner = await app.SignIn(Owner);

        // The other clerk's row lands between this request's read and its insert.
        await app.WithDb(db => db.Database.ExecuteSqlRawAsync("""
            CREATE TRIGGER other_clerk BEFORE INSERT ON RevenueRecords
            BEGIN
                INSERT INTO RevenueRecords (OrganizationId, Id, VehicleId, BusinessDate, Amount, Reason, Note,
                    CapturedAt, CapturedBy, UpdatedAt, UpdatedBy, CorrectedAfterDate, Version)
                VALUES (NEW.OrganizationId, upper(hex(randomblob(16))), NEW.VehicleId, NEW.BusinessDate, '900.0', NULL, NULL,
                    NEW.CapturedAt, NEW.CapturedBy, NEW.UpdatedAt, NEW.UpdatedBy, 0, 1);
            END
            """));
        var raced = await Put(owner, vehicle, today, amount: 1500m);
        await app.WithDb(db => db.Database.ExecuteSqlRawAsync("DROP TRIGGER other_clerk"));

        Assert.Equal(HttpStatusCode.Conflict, raced.StatusCode);
        var problem = await Body(raced);
        Assert.Equal(409, problem.GetProperty("status").GetInt32());
        Assert.False(problem.TryGetProperty("current", out _));
        Assert.Equal(HttpStatusCode.OK, (await Put(owner, vehicle, today, amount: 1500m)).StatusCode);
    }

    [Fact]
    public async Task TheVehicleFilterServesTheDetailAndHonoursDataScope()
    {
        var (today, company) = await Arrange();
        var other = await Company(app, "Outside Scope Fleet");
        var mine = await Vehicle(app, company, "KAA 171A", today.AddDays(-3));
        var theirs = await Vehicle(app, other, "KAA 172A", today.AddDays(-3));
        await ScopeToCompany(app, Clerk, company);
        using var clerk = await app.SignIn(Clerk);

        Assert.Equal([mine], (await GetWeek(clerk)).Vehicles.Select(x => x.Id).ToArray());
        Assert.Equal(mine, Assert.Single((await GetWeek(clerk, $"?vehicleId={mine}")).Vehicles).Id);
        Assert.Equal(HttpStatusCode.NotFound, (await clerk.GetAsync($"/setup/revenue?vehicleId={theirs}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await Put(clerk, theirs, today.AddDays(-3), amount: 1000m)).StatusCode);
    }

    [Fact]
    public async Task EachCapturePathChecksItsOwnPermission()
    {
        var (today, company) = await Arrange();
        var vehicle = await Vehicle(app, company, "KAA 181A", today.AddDays(-10));
        await Records(app, vehicle, today.AddDays(-10), today.AddDays(-3));
        await ScopeToCompany(app, Clerk, company);
        await Deny(app, Admin, "revenue.capture");
        using var admin = await app.SignIn(Admin);
        using var clerk = await app.SignIn(Clerk);

        // Office admin without capture: view and correct, but no capture and so no no-earnings reasons.
        Assert.Equal(HttpStatusCode.Forbidden, (await Put(admin, vehicle, today.AddDays(-2), amount: 1000m)).StatusCode);
        var adminRow = Assert.Single((await GetWeek(admin, $"?vehicleId={vehicle}")).Vehicles);
        Assert.False(adminRow.On(today.AddDays(-2)).CanEdit);
        Assert.True(adminRow.On(today.AddDays(-3)).CanEdit);
        Assert.Equal(HttpStatusCode.Forbidden, (await Put(admin, vehicle, today.AddDays(-3), reason: "Garage", version: 1)).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await Put(admin, vehicle, today.AddDays(-3), amount: 800m, version: 1)).StatusCode);

        // Revenue clerk: capture and no-earnings reasons, but no corrections after the day.
        Assert.Equal(HttpStatusCode.OK, (await Put(clerk, vehicle, today.AddDays(-2), reason: "Garage")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await Put(clerk, vehicle, today.AddDays(-2), reason: "Other", note: "Flat tyre", version: 1)).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await Put(clerk, vehicle, today.AddDays(-1), reason: "Other", note: "Flat tyre")).StatusCode);
        var clerkRow = Assert.Single((await GetWeek(clerk, $"?vehicleId={vehicle}")).Vehicles);
        Assert.False(clerkRow.On(today.AddDays(-1)).CanEdit);
        Assert.True(clerkRow.On(today).CanEdit);
        Assert.Equal(HttpStatusCode.OK, (await Put(clerk, vehicle, today, amount: 1200m)).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await Put(clerk, vehicle, today, amount: 1300m, version: 1)).StatusCode);
    }

    [Fact]
    public async Task CaptureFollowsTheBusinessDateAndTheVehiclesActiveDays()
    {
        var (today, company) = await Arrange();
        var vehicle = await Vehicle(app, company, "KAA 191A", today.AddDays(-2));
        var left = await Vehicle(app, company, "KAA 192A", today.AddDays(-5), leftOn: today.AddDays(-1));
        await Records(app, left, today.AddDays(-5), today.AddDays(-2));
        using var owner = await app.SignIn(Owner);

        // The calendar has moved on, but the business date has not.
        Assert.Equal(HttpStatusCode.BadRequest, (await Put(owner, vehicle, today.AddDays(1), amount: 1000m)).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await Put(owner, vehicle, today.AddDays(-3), amount: 1000m)).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await Put(owner, left, today.AddDays(-1), amount: 1000m)).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await Put(owner, vehicle, today.AddDays(-2), reason: "Other")).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await Put(owner, vehicle, today.AddDays(-2), reason: "Other", note: new string('x', 81))).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await Put(owner, vehicle, today.AddDays(-2), amount: 0m)).StatusCode);

        Assert.Equal(HttpStatusCode.OK, (await Put(owner, vehicle, today.AddDays(-2), amount: 1000m, note: "   ")).StatusCode);
        var row = Assert.Single((await GetWeek(owner, $"?vehicleId={vehicle}")).Vehicles);
        Assert.Null(row.On(today.AddDays(-2)).Note);
    }

    [Fact]
    public async Task WeeksStartOnTheOrganizationsFirstDayAndExpectedFollowsDatedTargets()
    {
        var (today, company) = await Arrange();
        await SetFirstDayOfWeek(app, DayOfWeek.Sunday);
        var sunday = today.AddDays(-4);
        var vehicle = await Vehicle(app, company, "KAA 201A", today.AddDays(-10), weeklyTarget: 5000m,
            revision: (14000m, today.AddDays(-1)));
        await Records(app, vehicle, today.AddDays(-10), today.AddDays(-1));
        var empty = await Company(app, "Empty Fleet");
        using var owner = await app.SignIn(Owner);

        var week = await GetWeek(owner, $"?companyId={company}");
        Assert.Equal(sunday, week.WeekStart);
        Assert.Equal(sunday, week.CurrentWeekStart);
        Assert.Equal(sunday, (await GetWeek(owner, $"?weekStart={today:yyyy-MM-dd}")).WeekStart);
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.GetAsync($"/setup/revenue?weekStart={sunday.AddDays(7):yyyy-MM-dd}")).StatusCode);
        Assert.Equal($"{sunday:yyyy-MM-dd}", (await Dashboard(owner, "week")).GetProperty("from").GetString());

        var row = Assert.Single(week.Vehicles);
        Assert.Equal(714.29m, row.On(today.AddDays(-2)).Expected);
        Assert.Equal(2000m, row.On(today.AddDays(-1)).Expected);
        Assert.Equal(4142.86m, row.TotalExpected);

        var none = await GetWeek(owner, $"?companyId={empty}");
        Assert.Empty(none.Vehicles);
        Assert.Equal(0m, none.TotalExpected);
        Assert.Null(none.Percent);
    }

    [Fact]
    public async Task DashboardEditsCountOnlyTheVehiclesActiveDaysLikeEveryOtherFigure()
    {
        var (today, company) = await Arrange();
        var vehicle = await Vehicle(app, company, "KAA 211A", today.AddDays(-10));
        await Records(app, vehicle, today.AddDays(-10), today.AddDays(-1));
        using var owner = await app.SignIn(Owner);
        Assert.Equal(HttpStatusCode.OK, (await Put(owner, vehicle, today.AddDays(-1), amount: 900m, version: 1)).StatusCode);
        Assert.Equal(1, (await Dashboard(owner, "week")).GetProperty("editedRecords").GetInt32());

        // Leaving the fleet from that day takes the corrected record out of the revenue, the target and the edits alike.
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var fleetVehicle = await db.Set<Auth.Domain.Setup.FleetVehicle>().IgnoreQueryFilters().SingleAsync(x => x.Id == vehicle);
            fleetVehicle.Retire(today.AddDays(-1), today);
            await db.SaveChangesAsync();
        });
        var dashboard = await Dashboard(owner, "week");
        Assert.Equal(2000m, dashboard.GetProperty("revenue").GetDecimal());
        Assert.Equal(0, dashboard.GetProperty("editedRecords").GetInt32());
    }

    [Fact]
    public async Task DashboardFiguresAreShownOnlyToPeopleWhoMaySeeTheirCard()
    {
        var (today, company) = await Arrange();
        var vehicle = await Vehicle(app, company, "KAA 221A", today.AddDays(-10));
        await Records(app, vehicle, today.AddDays(-10), today.AddDays(-2));
        await ScopeToCompany(app, Clerk, company);
        // Without revenue.view the office admin keeps dash.edits (it rests on audit.view) and loses every revenue card.
        await Deny(app, Admin, "revenue.view");
        using var editsOnly = await app.SignIn(Admin);
        using var clerk = await app.SignIn(Clerk);

        var edits = await Dashboard(editsOnly, "week");
        foreach (var hidden in new[] { "revenue", "expected", "percent", "capturedToday", "vehiclesToday", "missingDays", "missingVehicles" })
            Assert.Equal(JsonValueKind.Null, edits.GetProperty(hidden).ValueKind);
        Assert.Equal(0, edits.GetProperty("editedRecords").GetInt32());

        // A clerk sees the capture and gaps cards, but not the revenue or edits card.
        var capture = await Dashboard(clerk, "week");
        Assert.Equal(JsonValueKind.Null, capture.GetProperty("revenue").ValueKind);
        Assert.Equal(1, capture.GetProperty("vehiclesToday").GetInt32());
        Assert.Equal(1, capture.GetProperty("missingDays").GetInt32());
        Assert.Equal(JsonValueKind.Null, capture.GetProperty("editedRecords").ValueKind);
    }

    [Fact]
    public async Task CompanyOptionsKeepArchivedCompaniesOnlyForWeeksTheyHadAVehicleRunning()
    {
        var (today, company) = await Arrange();
        var monday = today.AddDays(-3);
        var archived = await Company(app, "Archived Fleet");
        await Vehicle(app, archived, "KAA 231A", today.AddDays(-30), leftOn: monday);
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            (await db.Set<Auth.Domain.Setup.PsvCompany>().IgnoreQueryFilters().SingleAsync(x => x.Id == archived)).Archive(monday);
            await db.SaveChangesAsync();
        });
        using var owner = await app.SignIn(Owner);

        Assert.Equal([company], (await GetWeek(owner)).Companies.Select(x => x.Id).ToArray());
        var lastWeek = await GetWeek(owner, $"?weekStart={monday.AddDays(-7):yyyy-MM-dd}");
        Assert.Equal([archived, company], lastWeek.Companies.Select(x => x.Id).ToArray());
    }

    private static async Task<Week> GetWeek(HttpClient client, string query = "") =>
        (await client.GetFromJsonAsync<Week>("/setup/revenue" + query))!;

    private static Task<JsonElement> Dashboard(HttpClient client, string period) =>
        client.GetFromJsonAsync<JsonElement>($"/setup/revenue/dashboard?period={period}");

    private static Task<HttpResponseMessage> Put(HttpClient client, Guid vehicle, DateOnly date,
        decimal? amount = null, string? reason = null, string? note = null, long? version = null) =>
        client.PutAsJsonAsync($"/setup/revenue/{vehicle}/{date:yyyy-MM-dd}", new { amount, reason, note, version });

    private static Task<JsonElement> Body(HttpResponseMessage response) => response.Content.ReadFromJsonAsync<JsonElement>();

    private sealed record Week(DateOnly WeekStart, DateOnly WeekThrough, DateOnly CurrentWeekStart, DateOnly BusinessDate,
        List<Option> Companies, List<Row> Vehicles, decimal TotalAmount, decimal TotalExpected, int? Percent);

    private sealed record Option(Guid Id, string Name);

    private sealed record Row(Guid Id, DateOnly? EarliestMissing, List<Cell> Days, decimal TotalAmount, decimal TotalExpected, int? Percent)
    {
        public Cell On(DateOnly date) => Days.Single(x => x.Date == date);
    }

    private sealed record Cell(DateOnly Date, string Status, decimal Expected, decimal? Amount, string? Reason, string? Note,
        bool CanEdit, bool EditedAfterCapture, long? Version);

    // D4: recorded revenue never disappears. A lifecycle change that would put a captured day outside the
    // vehicle's time in the fleet is refused, and the refusal names the day.
    [Fact]
    public async Task ALifecycleChangeCannotHideADayThatHasARecord()
    {
        var (today, company) = await Arrange();
        var joined = today.AddDays(-20);
        var vehicle = await Vehicle(app, company, "KDC 909C", joined);
        await Records(app, vehicle, today.AddDays(-5), today.AddDays(-2), 1000m);

        using var owner = await app.SignIn(Owner);

        // Leaving on a day it has a record for, or before one, would drop that record out of every report.
        var leaving = await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/retire", new { leftOn = today.AddDays(-2).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) });
        Assert.Equal(HttpStatusCode.BadRequest, leaving.StatusCode);
        Assert.Contains(today.AddDays(-2).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture), (await Body(leaving)).GetProperty("detail").GetString());

        // Joining after a day it already has a record for would do the same from the other end.
        var joining = await owner.PutAsJsonAsync($"/setup/vehicles/{vehicle}",
            new { companyId = company, registration = "KDC 909C", joinedOn = today.AddDays(-4).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture), weeklyTarget = 7000m });
        Assert.Equal(HttpStatusCode.BadRequest, joining.StatusCode);
        Assert.Contains(today.AddDays(-5).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture), (await Body(joining)).GetProperty("detail").GetString());

        // The day after its last record is allowed: nothing recorded falls outside the fleet.
        var allowed = await owner.PostAsJsonAsync($"/setup/vehicles/{vehicle}/retire", new { leftOn = today.AddDays(-1).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) });
        Assert.Equal(HttpStatusCode.OK, allowed.StatusCode);
    }

    public void Dispose() => app.Dispose();

}
