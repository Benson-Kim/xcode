using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application.CentralExpenses;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;
using Xunit;
using static Auth.Tests.RevenueTestData;

namespace Auth.Tests;

public sealed class CentralExpenseTests : IDisposable
{
    private readonly AuthFactory app = new();

    private sealed record World(DateOnly Today, Guid A, Guid B, Guid C, Guid Outside, Guid Tyres, Guid Parking, Guid Clerk, Guid Admin, Guid Owner);

    // The clerk works one company (A, B, C); the outside vehicle belongs to another. Each person signs in once per test:
    // a new device code cannot be sent again within a minute.
    private async Task<(World W, HttpClient Owner)> Arrange()
    {
        await app.SeedDemo();
        var today = PinnedThursday(app);
        await SetBusinessDate(app, today);
        var company = await Company(app, "Central Fleet");
        var other = await Company(app, "Other Fleet");
        var joined = today.AddDays(-30);
        var (a, b, c) = (await Vehicle(app, company, "KAA 601A", joined), await Vehicle(app, company, "KAB 602B", joined),
            await Vehicle(app, company, "KAC 603C", joined));
        var outside = await Vehicle(app, other, "KAD 604D", joined);
        await ScopeToCompany(app, Clerk, company);
        var owner = await app.SignIn(Owner);
        Guid clerk = default, admin = default, ownerId = default;
        await app.WithDb(async db =>
        {
            clerk = (await db.Users.SingleAsync(x => x.Email == Clerk)).Id;
            admin = (await db.Users.SingleAsync(x => x.Email == Admin)).Id;
            ownerId = (await db.Users.SingleAsync(x => x.Email == Owner)).Id;
        });
        return (new(today, a, b, c, outside, await ExpenseItemTestData.Id(owner, "Tyres"), await ExpenseItemTestData.Id(owner, "Parking"),
            clerk, admin, ownerId), owner);
    }

    [Fact]
    public async Task RecordingOnOneVehicleSavesOneRowThatTheLedgerShowsAndTheChangeLogNames()
    {
        var (w, owner) = await Arrange();
        var id = Guid.NewGuid();

        var recorded = await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 4, 4200m, [(w.A, 16800m)], id, "  Four tyres ")));
        Assert.Equal([id], recorded.Ids);
        Assert.Equal(16800m, recorded.Total);

        var ledger = await Ledger(owner, w.Today, w.Today);
        var row = Assert.Single(ledger.Items);
        Assert.Equal((id.ToString(), "central", w.Today, w.A, "KAA 601A", (Guid?)w.Tyres, "Tyres", "Garage and repairs", ExpenseBucket.RepairsAndMaintenance),
            (row.Id, row.Source, row.Date, row.VehicleId, row.Registration, row.ExpenseItemId, row.ItemName, row.CategoryName, row.Bucket));
        Assert.Equal((4m, 4200m, 16800m, "Four tyres", "Antony Maina", (string?)null, (Guid?)null, (ExpenseGroupDto?)null, (long?)1, true, true),
            (row.Units, row.UnitAmount, row.Total, row.Note, row.RecordedByName, row.HolderName, row.ScheduleId, row.Group, row.Version, row.CanEdit, row.CanRemove));
        Assert.Equal((w.Today, true, true), (ledger.BusinessDate, ledger.Permissions.CanRecord, ledger.Permissions.CanCorrect));
        Assert.Equal(new ExpenseFiguresDto(16800m, 16800m, 0m, 0m), ledger.Figures);
        Assert.Equal((1, 16800m, 1, 100), (ledger.Total, ledger.Amount, ledger.PageNumber, ledger.PageSize));

        var log = await Log(owner);
        Assert.Equal([(id, $"Recorded central expense on KAA 601A for {Long(w.Today)}: Tyres, KES 16,800")], log.Select(x => (x.EntityId, x.Reason)));
        await app.WithDb(async db =>
            Assert.Contains(await db.AuditEvents.IgnoreQueryFilters().ToListAsync(), x => x.Action == "expenses.recorded" && x.Entity == id.ToString()));

        // A refund is a negative amount.
        var refund = await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 1, -500m, [(w.A, -500m)])));
        Assert.Equal(-500m, refund.Total);
        Assert.Equal(16300m, (await Ledger(owner, w.Today, w.Today)).Figures.Central);
    }

    [Fact]
    public async Task ASplitSavesOneRowPerVehicleAndAnEvenSplitKeepsTheUnitCost()
    {
        var (w, owner) = await Arrange();
        var group = Guid.NewGuid();

        var even = await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 6, 2800m, [(w.A, 5600m), (w.B, 5600m), (w.C, 5600m)], group)));
        Assert.Equal(3, even.Ids.Distinct().Count());
        Assert.DoesNotContain(group, even.Ids);
        Assert.Equal(16800m, even.Total);
        var rows = (await Ledger(owner, w.Today, w.Today)).Items;
        Assert.Equal(3, rows.Count);
        Assert.All(rows, r => Assert.Equal((2m, 2800m, 5600m, new ExpenseGroupDto(group, 3, 16800m, 6m, 2800m)), (r.Units, r.UnitAmount, r.Total, r.Group)));
        Assert.Equal(even.Ids.Order(), rows.Select(r => Guid.Parse(r.Id)).Order());

        // Three entries in the change log, one for each row, each with the row's own amount.
        var log = await Log(owner);
        Assert.Equal(3, log.Count);
        Assert.Equal(new[] { "KAA 601A", "KAB 602B", "KAC 603C" }.Select(r => $"Recorded central expense on {r} for {Long(w.Today)}: Tyres, KES 5,600").Order(),
            log.Select(x => x.Reason).Order());

        // An uneven split cannot keep the unit cost: each row is one unit at its own amount.
        var yesterday = w.Today.AddDays(-1);
        await Recorded(await Post(owner, Buy(yesterday, w.Tyres, 1, 100m, [(w.A, 33.34m), (w.B, 33.33m), (w.C, 33.33m)])));
        var uneven = (await Ledger(owner, yesterday, yesterday)).Items.OrderBy(r => r.Registration).ToList();
        Assert.Equal([(1m, 33.34m, 33.34m), (1m, 33.33m, 33.33m), (1m, 33.33m, 33.33m)], uneven.Select(r => (r.Units, r.UnitAmount, r.Total)));
        Assert.All(uneven, r => Assert.Equal((3, 100m, 1m, 100m), (r.Group!.Size, r.Group.Total, r.Group.Units, r.Group.UnitAmount)));
        Assert.Single(uneven.Select(r => r.Group!.Id).Distinct());

        // Even, but a third of a unit is not a quantity: one unit at the vehicle's amount.
        var earlier = w.Today.AddDays(-2);
        await Recorded(await Post(owner, Buy(earlier, w.Tyres, 1, 90m, [(w.A, 30m), (w.B, 30m), (w.C, 30m)])));
        var thirds = (await Ledger(owner, earlier, earlier)).Items;
        Assert.All(thirds, r => Assert.Equal((1m, 30m, 30m, 1m, 90m), (r.Units, r.UnitAmount, r.Total, r.Group!.Units, r.Group.UnitAmount)));
    }

    [Fact]
    public async Task BadAllocationsAndLinesAreRefusedWithTheirReason()
    {
        var (w, owner) = await Arrange();
        var date = w.Today;
        const string vehicles = "Choose 1-50 distinct vehicles.";

        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 1, 300m, [(w.A, 100m), (w.B, 100m)])), "The vehicle amounts must add up to the total.");
        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 1, 300m, [(w.A, 100m), (w.B, 100m), (w.C, 101m)])), "The vehicle amounts must add up to the total.");
        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 1, 300m, [(w.A, 150m), (w.A, 150m)])), vehicles);
        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 1, 300m, [])), vehicles);
        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 51, 1m, [.. Enumerable.Range(0, 51).Select(_ => (Guid.NewGuid(), 1m))])), vehicles);
        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 1, 300m, [(Guid.Empty, 300m)])), vehicles);
        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 1, 300m, [(w.A, 400m), (w.B, -100m)])),
            "Each vehicle's amount must have the same sign as the total.");
        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 1, -300m, [(w.A, 150m), (w.B, 150m)])),
            "Each vehicle's amount must have the same sign as the total.");
        const string amount = "Each vehicle's amount must be other than zero, with at most two decimals.";
        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 1, 300m, [(w.A, 300m), (w.B, 0m)])), amount);
        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 1, 300m, [(w.A, 299.995m), (w.B, 0.005m)])), amount);

        const string units = "Units must be above zero, with at most three decimals.";
        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 0m, 100m, [(w.A, 100m)])), units);
        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 1.2345m, 100m, [(w.A, 123.45m)])), units);
        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 1, 0m, [(w.A, 100m)])), "Enter an amount other than zero.");
        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 1, 10.005m, [(w.A, 10.01m)])), "Enter the amount with at most two decimals.");
        await AssertBadRequest(await Post(owner, Buy(date, w.Tyres, 1, 100m, [(w.A, 100m)], note: new string('x', 81))), "The note must be at most 80 characters.");
        Assert.Empty((await Ledger(owner, date, date)).Items);

        // The total is units times the unit amount, rounded to the cent, halves away from zero.
        await Recorded(await Post(owner, Buy(date, w.Tyres, 2.5m, 0.33m, [(w.A, 0.83m)])));
        Assert.Equal(0.83m, Assert.Single((await Ledger(owner, date, date)).Items).Total);
    }

    [Fact]
    public async Task VehiclesDatesAndItemsAreCheckedWhereTheExpenseIsRecorded()
    {
        var (w, owner) = await Arrange();
        await Grant(app, Clerk, PermissionKeys.ExpensesCapture);
        using var clerk = await app.SignIn(Clerk);
        var retired = await Vehicle(app, await CompanyOf(w.A), "KAE 605E", w.Today.AddDays(-30), leftOn: w.Today.AddDays(-5));
        var stopped = await ExpenseItemTestData.Id(owner, "Old spares");
        (await owner.PostAsJsonAsync($"/setup/expense-items/{stopped}/stop", new { })).EnsureSuccessStatusCode();

        await AssertBadRequest(await Post(clerk, Buy(w.Today, w.Tyres, 1, 100m, [(w.Outside, 100m)])), "Choose one of your vehicles.");
        await AssertBadRequest(await Post(clerk, Buy(w.Today, w.Tyres, 1, 200m, [(w.A, 100m), (w.Outside, 100m)])), "Choose one of your vehicles.");
        await AssertBadRequest(await Post(clerk, Buy(w.Today, w.Tyres, 1, 100m, [(Guid.NewGuid(), 100m)])), "Choose one of your vehicles.");
        await AssertBadRequest(await Post(clerk, Buy(w.Today.AddDays(-40), w.Tyres, 1, 100m, [(w.A, 100m)])), "KAA 601A was not in the fleet on that day.");
        await AssertBadRequest(await Post(clerk, Buy(w.Today, w.Tyres, 1, 100m, [(retired, 100m)])), "KAE 605E was not in the fleet on that day.");
        await AssertBadRequest(await Post(clerk, Buy(w.Today.AddDays(1), w.Tyres, 1, 100m, [(w.A, 100m)])), "An expense cannot be recorded for a future date.");
        await AssertBadRequest(await Post(clerk, Buy(w.Today.AddDays(-3651), w.Tyres, 1, 100m, [(w.A, 100m)])), "Choose a date in the last ten years.");
        await AssertBadRequest(await Post(clerk, Buy(w.Today, stopped, 1, 100m, [(w.A, 100m)])), "Choose an item that is in use.");
        await AssertBadRequest(await Post(clerk, Buy(w.Today, Guid.NewGuid(), 1, 100m, [(w.A, 100m)])), "Choose an item that is in use.");
        Assert.Empty((await Ledger(owner, w.Today.AddDays(-60), w.Today)).Items);

        // The options follow the date: a vehicle that joined later is not offered before it joined.
        var late = await Vehicle(app, await CompanyOf(w.A), "KAF 606F", w.Today.AddDays(-3));
        var now = await Options(owner, w.Today);
        Assert.Equal(["KAA 601A", "KAB 602B", "KAC 603C", "KAD 604D", "KAF 606F"], now.Vehicles.Select(v => v.Registration));
        Assert.DoesNotContain(stopped, now.Items.Select(i => i.Id));
        Assert.Contains(now.Items, i => i.Id == w.Tyres && i.CategoryName == "Garage and repairs" && i.Bucket == ExpenseBucket.RepairsAndMaintenance);
        var before = await Options(owner, w.Today.AddDays(-10));
        Assert.DoesNotContain(late, before.Vehicles.Select(v => v.Id));
        Assert.Contains("KAE 605E", before.Vehicles.Select(v => v.Registration));
        Assert.Equal(["KAA 601A", "KAB 602B", "KAC 603C", "KAF 606F"], (await Options(clerk, w.Today)).Vehicles.Select(v => v.Registration));
        await AssertBadRequest(await owner.GetAsync($"/setup/expenses/options?date={Day(w.Today.AddDays(1))}"), "An expense cannot be recorded for a future date.");
    }

    [Fact]
    public async Task ARetriedSaveAnswersWithTheRowsItMadeAndAnotherPersonCannotTakeTheId()
    {
        var (w, owner) = await Arrange();
        using var admin = await app.SignIn(Admin);
        var (single, split) = (Guid.NewGuid(), Guid.NewGuid());

        var first = await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 1, 1200m, [(w.A, 1200m)], single)));
        var again = await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 1, 1200m, [(w.A, 1200m)], single)));
        Assert.Equal([single], again.Ids);
        Assert.Equal(first.Ids, again.Ids);
        Assert.Equal(1200m, again.Total);

        var body = Buy(w.Today, w.Tyres, 3, 100m, [(w.A, 100m), (w.B, 100m), (w.C, 100m)], split);
        var made = await Recorded(await Post(owner, body));
        var retried = await Recorded(await Post(owner, body));
        Assert.Equal(made.Ids.Order(), retried.Ids.Order());
        Assert.Equal(300m, retried.Total);
        Assert.Equal(4, (await Ledger(owner, w.Today, w.Today)).Total);
        Assert.Equal(4, (await Log(owner)).Count);

        foreach (var taken in new[] { single, split })
        {
            using var response = await Post(admin, Buy(w.Today, w.Tyres, 1, 50m, [(w.B, 50m)], taken));
            Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
            var problem = await response.Content.ReadFromJsonAsync<JsonElement>();
            Assert.Equal("This expense was already saved by someone else. Reload and try again.", problem.GetProperty("detail").GetString());
            Assert.True(!problem.TryGetProperty("current", out var current) || current.ValueKind == JsonValueKind.Null);
        }
        Assert.Equal(4, (await Ledger(owner, w.Today, w.Today)).Total);

        // The id of one row of a split is no purchase id either.
        using var rowId = await Post(owner, Buy(w.Today, w.Tyres, 1, 50m, [(w.B, 50m)], made.Ids[0]));
        Assert.Equal(HttpStatusCode.Conflict, rowId.StatusCode);
    }

    [Fact]
    public async Task ChangingBumpsTheVersionAnUnchangedSaveIsAReplayAndAStaleVersionConflictsWithTheCurrentRow()
    {
        var (w, owner) = await Arrange();
        var id = (await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 4, 4200m, [(w.A, 16800m)])))).Ids.Single();

        var noted = await Saved(await Put(owner, id, Edit(w, w.A, w.Tyres, 4, 4200m, 1, "Front axle")));
        Assert.Equal((id, 2L), (noted.Id, noted.Version));
        var row = Assert.Single((await Ledger(owner, w.Today, w.Today)).Items);
        Assert.Equal(("Front axle", 2L), (row.Note, row.Version));

        // The same values again change nothing and write nothing.
        var logged = (await Log(owner)).Count;
        Assert.Equal(noted, await Saved(await Put(owner, id, Edit(w, w.A, w.Tyres, 4, 4200m, 1, "Front axle"))));
        Assert.Equal(noted, await Saved(await Put(owner, id, Edit(w, w.A, w.Tyres, 4, 4200m, 2, "Front axle"))));
        Assert.Equal(logged, (await Log(owner)).Count);

        using var stale = await Put(owner, id, Edit(w, w.A, w.Tyres, 4, 4500m, 1, "Front axle"));
        Assert.Equal(HttpStatusCode.Conflict, stale.StatusCode);
        var current = (await stale.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("current");
        Assert.Equal((4200m, 2L, "Front axle", "central"), (current.GetProperty("unitAmount").GetDecimal(), current.GetProperty("version").GetInt64(),
            current.GetProperty("note").GetString(), current.GetProperty("source").GetString()));
        await AssertBadRequest(await Put(owner, id, Edit(w, w.A, w.Tyres, 4, 4500m, null, null)), "Send the version of the expense you opened.");

        // A new price, vehicle and day are one change, and the row follows the vehicle.
        var yesterday = w.Today.AddDays(-1);
        var moved = await Saved(await Put(owner, id, new { date = yesterday, vehicleId = w.B, expenseItemId = w.Tyres, units = 4m, unitAmount = 4500m, note = "Front axle", version = 2L }));
        Assert.Equal(3L, moved.Version);
        var after = Assert.Single((await Ledger(owner, yesterday, yesterday)).Items);
        Assert.Equal(("KAB 602B", 18000m), (after.Registration, after.Total));
        Assert.Empty((await Ledger(owner, w.Today, w.Today)).Items);
        Assert.Contains($"Changed central expense on KAB 602B for {Long(yesterday)}: Tyres, KES 18,000", (await Log(owner)).Select(x => x.Reason));

        await AssertBadRequest(await Put(owner, id, new { date = w.Today.AddDays(-40), vehicleId = w.B, expenseItemId = w.Tyres, units = 4m, unitAmount = 4500m, version = 3L }),
            "KAB 602B was not in the fleet on that day.");
        await AssertBadRequest(await Put(owner, id, new { date = w.Today.AddDays(1), vehicleId = w.B, expenseItemId = w.Tyres, units = 4m, unitAmount = 4500m, version = 3L }),
            "An expense cannot be recorded for a future date.");
        await AssertBadRequest(await Put(owner, id, new { date = yesterday, vehicleId = w.B, expenseItemId = Guid.NewGuid(), units = 4m, unitAmount = 4500m, version = 3L }),
            "Choose an item that is in use.");
        Assert.Equal(HttpStatusCode.NotFound, (await Put(owner, Guid.NewGuid(), Edit(w, w.A, w.Tyres, 1, 1m, 1, null))).StatusCode);
    }

    // The version is a real concurrency token: another writer's save between the read and the update loses the update.
    [Fact]
    public async Task ASaveThatLosesARaceOnTheVersionIsAConflictNotAnOverwrite()
    {
        var (w, owner) = await Arrange();
        var id = (await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 1, 100m, [(w.A, 100m)])))).Ids.Single();

        app.Database.Reset();
        app.Database.Interleave("CentralExpenses", "UPDATE \"CentralExpenses\" SET \"Version\" = \"Version\" + 1");
        using var raced = await Put(owner, id, Edit(w, w.A, w.Tyres, 1, 150m, 1, null));
        Assert.Equal(HttpStatusCode.Conflict, raced.StatusCode);
        Assert.Equal("Reload and try again.", (await raced.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString());

        var row = Assert.Single((await Ledger(owner, w.Today, w.Today)).Items);
        Assert.Equal((100m, 1L), (row.Total, row.Version));
        Assert.Single(await Log(owner));
    }

    [Fact]
    public async Task ChangingTheItemUnitsOrPriceTakesARowOutOfItsGroupButTheNoteAndVehicleDoNot()
    {
        var (w, owner) = await Arrange();
        var group = Guid.NewGuid();
        var made = await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 6, 2800m, [(w.A, 5600m), (w.B, 5600m), (w.C, 5600m)], group)));
        async Task<ExpenseLedgerRowDto> RowOn(Guid vehicle) => (await Ledger(owner, w.Today, w.Today)).Items.Single(r => r.VehicleId == vehicle);

        var (rowA, rowB, rowC) = (await RowOn(w.A), await RowOn(w.B), await RowOn(w.C));
        await Saved(await Put(owner, Guid.Parse(rowA.Id), Edit(w, w.A, w.Tyres, 2, 2800m, 1, "Left side")));
        var noted = await RowOn(w.A);
        Assert.Equal(("Left side", new ExpenseGroupDto(group, 3, 16800m, 6m, 2800m)), (noted.Note, noted.Group));

        // A dearer tyre is no longer the purchase: the row stands alone, with its own total, units and price.
        await Saved(await Put(owner, Guid.Parse(rowB.Id), Edit(w, w.B, w.Tyres, 2, 3000m, 1, null)));
        var priced = await RowOn(w.B);
        Assert.Equal((6000m, (ExpenseGroupDto?)null), (priced.Total, priced.Group));
        await Saved(await Put(owner, Guid.Parse(rowC.Id), Edit(w, w.C, w.Parking, 2, 2800m, 1, null)));
        Assert.Null((await RowOn(w.C)).Group);
        Assert.Equal(("Parking", "Charges"), ((await RowOn(w.C)).ItemName, (await RowOn(w.C)).CategoryName));

        // The group id stays the retry key, so the first save still answers with all three rows.
        var retried = await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 6, 2800m, [(w.A, 5600m), (w.B, 5600m), (w.C, 5600m)], group)));
        Assert.Equal(made.Ids.Order(), retried.Ids.Order());
        Assert.Equal(3, (await Ledger(owner, w.Today, w.Today)).Total);

        // The purchase still holds a row for A, whatever that row has become, so C cannot move onto A.
        await AssertBadRequest(await Put(owner, Guid.Parse(rowC.Id), Edit(w, w.A, w.Parking, 2, 2800m, 2, null)),
            "This purchase already has a row for KAA 601A.");
        // A row that kept its group may move to a vehicle the purchase does not use.
        var elsewhere = await Saved(await Put(owner, Guid.Parse(rowA.Id), Edit(w, w.Outside, w.Tyres, 2, 2800m, 2, "Left side")));
        Assert.Equal(3L, elsewhere.Version);
        Assert.Equal(new ExpenseGroupDto(group, 3, 16800m, 6m, 2800m), (await RowOn(w.Outside)).Group);
    }

    [Fact]
    public async Task RemovingNeedsAReasonAndTakesTheRowOutOfTheLedgerTheFiguresAndTheVehicleReport()
    {
        var (w, owner) = await Arrange();
        var id = (await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 4, 4200m, [(w.A, 16800m)])))).Ids.Single();
        var kept = (await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 1, 700m, [(w.A, 700m)])))).Ids.Single();
        Assert.Equal(17500m, (await Report(owner, w.A, w.Today)).MoneyOut);

        await AssertBadRequest(await Remove(owner, id, 1, ""), "A reason of 1–500 characters is required.");
        await AssertBadRequest(await Remove(owner, id, 1, new string('x', 501)), "A reason of 1–500 characters is required.");
        await AssertBadRequest(await owner.PostAsJsonAsync($"/setup/expenses/entries/{id}/remove", new { reason = "Typo" }), "Send the version of the expense you opened.");
        using var stale = await Remove(owner, id, 7, "Recorded twice");
        Assert.Equal(HttpStatusCode.Conflict, stale.StatusCode);
        Assert.Equal(16800m, (await stale.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("current").GetProperty("total").GetDecimal());

        var removed = await Saved(await Remove(owner, id, 1, "  Recorded twice "));
        Assert.Equal((id, 2L), (removed.Id, removed.Version));
        var ledger = await Ledger(owner, w.Today, w.Today);
        Assert.Equal([kept.ToString()], ledger.Items.Select(r => r.Id));
        Assert.Equal((new ExpenseFiguresDto(700m, 700m, 0m, 0m), 1, 700m), (ledger.Figures, ledger.Total, ledger.Amount));
        var report = await Report(owner, w.A, w.Today);
        Assert.Equal(700m, report.MoneyOut);
        Assert.Equal([kept], report.Postings.Select(p => p.ItemId));

        Assert.Equal(HttpStatusCode.NotFound, (await Remove(owner, id, 2, "Again")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await Put(owner, id, Edit(w, w.A, w.Tyres, 4, 4200m, 2, "Back"))).StatusCode);
        Assert.Contains((await Log(owner)).Select(x => x.Reason),
            reason => reason == $"Removed central expense on KAA 601A for {Long(w.Today)}: Tyres, KES 16,800. Reason: Recorded twice.");
        await app.WithDb(async db =>
        {
            var row = await db.Set<CentralExpense>().IgnoreQueryFilters().SingleAsync(x => x.Id == id);
            Assert.Equal(("Recorded twice", (Guid?)w.Owner, 2L), (row.RemovalReason, row.RemovedBy, row.Version));
        });
    }

    [Fact]
    public async Task ViewersCannotRecordCapturersChangeOnlyTheirOwnRowsOfTheDayAndCorrectorsChangeAny()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);
        using var admin = await app.SignIn(Admin);
        var yesterday = w.Today.AddDays(-1);
        await Grant(app, Clerk, PermissionKeys.ExpensesView);

        Assert.Equal(HttpStatusCode.Forbidden, (await Post(clerk, Buy(w.Today, w.Tyres, 1, 100m, [(w.A, 100m)]))).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await clerk.GetAsync("/setup/expenses/options")).StatusCode);
        var viewing = await Ledger(clerk, w.Today, w.Today);
        Assert.Equal((false, false), (viewing.Permissions.CanRecord, viewing.Permissions.CanCorrect));

        await Grant(app, Clerk, PermissionKeys.ExpensesCapture);
        Assert.Equal(HttpStatusCode.OK, (await clerk.GetAsync("/setup/expenses/options")).StatusCode);
        var (mine, old) = ((await Recorded(await Post(clerk, Buy(w.Today, w.Tyres, 1, 100m, [(w.A, 100m)])))).Ids.Single(),
            (await Recorded(await Post(clerk, Buy(yesterday, w.Tyres, 1, 200m, [(w.A, 200m)])))).Ids.Single());
        var theirs = (await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 1, 300m, [(w.A, 300m)])))).Ids.Single();

        var ledger = await Ledger(clerk, yesterday, w.Today);
        Assert.Equal((true, false), (ledger.Permissions.CanRecord, ledger.Permissions.CanCorrect));
        var flags = ledger.Items.ToDictionary(r => Guid.Parse(r.Id), r => (r.CanEdit, r.CanRemove));
        Assert.Equal((true, true), flags[mine]);
        Assert.Equal((false, false), flags[old]);
        Assert.Equal((false, false), flags[theirs]);

        const string correct = "needs the permission \"Change an expense after the day\".";
        Assert.Equal(2L, (await Saved(await Put(clerk, mine, Edit(w, w.A, w.Tyres, 1, 100m, 1, "Mine")))).Version);
        await AssertForbidden(await Put(clerk, old, Edit(w, w.A, w.Tyres, 1, 250m, 1, null)), $"Changing an expense from an earlier day {correct}");
        await AssertForbidden(await Put(clerk, theirs, Edit(w, w.A, w.Tyres, 1, 350m, 1, null)), $"Changing someone else's expense {correct}");
        await AssertForbidden(await Remove(clerk, old, 1, "Wrong day"), $"Changing an expense from an earlier day {correct}");
        await AssertForbidden(await Remove(clerk, theirs, 1, "Not mine"), $"Changing someone else's expense {correct}");
        await AssertForbidden(await Put(clerk, mine, new { date = yesterday, vehicleId = w.A, expenseItemId = w.Tyres, units = 1m, unitAmount = 100m, note = "Mine", version = 2L }),
            $"Changing the date of an expense {correct}");

        // Someone who corrects changes any row, on any day, and may move it to another day.
        var adminView = await Ledger(admin, yesterday, w.Today);
        Assert.True(adminView.Items.All(r => r.CanEdit && r.CanRemove));
        Assert.Equal(2L, (await Saved(await Put(admin, old, Edit(w, w.A, w.Tyres, 1, 250m, 1, "Corrected")))).Version);
        Assert.Equal(2L, (await Saved(await Put(admin, theirs, new { date = yesterday, vehicleId = w.A, expenseItemId = w.Tyres, units = 1m, unitAmount = 300m, version = 1L }))).Version);
        Assert.Equal(3L, (await Saved(await Remove(admin, mine, 2, "Entered by mistake"))).Version);
    }

    [Fact]
    public async Task TheLedgerHoldsApprovedPettyCashScheduledRunsAndCentralRowsButNeverSavings()
    {
        var (w, owner) = await Arrange();
        var data = await FillLedger(w, owner);

        var ledger = await Ledger(owner, w.Today.AddDays(-10), w.Today.AddDays(5));
        Assert.Equal((w.Today.AddDays(-10), w.Today.AddDays(5), w.Today), (ledger.From, ledger.To, ledger.BusinessDate));
        Assert.Equal(new ExpenseFiguresDto(3300m, 1500m, 1200m, 600m), ledger.Figures);
        Assert.Equal((5, 3300m), (ledger.Total, ledger.Amount));
        // Newest first; within a day central, then petty cash, then scheduled.
        Assert.Equal([("central", w.Today), ("pettycash", w.Today), ("scheduled", w.Today), ("central", w.Today.AddDays(-1)), ("scheduled", w.Today.AddDays(-7))],
            ledger.Items.Select(r => (r.Source, r.Date)));

        var petty = ledger.Items[1];
        Assert.Equal((data.Petty.ToString(), "Tyres", "Garage and repairs", 1200m, "Wanjiru Kamau", "Peter Otieno"),
            (petty.Id, petty.ItemName, petty.CategoryName, petty.Total, petty.HolderName, petty.RecordedByName));
        Assert.Equal(((long?)null, false, false, (Guid?)null, (ExpenseGroupDto?)null), (petty.Version, petty.CanEdit, petty.CanRemove, petty.ScheduleId, petty.Group));

        var scheduled = ledger.Items[2];
        Assert.Equal(($"{data.Schedule}:{Day(w.Today)}:{w.A}", "Parking", "Charges", (Guid?)w.Parking, ExpenseBucket.RecurringCharges),
            (scheduled.Id, scheduled.ItemName, scheduled.CategoryName, scheduled.ExpenseItemId, scheduled.Bucket));
        Assert.Equal(((Guid?)data.Schedule, (string?)null, (string?)null, 1m, 300m, 300m, false, false),
            (scheduled.ScheduleId, scheduled.RecordedByName, scheduled.HolderName, scheduled.Units, scheduled.UnitAmount, scheduled.Total, scheduled.CanEdit, scheduled.CanRemove));
        Assert.DoesNotContain(ledger.Items, r => r.ItemName == "Owner savings" || r.ItemName == "Next week");
        Assert.DoesNotContain(ledger.Items, r => r.Date > w.Today);

        // Nothing is posted after the business date, and the period after it is empty.
        var future = await Ledger(owner, w.Today.AddDays(1), w.Today.AddDays(3));
        Assert.Equal((0, 0m, new ExpenseFiguresDto(0m, 0m, 0m, 0m)), (future.Total, future.Amount, future.Figures));

        // The vehicle report reads the same postings: savings stay in it, petty cash only while approved.
        var report = await Report(owner, w.A, w.Today);
        // 1,000 central, 1,200 approved petty cash and the Parking runs of the last three Thursdays.
        Assert.Equal(1000m + 1200m + 3 * 300m, report.MoneyOut);
        Assert.Equal(3 * 1000m, report.Savings);
        Assert.Equal(["central", "pettycash"], report.Postings.Where(p => p.Source is not null).Select(p => p.Source!).Distinct().Order());
    }

    [Fact]
    public async Task SourceAndSearchNarrowTheRowsButNotTheFiguresAndPagingCountsEveryMatch()
    {
        var (w, owner) = await Arrange();
        await FillLedger(w, owner);
        var (from, to) = (w.Today.AddDays(-10), w.Today.AddDays(5));
        var everything = new ExpenseFiguresDto(3300m, 1500m, 1200m, 600m);

        async Task<ExpenseLedgerDto> Narrow(string extra)
        {
            var result = await Ledger(owner, from, to, extra);
            Assert.Equal(everything, result.Figures);
            return result;
        }

        var central = await Narrow("&source=central");
        Assert.Equal((2, 1500m), (central.Total, central.Amount));
        Assert.All(central.Items, r => Assert.Equal("central", r.Source));
        var petty = await Narrow("&source=pettycash");
        Assert.Equal((1, 1200m), (petty.Total, petty.Amount));
        var scheduled = await Narrow("&source=scheduled");
        Assert.Equal((2, 600m), (scheduled.Total, scheduled.Amount));

        Assert.Equal((3, 2700m), ((await Narrow("&q=tyres")).Total, (await Narrow("&q=TYRES")).Amount));
        Assert.Equal((1, 500m), ((await Narrow("&q=KAB")).Total, (await Narrow("&q=kab+602")).Amount));
        Assert.Equal(1, (await Narrow("&q=front")).Total);
        Assert.Equal(["pettycash"], (await Narrow("&q=wanjiru")).Items.Select(r => r.Source));
        Assert.Equal(["pettycash"], (await Narrow("&q=otieno")).Items.Select(r => r.Source));
        Assert.Equal(["central", "central"], (await Narrow("&q=antony")).Items.Select(r => r.Source));
        Assert.Equal((2, 600m), ((await Narrow("&q=charges")).Total, (await Narrow("&q=parking")).Amount));
        Assert.Equal(3, (await Narrow("&q=garage")).Total);
        Assert.Equal((1, 1200m), ((await Narrow("&q=tyres&source=pettycash")).Total, (await Narrow("&q=tyres&source=pettycash")).Amount));
        Assert.Equal(0, (await Narrow("&q=nothing+like+this")).Total);

        var first = await Narrow("&pageSize=2");
        Assert.Equal((2, 5, 3300m, 1, 2), (first.Items.Count, first.Total, first.Amount, first.PageNumber, first.PageSize));
        var second = await Narrow("&pageSize=2&page=2");
        var third = await Narrow("&pageSize=2&page=3");
        Assert.Equal((2, 1, 5, 3300m), (second.Items.Count, third.Items.Count, third.Total, third.Amount));
        Assert.Equal(5, first.Items.Concat(second.Items).Concat(third.Items).Select(r => r.Id).Distinct().Count());
        Assert.Empty((await Narrow("&pageSize=2&page=4")).Items);

        await AssertBadRequest(await owner.GetAsync($"/setup/expenses/ledger?from={Day(from)}&to={Day(to)}&source=bills"), "Choose central, petty cash or scheduled.");
        await AssertBadRequest(await owner.GetAsync($"/setup/expenses/ledger?from={Day(from)}&to={Day(to)}&q={new string('x', 201)}"), "Search for 200 characters or fewer.");
        await AssertBadRequest(await owner.GetAsync($"/setup/expenses/ledger?from={Day(to)}&to={Day(from)}"), "The first date cannot be after the last date.");
        await AssertBadRequest(await owner.GetAsync($"/setup/expenses/ledger?from={Day(from)}&to={Day(from.AddDays(367))}"), "Choose a period of at most 367 days.");
        Assert.Equal(HttpStatusCode.OK, (await owner.GetAsync($"/setup/expenses/ledger?from={Day(from)}&to={Day(from.AddDays(366))}")).StatusCode);
        await AssertBadRequest(await owner.GetAsync($"/setup/expenses/ledger?from={Day(from)}&to={Day(to)}&pageSize=101"), "Page must be 1–100000 and page size 1–100.");
        await AssertBadRequest(await owner.GetAsync($"/setup/expenses/ledger?to={Day(to)}"), "Choose the first and the last date.");
    }

    [Fact]
    public async Task APersonSeesNoRowsFiguresOptionsOrLogForVehiclesOutsideTheirScope()
    {
        var (w, owner) = await Arrange();
        await Grant(app, Clerk, PermissionKeys.ExpensesCapture);
        await Grant(app, Clerk, PermissionKeys.AuditView);
        using var clerk = await app.SignIn(Clerk);
        await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 2, 1000m, [(w.A, 1000m), (w.Outside, 1000m)])));
        var hidden = (await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 1, 4000m, [(w.Outside, 4000m)])))).Ids.Single();
        await Schedule("Parking", RecurringKind.Cost, 300m, (int)w.Today.DayOfWeek, w.Today.AddDays(-10), w.Outside, w.Parking, ExpenseBucket.RecurringCharges);
        await SeedPettyCash(w, w.Clerk, w.Clerk, w.Outside, w.Tyres, 900m, w.Today, "approved");

        var all = await Ledger(owner, w.Today, w.Today);
        Assert.Equal((7200m, 5), (all.Figures.Total, all.Total));
        var mine = await Ledger(clerk, w.Today, w.Today);
        Assert.Equal([w.A], mine.Items.Select(r => r.VehicleId));
        Assert.Equal((new ExpenseFiguresDto(1000m, 1000m, 0m, 0m), 1, 1000m), (mine.Figures, mine.Total, mine.Amount));
        Assert.Equal(0, (await Ledger(clerk, w.Today, w.Today, "&q=KAD")).Total);

        Assert.DoesNotContain(w.Outside, (await Options(clerk, w.Today)).Vehicles.Select(v => v.Id));
        Assert.Equal(HttpStatusCode.NotFound, (await Put(clerk, hidden, Edit(w, w.Outside, w.Tyres, 1, 1m, 1, null))).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await Remove(clerk, hidden, 1, "Not mine")).StatusCode);
        await AssertBadRequest(await Post(clerk, Buy(w.Today, w.Tyres, 1, 10m, [(w.Outside, 10m)])), "Choose one of your vehicles.");

        // The change log shows the clerk the row on their own vehicle and nothing about the other one.
        var seen = await Log(clerk);
        Assert.Equal(3, (await Log(owner)).Count);
        Assert.Contains("KAA 601A", Assert.Single(seen).Reason);
    }

    [Fact]
    public async Task AnotherOrganizationsRowsAreNeverSeenOrChanged()
    {
        var (w, owner) = await Arrange();
        Guid foreign = default;
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var organization = new Organization { Slug = "elsewhere", Name = "Elsewhere" };
            db.Organizations.Add(organization);
            await db.SaveChangesAsync();
            var company = new PsvCompany(organization.Id, "Elsewhere Fleet");
            var vehicle = new FleetVehicle(organization.Id, company.Id, new VehicleRegistration("KZZ 999Z"), w.Today.AddDays(-30), 7000m);
            var category = new ExpenseCategory(organization.Id, "Elsewhere repairs", ExpenseBucket.RepairsAndMaintenance);
            var item = new ExpenseItem(category, "Elsewhere tyres");
            db.AddRange(company, vehicle, category, item);
            await db.SaveChangesAsync();
            var rows = CentralExpense.Record(null, organization.Id, new CentralPurchase(w.Today, item.Id, 1, 999m, null, [new(vehicle.Id, 999m)]),
                app.Clock.UtcNow.ToUniversalTime(), Guid.NewGuid());
            db.AddRange(rows);
            await db.SaveChangesAsync();
            foreign = rows.Single().Id;
        });
        await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 1, 100m, [(w.A, 100m)])));

        var ledger = await Ledger(owner, w.Today, w.Today);
        Assert.Equal((100m, 1), (ledger.Figures.Total, ledger.Total));
        Assert.DoesNotContain(ledger.Items, r => r.Id == foreign.ToString());
        Assert.Equal(HttpStatusCode.NotFound, (await Put(owner, foreign, Edit(w, w.A, w.Tyres, 1, 1m, 1, null))).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await Remove(owner, foreign, 1, "Not ours")).StatusCode);
        // The other organization's id is free here.
        Assert.Equal([foreign], (await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 1, 50m, [(w.B, 50m)], foreign)))).Ids);
    }

    [Fact]
    public async Task TheOpenApiDocumentDescribesTheCentralExpenseRoutes()
    {
        using var client = app.CreateClient();
        using var document = JsonDocument.Parse(await client.GetStringAsync("/openapi/v1.json"));
        var paths = document.RootElement.GetProperty("paths");
        foreach (var path in new[] { "/setup/expenses/ledger", "/setup/expenses/options", "/setup/expenses/entries", "/setup/expenses/entries/{id}",
                     "/setup/expenses/entries/{id}/remove" })
            Assert.True(paths.TryGetProperty(path, out _), path);
        Assert.True(paths.GetProperty("/setup/expenses/entries/{id}").TryGetProperty("put", out _));
    }

    // Stored and scheduled rows meet on the business date. Eight rows, newest first, with each day listing central, then
    // petty cash, then scheduled: the pages are cut from the database, so every page boundary has to land in the right place.
    [Fact]
    public async Task PagesAreCutInTheDatabaseAndKeepTheOrderAcrossADayWhereAllThreeSourcesMeet()
    {
        var (w, owner) = await Arrange();
        var yesterday = w.Today.AddDays(-1);
        var lastWeek = w.Today.AddDays(-7);
        var centralA = (await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 1, 1000m, [(w.A, 1000m)])))).Ids.Single();
        var centralB = (await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 1, 500m, [(w.B, 500m)])))).Ids.Single();
        var centralC = (await Recorded(await Post(owner, Buy(yesterday, w.Tyres, 1, 100m, [(w.C, 100m)])))).Ids.Single();
        var petty = await SeedPettyCash(w, w.Clerk, w.Admin, w.A, w.Tyres, 1200m, w.Today, "approved");
        var schedule = await ScheduleShared("Parking", 300m, (int)DayOfWeek.Thursday, w.Today.AddDays(-20), [w.A, w.C], w.Parking);
        string Scheduled(DateOnly day, Guid vehicle) => $"{schedule}:{Day(day)}:{vehicle}";
        string[] expected =
        [
            centralA.ToString(), centralB.ToString(), petty.ToString(), Scheduled(w.Today, w.A), Scheduled(w.Today, w.C),
            centralC.ToString(), Scheduled(lastWeek, w.A), Scheduled(lastWeek, w.C)
        ];
        var (from, to) = (w.Today.AddDays(-10), w.Today);

        foreach (var size in new[] { 2, 3, 5, 8 })
        {
            var seen = new List<string>();
            for (var page = 1; page <= (expected.Length + size - 1) / size; page++)
            {
                var result = await Ledger(owner, from, to, $"&pageSize={size}&page={page}");
                Assert.Equal(expected.Skip((page - 1) * size).Take(size), result.Items.Select(r => r.Id));
                Assert.Equal((8, 4000m, page, size), (result.Total, result.Amount, result.PageNumber, result.PageSize));
                Assert.Equal(new ExpenseFiguresDto(4000m, 1600m, 1200m, 1200m), result.Figures);
                seen.AddRange(result.Items.Select(r => r.Id));
            }
            Assert.Equal(expected, seen);
            var past = await Ledger(owner, from, to, $"&pageSize={size}&page={(expected.Length + size - 1) / size + 1}");
            Assert.Empty(past.Items);
            Assert.Equal((8, 4000m), (past.Total, past.Amount));
        }

        // The source and the search change what is counted and where the pages fall, so the database applies them.
        var vehicleC = await Ledger(owner, from, to, "&q=KAC&pageSize=2");
        Assert.Equal([Scheduled(w.Today, w.C), centralC.ToString()], vehicleC.Items.Select(r => r.Id));
        Assert.Equal((3, 700m), (vehicleC.Total, vehicleC.Amount));
        Assert.Equal([Scheduled(lastWeek, w.C)], (await Ledger(owner, from, to, "&q=KAC&pageSize=2&page=2")).Items.Select(r => r.Id));
        var stored = await Ledger(owner, from, to, "&source=central&pageSize=2&page=2");
        Assert.Equal([centralC.ToString()], stored.Items.Select(r => r.Id));
        Assert.Equal((3, 1600m), (stored.Total, stored.Amount));
        var onlyScheduled = await Ledger(owner, from, to, "&source=scheduled&pageSize=3&page=2");
        Assert.Equal([Scheduled(lastWeek, w.C)], onlyScheduled.Items.Select(r => r.Id));
        Assert.Equal((4, 1200m), (onlyScheduled.Total, onlyScheduled.Amount));
        var pettyOnly = await Ledger(owner, from, to, "&source=pettycash");
        Assert.Equal([petty.ToString()], pettyOnly.Items.Select(r => r.Id));
        Assert.Equal((1, 1200m), (pettyOnly.Total, pettyOnly.Amount));
        var byPerson = await Ledger(owner, from, to, "&q=wanjiru+kamau");
        Assert.Equal([petty.ToString()], byPerson.Items.Select(r => r.Id));
        Assert.Equal((1, 1200m), (byPerson.Total, byPerson.Amount));
    }

    // The ledger reads the same number of times however many rows the period holds, and the rows it reads for a page do not
    // grow with them.
    [Fact]
    public async Task TheLedgerReadsTheSameNumberOfTimesHoweverManyRowsThePeriodHolds()
    {
        var (w, owner) = await Arrange();
        await ScheduleShared("Parking", 300m, (int)DayOfWeek.Friday, w.Today.AddDays(-20), [w.A, w.B], w.Parking);
        var from = w.Today.AddDays(-30);

        async Task<(int Reads, int Rows, int Total)> Measure(string extra = "")
        {
            app.Database.Reset();
            var result = await Ledger(owner, from, w.Today, $"&pageSize=10{extra}");
            Assert.Equal(Math.Min(10, result.Total), result.Items.Count);
            var reads = app.Database.Sql.Count(sql => sql.TrimStart().StartsWith("SELECT", StringComparison.OrdinalIgnoreCase));
            return (reads, app.Database.Rows, result.Total);
        }

        await SeedCentral(w, 0, 5);
        var few = await Measure();
        var fewSearched = await Measure("&q=tyres");
        var fewSource = await Measure("&source=central");
        await SeedCentral(w, 5, 145);
        var some = await Measure();
        await SeedCentral(w, 150, 150);
        var many = await Measure();

        Assert.Equal(few.Total + 145, some.Total);
        Assert.Equal(some.Total + 150, many.Total);
        Assert.Equal([few.Reads], new[] { some.Reads, many.Reads, fewSearched.Reads, fewSource.Reads, (await Measure("&q=tyres")).Reads, (await Measure("&source=central")).Reads }.Distinct());
        // 25 days of rows however many there are: the same days are counted and the same ten stored rows read (the scheduled
        // Fridays fall on older days than the page).
        Assert.Equal(some.Rows, many.Rows);
    }

    private sealed record Ledgered(Guid Petty, Guid Schedule);

    // Central 1,000 on A today with a note and 500 on B yesterday; petty cash approved 1,200 on A (waiting, sent back and
    // removed ones beside it); a Parking schedule of 300 on A each Thursday, savings of 1,000 and one that starts tomorrow.
    private async Task<Ledgered> FillLedger(World w, HttpClient owner)
    {
        await Recorded(await Post(owner, Buy(w.Today, w.Tyres, 1, 1000m, [(w.A, 1000m)], note: "Front tyres")));
        await Recorded(await Post(owner, Buy(w.Today.AddDays(-1), w.Tyres, 1, 500m, [(w.B, 500m)])));
        var petty = await SeedPettyCash(w, w.Clerk, w.Admin, w.A, w.Tyres, 1200m, w.Today, "approved");
        await SeedPettyCash(w, w.Clerk, w.Clerk, w.A, w.Tyres, 700m, w.Today, "waiting");
        await SeedPettyCash(w, w.Clerk, w.Clerk, w.A, w.Tyres, 300m, w.Today, "sentBack");
        await SeedPettyCash(w, w.Clerk, w.Clerk, w.A, w.Tyres, 400m, w.Today, "removed");
        var thursday = (int)DayOfWeek.Thursday;
        var schedule = await Schedule("Parking", RecurringKind.Cost, 300m, thursday, w.Today.AddDays(-20), w.A, w.Parking, ExpenseBucket.RecurringCharges);
        await Schedule("Owner savings", RecurringKind.Savings, 1000m, thursday, w.Today.AddDays(-20), w.A, null, null);
        await Schedule("Next week", RecurringKind.Cost, 999m, (int)DayOfWeek.Friday, w.Today.AddDays(1), w.A, w.Parking, ExpenseBucket.RecurringCharges);
        return new(petty, schedule);
    }

    private async Task<Guid> ScheduleShared(string name, decimal perVehicle, int weekday, DateOnly start, Guid[] vehicles, Guid item)
    {
        var id = Guid.Empty;
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var organization = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
            var recurring = new RecurringItem(organization, new RecurringDefinition(name, RecurringKind.Cost, perVehicle * vehicles.Length,
                new RecurringSchedule(RecurrenceFrequency.Weekly, weekday), start, null, [.. vehicles.Select(v => new VehicleShare(v, perVehicle))],
                item, ExpenseBucket.RecurringCharges));
            db.Add(recurring);
            await db.SaveChangesAsync();
            id = recurring.Id;
        });
        return id;
    }

    // Straight into the database: rows spread over the 25 days before the business date, on vehicle A.
    private Task SeedCentral(World w, int first, int count) => app.WithDb(async db =>
    {
        db.Provisioning = true;
        var organization = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
        var now = app.Clock.UtcNow.ToUniversalTime();
        for (var i = first; i < first + count; i++)
            db.AddRange(CentralExpense.Record(null, organization,
                new CentralPurchase(w.Today.AddDays(-(i % 25)), w.Tyres, 1, 10m + i, null, [new(w.A, 10m + i)]), now, w.Owner));
        await db.SaveChangesAsync();
    });

    private async Task<Guid> Schedule(string name, RecurringKind kind, decimal amount, int weekday, DateOnly start, Guid vehicle, Guid? item,
        ExpenseBucket? bucket)
    {
        var id = Guid.Empty;
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var organization = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
            var recurring = new RecurringItem(organization, new RecurringDefinition(name, kind, amount,
                new RecurringSchedule(RecurrenceFrequency.Weekly, weekday), start, null, [new(vehicle, amount)], item, bucket));
            db.Add(recurring);
            await db.SaveChangesAsync();
            id = recurring.Id;
        });
        return id;
    }

    private async Task<Guid> SeedPettyCash(World w, Guid holder, Guid recordedBy, Guid vehicle, Guid item, decimal amount, DateOnly date, string state)
    {
        var id = Guid.NewGuid();
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var organization = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
            var now = app.Clock.UtcNow.ToUniversalTime();
            var entry = new PettyCashEntry(id, organization, holder,
                new PettyCashLine(PettyCashKind.Expense, date, vehicle, item, 1, amount, null, null, false), now, recordedBy);
            if (state is "approved" or "removed") entry.Approve(now, w.Admin);
            if (state == "sentBack") entry.SendBack("Attach the receipt", now, w.Admin);
            if (state == "removed") entry.Remove("Wrong", now, w.Admin);
            db.Add(entry);
            await db.SaveChangesAsync();
        });
        return id;
    }

    private async Task<Guid> CompanyOf(Guid vehicle)
    {
        var company = Guid.Empty;
        await app.WithDb(async db => company = (await db.Set<FleetVehicle>().IgnoreQueryFilters().SingleAsync(v => v.Id == vehicle)).CompanyId);
        return company;
    }

    private static string Day(DateOnly date) => date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    private static string Long(DateOnly date) => date.ToString("d MMM yyyy", CultureInfo.InvariantCulture);

    private static object Buy(DateOnly date, Guid item, decimal units, decimal unitAmount, (Guid Vehicle, decimal Amount)[] allocations,
        Guid? id = null, string? note = null) =>
        new
        {
            id,
            date,
            expenseItemId = item,
            units,
            unitAmount,
            note,
            allocations = allocations.Select(a => new { vehicleId = a.Vehicle, amount = a.Amount }).ToArray()
        };

    private static object Edit(World w, Guid vehicle, Guid item, decimal units, decimal unitAmount, long? version, string? note) =>
        new { date = w.Today, vehicleId = vehicle, expenseItemId = item, units, unitAmount, note, version };

    private static Task<HttpResponseMessage> Post(HttpClient client, object body) => client.PostAsJsonAsync("/setup/expenses/entries", body);

    private static Task<HttpResponseMessage> Put(HttpClient client, Guid id, object body) => client.PutAsJsonAsync($"/setup/expenses/entries/{id}", body);

    private static Task<HttpResponseMessage> Remove(HttpClient client, Guid id, long version, string reason) =>
        client.PostAsJsonAsync($"/setup/expenses/entries/{id}/remove", new { version, reason });

    private static async Task<ExpenseLedgerDto> Ledger(HttpClient client, DateOnly from, DateOnly to, string extra = "") =>
        (await client.GetFromJsonAsync<ExpenseLedgerDto>($"/setup/expenses/ledger?from={Day(from)}&to={Day(to)}{extra}"))!;

    private static async Task<ExpenseOptionsDto> Options(HttpClient client, DateOnly date) =>
        (await client.GetFromJsonAsync<ExpenseOptionsDto>($"/setup/expenses/options?date={Day(date)}"))!;

    private static async Task<VehicleReport> Report(HttpClient client, Guid vehicle, DateOnly today) =>
        (await client.GetFromJsonAsync<VehicleReport>($"/setup/vehicles/{vehicle}/report?from={Day(today.AddDays(-30))}&through={Day(today)}"))!;

    private static async Task<List<HistoryEntry>> Log(HttpClient client) =>
        [.. (await client.GetFromJsonAsync<HistoryPage>("/setup/history?section=centralexpenses&pageSize=100"))!.Items];

    private static Task<ExpenseRecorded> Recorded(HttpResponseMessage response) => Read<ExpenseRecorded>(response);

    private static Task<ExpenseSaved> Saved(HttpResponseMessage response) => Read<ExpenseSaved>(response);

    private static async Task<T> Read<T>(HttpResponseMessage response)
    {
        using (response)
        {
            if (!response.IsSuccessStatusCode)
                Assert.Fail($"{(int)response.StatusCode}: {await response.Content.ReadAsStringAsync()}");
            return (await response.Content.ReadFromJsonAsync<T>())!;
        }
    }

    private static async Task AssertBadRequest(HttpResponseMessage response, string detail)
    {
        using (response)
        {
            Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
            Assert.Equal(detail, (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString());
        }
    }

    private static async Task AssertForbidden(HttpResponseMessage response, string detail)
    {
        using (response)
        {
            Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
            Assert.Equal(detail, (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString());
        }
    }

    public void Dispose() => app.Dispose();
}

// The rules of a purchase and a row, with no database.
public sealed class CentralExpenseDomainTests
{
    private static readonly DateOnly Date = new(2026, 10, 8);
    private static readonly DateTimeOffset Now = new(2026, 10, 8, 9, 0, 0, TimeSpan.Zero);
    private static readonly Guid Organization = Guid.NewGuid();
    private static readonly Guid Actor = Guid.NewGuid();
    private static readonly Guid Item = Guid.NewGuid();

    private static CentralPurchase Purchase(decimal units, decimal unitAmount, params decimal[] amounts) =>
        new(Date, Item, units, unitAmount, null, [.. amounts.Select(a => new ExpenseAllocationLine(Guid.NewGuid(), a))]);

    [Fact]
    public void OneVehicleTakesThePurchaseAsBoughtAndKeepsItsId()
    {
        var group = Guid.NewGuid();
        var row = Assert.Single(CentralExpense.Record(group, Organization, Purchase(4, 4200m, 16800m), Now, Actor));
        Assert.Equal((group, group, 1, 4m, 4200m, 16800m), (row.Id, row.GroupId, row.GroupSize, row.Units, row.UnitAmount, row.Total));
        Assert.Equal((16800m, 4m, 4200m, 1L), (row.GroupTotal, row.GroupUnits, row.GroupUnitAmount, row.Version));
        Assert.Equal((Actor, Now), (row.RecordedBy, row.RecordedAt));
    }

    [Fact]
    public void AnEvenSplitKeepsTheUnitCostOnlyWhileUnitsDivideIntoThreeDecimals()
    {
        Assert.Equal((2m, 2800m, 5600m), Rows(Purchase(6, 2800m, 5600m, 5600m, 5600m)).Select(r => (r.Units, r.UnitAmount, r.Total)).Distinct().Single());
        Assert.Equal((0.25m, 40m, 10m), Rows(Purchase(1, 40m, 10m, 10m, 10m, 10m)).Select(r => (r.Units, r.UnitAmount, r.Total)).Distinct().Single());
        // A refund splits the same way.
        Assert.Equal((2m, -50m, -100m), Rows(Purchase(6, -50m, -100m, -100m, -100m)).Select(r => (r.Units, r.UnitAmount, r.Total)).Distinct().Single());
        // A third of a unit is not a quantity.
        Assert.Equal((1m, 30m, 30m), Rows(Purchase(1, 90m, 30m, 30m, 30m)).Select(r => (r.Units, r.UnitAmount, r.Total)).Distinct().Single());
    }

    [Fact]
    public void AnUnevenSplitStoresOneUnitAtEachAmountAndTheRowsAddUpToTheTotal()
    {
        var rows = Rows(Purchase(1, 100m, 33.34m, 33.33m, 33.33m));
        Assert.Equal([(1m, 33.34m), (1m, 33.33m), (1m, 33.33m)], rows.Select(r => (r.Units, r.UnitAmount)));
        Assert.Equal(100m, rows.Sum(r => r.Total));
        Assert.Equal(3, rows.Select(r => r.Id).Distinct().Count());
        Assert.Single(rows.Select(r => r.GroupId).Distinct());
        Assert.All(rows, r => Assert.Equal((3, 100m, 1m, 100m), (r.GroupSize, r.GroupTotal, r.GroupUnits, r.GroupUnitAmount)));

        var unevenUnits = Rows(Purchase(10, 100m, 400m, 600m));
        Assert.Equal([(1m, 400m), (1m, 600m)], unevenUnits.Select(r => (r.Units, r.UnitAmount)));
    }

    [Fact]
    public void ThePurchaseIsCheckedBeforeAnyRowIsMade()
    {
        Assert.Throws<ArgumentException>(() => Rows(Purchase(1, 100m, 60m, 60m)));
        Assert.Throws<ArgumentException>(() => Rows(Purchase(1, 100m, 150m, -50m)));
        Assert.Throws<ArgumentException>(() => Rows(Purchase(1, 100m)));
        Assert.Throws<ArgumentException>(() => Rows(Purchase(1, 100m, [.. Enumerable.Repeat(1m, 101).Take(51)])));
        var vehicle = Guid.NewGuid();
        Assert.Throws<ArgumentException>(() => CentralExpense.Record(null, Organization,
            new(Date, Item, 1, 100m, null, [new(vehicle, 50m), new(vehicle, 50m)]), Now, Actor));
        Assert.Throws<ArgumentException>(() => CentralExpense.Record(null, Organization, Purchase(1, 100m, 100m), Now.ToOffset(TimeSpan.FromHours(3)), Actor));
        Assert.Throws<ArgumentException>(() => CentralExpense.Record(null, Guid.Empty, Purchase(1, 100m, 100m), Now, Actor));
    }

    [Fact]
    public void EveryChangeAndRemovalBumpsTheVersionAndTheItemUnitsOrPriceLeaveTheGroup()
    {
        var rows = Rows(Purchase(6, 2800m, 5600m, 5600m, 5600m));
        var (row, other, third) = (rows[0], rows[1], rows[2]);
        CentralExpenseLine Line(CentralExpense of, Guid? item = null, decimal? units = null, decimal? price = null, string? note = null, DateOnly? date = null, Guid? vehicle = null) =>
            new(date ?? of.Date, vehicle ?? of.VehicleId, item ?? of.ExpenseItemId, units ?? of.Units, price ?? of.UnitAmount, note ?? of.Note);

        Assert.True(row.Matches(Line(row)));
        row.Change(Line(row, note: "Spare"), Now.AddMinutes(1), Actor);
        Assert.Equal((2L, 3, 16800m, "Spare"), (row.Version, row.GroupSize, row.GroupTotal, row.Note));
        row.Change(Line(row, date: Date.AddDays(-1), vehicle: Guid.NewGuid()), Now.AddMinutes(2), Actor);
        Assert.Equal((3L, 3), (row.Version, row.GroupSize));

        other.Change(Line(other, price: 3000m), Now.AddMinutes(1), Actor);
        Assert.Equal((2L, 1, 6000m, 2m, 3000m, 6000m), (other.Version, other.GroupSize, other.GroupTotal, other.GroupUnits, other.GroupUnitAmount, other.Total));
        third.Change(Line(third, units: 1m), Now.AddMinutes(1), Actor);
        Assert.Equal((1, 2800m, 1m), (third.GroupSize, third.GroupTotal, third.GroupUnits));
        third.Change(Line(third, item: Guid.NewGuid()), Now.AddMinutes(2), Actor);
        Assert.Equal((3L, 1), (third.Version, third.GroupSize));
        Assert.Equal(rows[0].GroupId, third.GroupId);

        row.Remove("Recorded twice", Now.AddMinutes(3), Actor);
        Assert.Equal((4L, true, "Recorded twice"), (row.Version, row.Removed, row.RemovalReason));
        Assert.Throws<InvalidOperationException>(() => row.Change(Line(row, note: "Again"), Now.AddMinutes(4), Actor));
        Assert.Throws<InvalidOperationException>(() => row.Remove("Again", Now.AddMinutes(4), Actor));
        Assert.Throws<ArgumentException>(() => other.Remove(" ", Now, Actor));
        Assert.Throws<ArgumentException>(() => other.Change(Line(other, price: 0m), Now, Actor));
        Assert.Throws<ArgumentException>(() => other.Change(Line(other, note: "x"), Now.ToOffset(TimeSpan.FromHours(3)), Actor));
    }

    private static IReadOnlyList<CentralExpense> Rows(CentralPurchase purchase) =>
        CentralExpense.Record(null, Organization, purchase, Now, Actor);
}
