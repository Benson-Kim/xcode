using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application.PettyCash;
using Auth.Application.Setup;
using Microsoft.EntityFrameworkCore;
using Xunit;
using static Auth.Tests.RevenueTestData;

namespace Auth.Tests;

public sealed class PettyCashTests : IDisposable
{
    private const string BumpChangeLog = "UPDATE \"Organizations\" SET \"SettingsVersion\" = \"SettingsVersion\" + 1";
    private readonly AuthFactory app = new();

    private sealed record World(DateOnly Today, Guid Vehicle, Guid Outside, Guid Item, Guid Clerk, Guid Admin, Guid Owner);

    // The clerk keeps a float and works one company; the office admin approves up to 5,000; the owner may do anything.
    // Each person signs in once per test: a new device code cannot be sent again within a minute.
    private async Task<(World W, HttpClient Owner)> Arrange()
    {
        await app.SeedDemo();
        var today = PinnedThursday(app);
        await SetBusinessDate(app, today);
        var company = await Company(app, "Petty Fleet");
        var other = await Company(app, "Other Fleet");
        var vehicle = await Vehicle(app, company, "KAA 501A", today.AddDays(-30));
        var outside = await Vehicle(app, other, "KAB 502B", today.AddDays(-30));
        await ScopeToCompany(app, Clerk, company);
        await Grant(app, Clerk, "pettycash.spend");
        await Grant(app, Admin, "pettycash.approve_item");
        await SetLimit(Admin, 5000m);
        var owner = await app.SignIn(Owner);
        var item = await ExpenseItemTestData.Id(owner, "Tyres");
        Guid clerk = default, admin = default, ownerId = default;
        await app.WithDb(async db =>
        {
            clerk = (await db.Users.SingleAsync(x => x.Email == Clerk)).Id;
            admin = (await db.Users.SingleAsync(x => x.Email == Admin)).Id;
            ownerId = (await db.Users.SingleAsync(x => x.Email == Owner)).Id;
        });
        return (new(today, vehicle, outside, item, clerk, admin, ownerId), owner);
    }

    [Fact]
    public async Task RecordingSpendingWaitsForApprovalAndShowsOnTheFloat()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);

        Assert.Equal(10000m, (await Saved(await Post(owner, Cash(w.Today, w.Clerk, 10000m)))).Balance);
        var spent = await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 1500m, units: 2, note: "Two tyres")));
        Assert.Equal(("waiting", 7000m), (spent.Status, spent.Balance));

        var overview = await Overview(clerk, w.Today);
        Assert.Equal(("day", w.Today, w.Today), (overview.Period, overview.From, overview.To));
        Assert.Equal(new PettyCashFiguresDto(0m, 10000m, 3000m, 0m, 3000m, 7000m), overview.Figures);
        var mine = Assert.Single(overview.Floats);
        Assert.Equal((w.Clerk, 10000m, 3000m, 3000m, 1, 7000m, (DateOnly?)w.Today),
            (mine.HolderId, mine.CashReceived, mine.Expenses, mine.Waiting, mine.WaitingCount, mine.Balance, mine.LastCashOn));
        Assert.Equal((w.Clerk, true, false, false), (overview.Permissions.HolderId, overview.Permissions.CanSpend,
            overview.Permissions.CanIssue, overview.Permissions.CanApproveItem));

        // The day before had nothing yet; the float itself is always to date.
        var dayBefore = await Overview(owner, w.Today.AddDays(-1), w.Clerk);
        Assert.Equal((0m, 0m, 7000m), (dayBefore.Figures.OpeningBalance, dayBefore.Figures.ClosingBalance, dayBefore.Floats.Single().Balance));

        var entries = await Entries(clerk, $"from={w.Today:yyyy-MM-dd}&to={w.Today:yyyy-MM-dd}");
        Assert.Equal(2, entries.Total);
        var expense = entries.Items.Single(x => x.Kind == "expense");
        Assert.Equal(("KAA 501A", "Tyres", 2m, 1500m, 3000m, "waiting", "Two tyres"),
            (expense.Registration, expense.ExpenseItemName, expense.Units, expense.UnitAmount, expense.Total, expense.Status, expense.Note));
        Assert.Equal((true, true, false), (expense.CanEdit, expense.CanRemove, expense.CanReview));
        var cash = entries.Items.Single(x => x.Kind == "cash");
        Assert.Equal((null, false, false), (cash.Status, cash.CanEdit, cash.CanRemove));
    }

    // A manager may pay from their own pocket before cash reaches them; only taking cash back is held at zero.
    [Fact]
    public async Task SpendingMayTakeAFloatBelowZeroButTakingCashBackNeedsPermission()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);

        var spent = await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 3000m)));
        Assert.Equal(("waiting", -3000m), (spent.Status, spent.Balance));
        Assert.Equal(-3500m, (await Saved(await Post(clerk, Credit(w.Today, 500m, "Kamau Motors", "Paid for parts")))).Balance);
        var overview = await Overview(clerk, w.Today);
        Assert.Equal((0m, 3500m, -3500m), (overview.Figures.OpeningBalance, overview.Figures.MoneyOut, overview.Figures.ClosingBalance));
        Assert.Equal(-3500m, overview.Floats.Single().Balance);
        // Changing spending deeper below zero is not refused either.
        Assert.Equal(-4500m, (await Saved(await clerk.PutAsJsonAsync($"/setup/pettycash/entries/{spent.Id}",
            Expense(w.Today, w.Vehicle, w.Item, 4000m, version: spent.Version)))).Balance);
        Assert.Equal(-4300m, (await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, -200m)))).Balance);

        // The owner may take cash back below zero; without that permission it is refused, while giving cash never is.
        Assert.Equal(-4800m, (await Saved(await Post(owner, Cash(w.Today, w.Clerk, -500m)))).Balance);
        await Deny(app, Owner, "pettycash.issue_negative");
        using var refused = await Post(owner, Cash(w.Today, w.Clerk, -100m));
        Assert.Equal(HttpStatusCode.BadRequest, refused.StatusCode);
        var problem = await refused.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("This takes the float below zero, which needs the permission \"Send money that takes a float below zero\".",
            problem.GetProperty("detail").GetString());
        Assert.Equal(-4900m, problem.GetProperty("balanceAfter").GetDecimal());
        Assert.Equal(-3800m, (await Saved(await Post(owner, Cash(w.Today, w.Clerk, 1000m)))).Balance);
    }

    [Fact]
    public async Task UnitsCanBePartOfOneAndAboveAThousand()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);

        var fuel = await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 182.40m, units: 11.875m, note: "Fuel")));
        await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 1250.50m, units: 4.5m, note: "Oil")));
        await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 10m, units: 1001m, note: "Washers")));
        var lines = (await Entries(clerk, "kind=expense")).Items.ToDictionary(x => x.Note!, x => (x.Units, x.Total));
        Assert.Equal((11.875m, 2166.00m), lines["Fuel"]);
        Assert.Equal((4.5m, 5627.25m), lines["Oil"]);
        Assert.Equal((1001m, 10010m), lines["Washers"]);

        // Saving the same units again is a replay, not a change.
        var again = await Saved(await clerk.PutAsJsonAsync($"/setup/pettycash/entries/{fuel.Id}",
            Expense(w.Today, w.Vehicle, w.Item, 182.40m, units: 11.875m, version: fuel.Version, note: "Fuel")));
        Assert.Equal(fuel.Version, again.Version);

        const string units = "Units must be above zero, with at most three decimals.";
        await AssertBadRequest(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 100m, units: 0m)), units);
        await AssertBadRequest(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 100m, units: -2m)), units);
        await AssertBadRequest(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 100m, units: 1.2345m)), units);
        await AssertBadRequest(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 0.01m, units: 0.001m)),
            "The total rounds to zero. Check the units and the amount.");
        await AssertBadRequest(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 10000m, units: 999999999.999m)), "The total is too large.");
        await AssertBadRequest(await Post(owner, new { kind = "cash", date = w.Today, holderId = w.Clerk, units = 2m, unitAmount = 100m }),
            "Only an expense has units.");
    }

    // A week runs from the organization's first day of the week, like revenue weeks.
    [Fact]
    public async Task AWeekShowsItsFiguresFromTheOrganizationsFirstDay()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);
        var monday = w.Today.AddDays(-3);
        await Saved(await Post(owner, Cash(monday.AddDays(-2), w.Clerk, 10000m)));
        await Saved(await Post(clerk, Expense(monday, w.Vehicle, w.Item, 1000m)));
        await Saved(await Post(owner, Cash(w.Today.AddDays(-1), w.Clerk, 2000m)));
        await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 500m)));

        var week = await Overview(clerk, w.Today, period: "week");
        Assert.Equal(("week", w.Today, monday, monday.AddDays(6)), (week.Period, week.Date, week.From, week.To));
        Assert.Equal(new PettyCashFiguresDto(10000m, 2000m, 1500m, 0m, 1500m, 10500m), week.Figures);
        Assert.Equal(10500m, week.Floats.Single().Balance);
        // A day inside the week asks for the same week.
        Assert.Equal(monday, (await Overview(clerk, monday.AddDays(1), period: "week")).From);

        await SetFirstDayOfWeek(app, DayOfWeek.Saturday);
        var fromSaturday = await Overview(clerk, w.Today, period: "week");
        Assert.Equal((monday.AddDays(-2), monday.AddDays(4)), (fromSaturday.From, fromSaturday.To));
        Assert.Equal(new PettyCashFiguresDto(0m, 12000m, 1500m, 0m, 1500m, 10500m), fromSaturday.Figures);

        await AssertBadRequest(await clerk.GetAsync($"/setup/pettycash/overview?period=month"), "Choose a day or a week.");
    }

    [Fact]
    public async Task SpendingIsOnlyOnYourOwnFloatAndForYourOwnVehicles()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);
        await Saved(await Post(owner, Cash(w.Today, w.Clerk, 10000m)));

        await AssertBadRequest(await Post(clerk, Expense(w.Today, w.Outside, w.Item, 100m)), "Choose one of your vehicles.");
        await AssertBadRequest(await Post(clerk, new { kind = "expense", date = w.Today, holderId = w.Owner, vehicleId = w.Vehicle,
            expenseItemId = w.Item, unitAmount = 100m }), "Spending is recorded on your own float.");
        await AssertBadRequest(await Post(clerk, Expense(w.Today.AddDays(1), w.Vehicle, w.Item, 100m)), "Petty cash cannot be recorded for a future date.");
        await AssertBadRequest(await Post(clerk, Expense(w.Today.AddDays(-40), w.Vehicle, w.Item, 100m)), "The vehicle was not in the fleet on that day.");
        await AssertBadRequest(await Post(clerk, new { kind = "expense", date = w.Today, itemId = w.Item, unitAmount = 100m }), "Choose the vehicle.");
        await AssertBadRequest(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 0m)), "Enter an amount other than zero.");
        await AssertBadRequest(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 10.005m)), "Enter the amount with at most two decimals.");
        await AssertForbidden(await Post(clerk, Cash(w.Today, w.Clerk, 100m)),
            "Giving cash to a float needs the permission \"Record money sent to a float\".");
    }

    [Fact]
    public async Task ApprovedSpendingReachesTheVehicleAndCreditNotesNever()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);
        using var admin = await app.SignIn(Admin);
        await Saved(await Post(owner, Cash(w.Today, w.Clerk, 10000m)));
        var spent = await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 1200m)));
        await Saved(await Post(clerk, Credit(w.Today, 800m, "Grace Wanjiku", "Advance for towing")));

        var before = await Report(owner, w.Vehicle, w.Today);
        Assert.DoesNotContain(before.Postings, p => p.Source == "pettycash");

        var approved = await Saved(await admin.PostAsJsonAsync($"/setup/pettycash/entries/{spent.Id}/approve", new { version = spent.Version }));
        Assert.Equal("approved", approved.Status);
        var after = await Report(owner, w.Vehicle, w.Today);
        var posting = Assert.Single(after.Postings, p => p.Source == "pettycash");
        Assert.Equal((spent.Id, w.Today, "Tyres", 1200m), (posting.ItemId, posting.Date, posting.Name, posting.Amount));
        Assert.Equal(before.MoneyOut + 1200m, after.MoneyOut);

        var row = (await Entries(clerk, "kind=expense")).Items.Single();
        Assert.Equal(("approved", "Peter Otieno", false, false), (row.Status, row.ReviewedByName, row.CanEdit, row.CanRemove));
    }

    [Fact]
    public async Task NobodyReviewsTheirOwnFloatTheirOwnEntryOrAboveTheirLimit()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);
        using var admin = await app.SignIn(Admin);
        await Saved(await Post(owner, Cash(w.Today, w.Clerk, 10000m)));

        var own = await Saved(await Post(owner, Expense(w.Today, w.Vehicle, w.Item, 100m)));
        await AssertForbidden(await Approve(owner, own), "You cannot approve or send back entries on your own float.");

        var issued = await Saved(await Post(owner, Credit(w.Today, 300m, "Kamau Motors", "Paid for the clerk", holder: w.Clerk)));
        await AssertForbidden(await Approve(owner, issued), "You cannot approve or send back an entry you recorded.");

        var large = await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 6000m)));
        var row = (await Entries(admin, $"holderId={w.Clerk}&kind=expense")).Items.Single();
        Assert.Equal((true, false), (row.AboveLimit, row.CanReview));
        await AssertForbidden(await Approve(admin, large), "This entry is above your approval limit.");
        Assert.Equal("approved", (await Saved(await Approve(owner, large))).Status);

        // Cash is never reviewed.
        var cash = (await Entries(owner, $"holderId={w.Clerk}&kind=cash")).Items.Single();
        await AssertBadRequest(await owner.PostAsJsonAsync($"/setup/pettycash/entries/{cash.Id}/approve", new { version = cash.Version }),
            "Cash given is not approved.");
    }

    [Fact]
    public async Task SendingBackNeedsACommentAndSavingAgainSendsItForApproval()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);
        using var admin = await app.SignIn(Admin);
        await Saved(await Post(owner, Cash(w.Today, w.Clerk, 10000m)));
        var spent = await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 1200m)));

        await AssertBadRequest(await admin.PostAsJsonAsync($"/setup/pettycash/entries/{spent.Id}/send-back", new { version = spent.Version, comment = " " }),
            "Say what should be fixed.");
        var sent = await Saved(await admin.PostAsJsonAsync($"/setup/pettycash/entries/{spent.Id}/send-back",
            new { version = spent.Version, comment = "Attach the receipt" }));
        Assert.Equal("sentBack", sent.Status);
        var row = (await Entries(clerk, "")).Items.Single(x => x.Kind == "expense");
        Assert.Equal(("sentBack", "Attach the receipt", true), (row.Status, row.SentBackNote, row.CanEdit));

        var again = await Saved(await clerk.PutAsJsonAsync($"/setup/pettycash/entries/{spent.Id}",
            Expense(w.Today, w.Vehicle, w.Item, 1200m, version: sent.Version)));
        Assert.Equal("waiting", again.Status);
        var resubmitted = (await Entries(clerk, "")).Items.Single(x => x.Kind == "expense");
        Assert.Equal(("waiting", (string?)null), (resubmitted.Status, resubmitted.SentBackNote));
    }

    [Fact]
    public async Task AnApprovedEntryIsChangedOnlyBySomeoneElseWhoApproves()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);
        using var admin = await app.SignIn(Admin);
        await Saved(await Post(owner, Cash(w.Today, w.Clerk, 10000m)));
        var spent = await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 1200m)));
        var approved = await Saved(await Approve(admin, spent));

        await AssertForbidden(await clerk.PutAsJsonAsync($"/setup/pettycash/entries/{spent.Id}",
                Expense(w.Today, w.Vehicle, w.Item, 1300m, version: approved.Version)),
            "An approved entry can only be changed by someone else who approves petty cash.");
        await AssertForbidden(await clerk.PostAsJsonAsync($"/setup/pettycash/entries/{spent.Id}/remove", new { version = approved.Version, reason = "Wrong" }),
            "An approved entry can only be changed by someone else who approves petty cash.");

        var corrected = await Saved(await admin.PutAsJsonAsync($"/setup/pettycash/entries/{spent.Id}",
            Expense(w.Today, w.Vehicle, w.Item, 1300m, version: approved.Version)));
        Assert.Equal(("waiting", 8700m), (corrected.Status, corrected.Balance));
        Assert.True(corrected.Version > approved.Version);
    }

    [Fact]
    public async Task AStaleVersionConflictsWithTheCurrentEntry()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);
        await Saved(await Post(owner, Cash(w.Today, w.Clerk, 10000m)));
        var spent = await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 1200m)));
        await Saved(await clerk.PutAsJsonAsync($"/setup/pettycash/entries/{spent.Id}", Expense(w.Today, w.Vehicle, w.Item, 1250m, version: spent.Version)));

        using var stale = await clerk.PutAsJsonAsync($"/setup/pettycash/entries/{spent.Id}", Expense(w.Today, w.Vehicle, w.Item, 1300m, version: spent.Version));
        Assert.Equal(HttpStatusCode.Conflict, stale.StatusCode);
        var current = (await stale.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("current");
        Assert.Equal((1250m, spent.Version + 1), (current.GetProperty("unitAmount").GetDecimal(), current.GetProperty("version").GetInt64()));

        using var staleRemove = await clerk.PostAsJsonAsync($"/setup/pettycash/entries/{spent.Id}/remove", new { version = spent.Version, reason = "Typo" });
        Assert.Equal(HttpStatusCode.Conflict, staleRemove.StatusCode);
    }

    [Fact]
    public async Task ARetriedCreateAnswersWithTheEntryItMade()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);
        await Saved(await Post(owner, Cash(w.Today, w.Clerk, 10000m)));
        var id = Guid.NewGuid();

        var first = await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 1200m, id: id)));
        var retried = await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 1200m, id: id)));
        Assert.Equal((id, first.Version, 8800m), (retried.Id, retried.Version, retried.Balance));
        Assert.Equal(1, (await Entries(clerk, "kind=expense")).Total);

        // Someone else cannot take over an id that is in use.
        using var taken = await Post(owner, Cash(w.Today, w.Clerk, 50m, id: id));
        Assert.Equal(HttpStatusCode.Conflict, taken.StatusCode);
    }

    [Fact]
    public async Task RemovingNeedsAReasonAndTakesTheEntryOutOfTheTotals()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);
        await Saved(await Post(owner, Cash(w.Today, w.Clerk, 10000m)));
        var spent = await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 1200m)));

        await AssertBadRequest(await clerk.PostAsJsonAsync($"/setup/pettycash/entries/{spent.Id}/remove", new { version = spent.Version, reason = "" }),
            "A reason of 1–500 characters is required.");
        var removed = await Saved(await clerk.PostAsJsonAsync($"/setup/pettycash/entries/{spent.Id}/remove",
            new { version = spent.Version, reason = "Recorded twice" }));
        Assert.Equal(10000m, removed.Balance);
        Assert.Equal(0, (await Entries(clerk, "kind=expense")).Total);
        Assert.Equal(10000m, (await Overview(clerk, w.Today)).Floats.Single().Balance);
        Assert.Equal(HttpStatusCode.NotFound, (await clerk.PostAsJsonAsync($"/setup/pettycash/entries/{spent.Id}/remove",
            new { version = removed.Version, reason = "Again" })).StatusCode);

        var log = (await owner.GetFromJsonAsync<HistoryPage>("/setup/history?section=pettycash"))!.Items;
        Assert.Contains(log, x => x.Reason ==
            $"Removed Wanjiru Kamau's petty cash spending on KAA 501A for {w.Today.ToString("d MMM yyyy", CultureInfo.InvariantCulture)}. Reason: Recorded twice.");
        Assert.Contains(log, x => x.Reason == "Recorded petty cash given to Wanjiru Kamau");

        // Removing cash lowers the float, so the same rule applies.
        var cash = (await Entries(owner, $"holderId={w.Clerk}&kind=cash")).Items.Single();
        await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 100m)));
        await Deny(app, Owner, "pettycash.issue_negative");
        using var refused = await owner.PostAsJsonAsync($"/setup/pettycash/entries/{cash.Id}/remove", new { version = cash.Version, reason = "Wrong person" });
        Assert.Equal(HttpStatusCode.BadRequest, refused.StatusCode);
    }

    [Fact]
    public async Task CreditNotesNeedAPayeeAndAReasonAndBelongToNoVehicle()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);
        await Saved(await Post(owner, Cash(w.Today, w.Clerk, 10000m)));

        await AssertBadRequest(await Post(clerk, Credit(w.Today, 500m, null, "Advance")), "Say who was paid.");
        await AssertBadRequest(await Post(clerk, Credit(w.Today, 500m, "Grace Wanjiku", " ")), "Say why the money was paid.");
        await AssertBadRequest(await Post(clerk, new { kind = "credit", date = w.Today, vehicleId = w.Vehicle, payee = "Grace", note = "Advance", unitAmount = 500m }),
            "A credit note is not recorded against a vehicle.");

        var credit = await Saved(await Post(clerk, Credit(w.Today, 500m, "Grace Wanjiku", "Advance to be repaid", reimbursable: true)));
        Assert.Equal(("waiting", 9500m), (credit.Status, credit.Balance));
        var overview = await Overview(clerk, w.Today);
        Assert.Equal((500m, 0m, 500m, 9500m), (overview.Figures.CreditNotes, overview.Figures.Expenses, overview.Figures.MoneyOut,
            overview.Figures.ClosingBalance));
        var row = (await Entries(clerk, "kind=credit")).Items.Single();
        Assert.Equal(("Grace Wanjiku", "Advance to be repaid", true, (Guid?)null), (row.Payee, row.Note, row.Reimbursable, row.VehicleId));
        // The Expenses tab asks for expenses and credit notes together, and cash stays on its own tab.
        Assert.Equal(["credit"], (await Entries(clerk, "kind=expense,credit")).Items.Select(x => x.Kind));
        await AssertBadRequest(await clerk.GetAsync("/setup/pettycash/entries?kind=expense,bills"), "Choose an expense, a credit note or cash.");

        // The payee paying it back is a negative credit note.
        Assert.Equal(10000m, (await Saved(await Post(clerk, Credit(w.Today, -500m, "Grace Wanjiku", "Repaid the advance")))).Balance);
    }

    [Fact]
    public async Task AHolderSeesOnlyTheirOwnFloat()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);
        await Saved(await Post(owner, Cash(w.Today, w.Clerk, 10000m)));
        await Saved(await Post(owner, Expense(w.Today, w.Outside, w.Item, 100m)));

        var mine = await Overview(clerk, w.Today);
        Assert.Equal([w.Clerk], mine.Holders.Select(h => h.Id));
        Assert.Equal([w.Clerk], mine.Floats.Select(f => f.HolderId));
        Assert.Equal(HttpStatusCode.NotFound, (await clerk.GetAsync($"/setup/pettycash/overview?holderId={w.Owner}")).StatusCode);
        Assert.All((await Entries(clerk, "")).Items, x => Assert.Equal(w.Clerk, x.HolderId));

        var everyone = await Overview(owner, w.Today);
        Assert.Contains(everyone.Holders, h => h.Id == w.Clerk);
        Assert.Contains(everyone.Floats, f => f.HolderId == w.Owner && f.Balance == -100m);
        Assert.Equal(2, (await Entries(owner, "")).Total);

        // "View every float" still stops at the viewer's vehicles.
        await Grant(app, Admin, "pettycash.view_all");
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            var scope = await db.SetupDataScopes.IgnoreQueryFilters().SingleAsync(x => x.UserId == w.Admin);
            scope.AllCompanies = false;
            await db.SaveChangesAsync();
        });
        using var admin = await app.SignIn(Admin);
        Assert.Equal(["cash"], (await Entries(admin, "")).Items.Select(x => x.Kind));
    }

    [Fact]
    public async Task ApprovingADayApprovesWhatThePersonMayAndSkipsTheRest()
    {
        var (w, owner) = await Arrange();
        await Grant(app, Admin, "pettycash.approve_day");
        using var clerk = await app.SignIn(Clerk);
        using var admin = await app.SignIn(Admin);
        await Saved(await Post(owner, Cash(w.Today.AddDays(-1), w.Clerk, 20000m)));
        await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 1000m)));
        await Saved(await Post(clerk, Credit(w.Today, 400m, "Kamau Motors", "Paid for parts")));
        await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 6000m)));
        await Saved(await Post(clerk, Expense(w.Today.AddDays(-1), w.Vehicle, w.Item, 700m)));

        using var response = await admin.PostAsJsonAsync("/setup/pettycash/approve-day", new { date = w.Today });
        var result = (await response.Content.ReadFromJsonAsync<PettyCashDayApproved>())!;
        Assert.Equal(new PettyCashDayApproved(2, 1400m, 1), result);
        var statuses = (await Entries(clerk, "")).Items.Where(x => x.Kind != "cash").Select(x => (x.Date == w.Today, x.Total, x.Status)).ToList();
        Assert.Contains((true, 1000m, "approved"), statuses);
        Assert.Contains((true, 400m, "approved"), statuses);
        Assert.Contains((true, 6000m, "waiting"), statuses);
        Assert.Contains((false, 700m, "waiting"), statuses);

        await AssertForbidden(await clerk.PostAsJsonAsync("/setup/pettycash/approve-day", new { date = w.Today }), null);
    }

    [Fact]
    public async Task DashboardCardsFollowTheirPermissions()
    {
        var (w, owner) = await Arrange();
        using var clerk = await app.SignIn(Clerk);
        await Saved(await Post(owner, Cash(w.Today, w.Clerk, 10000m)));
        await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 1200m)));
        await Saved(await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 6000m)));

        Assert.Equal(HttpStatusCode.Forbidden, (await clerk.GetAsync("/setup/pettycash/dashboard")).StatusCode);
        await Grant(app, Clerk, "dash.float");
        var own = (await clerk.GetFromJsonAsync<PettyCashDashboardDto>("/setup/pettycash/dashboard"))!;
        Assert.Null(own.Approvals);
        Assert.Equal(new PettyCashDashboardFloat(2800m, 2, 7200m, 0, 0m), own.Float);

        await Grant(app, Admin, "dash.pettycash");
        using var admin = await app.SignIn(Admin);
        var queue = (await admin.GetFromJsonAsync<PettyCashDashboardDto>("/setup/pettycash/dashboard"))!;
        Assert.Null(queue.Float);
        Assert.Equal((2, 7200m, (decimal?)5000m, 1), (queue.Approvals!.Count, queue.Approvals.Total, queue.Approvals.ApprovalLimit, queue.Approvals.AboveLimit));
        Assert.Equal(new PettyCashDashboardHolder(w.Clerk, "Wanjiru Kamau", 2, 7200m, w.Today), Assert.Single(queue.Approvals.Holders));
    }

    [Fact]
    public async Task PeopleWithoutPettyCashAreRefused()
    {
        var (w, owner) = await Arrange();
        await Saved(await Post(owner, Cash(w.Today, w.Clerk, 100m)));
        await app.WithDb(async db =>
        {
            db.Provisioning = true;
            (await db.PermissionOverrides.IgnoreQueryFilters().SingleAsync(x => x.UserId == w.Clerk && x.Permission == "pettycash.spend")).Granted = false;
            await db.SaveChangesAsync();
        });
        using var clerk = await app.SignIn(Clerk);
        Assert.Equal(HttpStatusCode.Forbidden, (await clerk.GetAsync("/setup/pettycash/overview")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await clerk.GetAsync("/setup/pettycash/entries")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await Post(clerk, Expense(w.Today, w.Vehicle, w.Item, 100m))).StatusCode);

        // Someone who lost the permission keeps their float on the list until it is settled, but cannot be given cash.
        var holder = (await Overview(owner, w.Today)).Holders.Single(h => h.Id == w.Clerk);
        Assert.False(holder.Active);
        await AssertBadRequest(await Post(owner, Cash(w.Today, w.Clerk, 100m)), "Choose someone who keeps a petty cash float.");
    }

    // A save that collides on the change log runs again from fresh reads, so a float changed in between is checked
    // against what it holds now.
    [Fact]
    public async Task ARetryChecksTheFloatAgainstTheLatestBalance()
    {
        var (w, owner) = await Arrange();
        await Saved(await Post(owner, Cash(w.Today, w.Clerk, 5000m)));
        await Deny(app, Owner, "pettycash.issue_negative");

        app.Database.Reset();
        app.Database.Interleave("Organizations", BumpChangeLog);
        app.Database.BetweenAttempts("UPDATE \"PettyCashEntries\" SET \"UnitAmount\" = '1000.0', \"Total\" = '1000.0' WHERE \"Kind\" = 1");
        using var takenBack = await Post(owner, Cash(w.Today, w.Clerk, -3000m));

        Assert.Equal(2, app.Database.Transactions);
        Assert.Equal(HttpStatusCode.BadRequest, takenBack.StatusCode);
        Assert.Equal(-2000m, (await takenBack.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("balanceAfter").GetDecimal());
        Assert.Equal(1, (await Entries(owner, "kind=cash")).Total);
    }

    private Task SetLimit(string email, decimal? limit) => app.WithDb(async db =>
    {
        db.Provisioning = true;
        var user = await db.Users.SingleAsync(x => x.Email == email);
        (await db.Memberships.IgnoreQueryFilters().SingleAsync(x => x.UserId == user.Id)).ApprovalLimit = limit;
        await db.SaveChangesAsync();
    });

    private static object Expense(DateOnly date, Guid vehicle, Guid item, decimal amount, decimal units = 1, Guid? id = null, long? version = null,
        string? note = null) =>
        new { kind = "expense", date, vehicleId = vehicle, expenseItemId = item, units, unitAmount = amount, id, version, note };

    private static object Cash(DateOnly date, Guid holder, decimal amount, Guid? id = null) =>
        new { kind = "cash", date, holderId = holder, unitAmount = amount, id };

    private static object Credit(DateOnly date, decimal amount, string? payee, string? note, Guid? holder = null, bool reimbursable = false) =>
        new { kind = "credit", date, holderId = holder, unitAmount = amount, payee, note, reimbursable };

    private static Task<HttpResponseMessage> Post(HttpClient client, object body) => client.PostAsJsonAsync("/setup/pettycash/entries", body);

    private static Task<HttpResponseMessage> Approve(HttpClient client, PettyCashSaved saved) =>
        client.PostAsJsonAsync($"/setup/pettycash/entries/{saved.Id}/approve", new { version = saved.Version });

    private static async Task<PettyCashOverviewDto> Overview(HttpClient client, DateOnly date, Guid? holder = null, string? period = null) =>
        (await client.GetFromJsonAsync<PettyCashOverviewDto>($"/setup/pettycash/overview?date={date:yyyy-MM-dd}" +
            $"{(holder is null ? "" : $"&holderId={holder}")}{(period is null ? "" : $"&period={period}")}"))!;

    private static async Task<Page<PettyCashEntryDto>> Entries(HttpClient client, string query) =>
        (await client.GetFromJsonAsync<Page<PettyCashEntryDto>>($"/setup/pettycash/entries?{query}"))!;

    private static async Task<VehicleReport> Report(HttpClient client, Guid vehicle, DateOnly today) =>
        (await client.GetFromJsonAsync<VehicleReport>($"/setup/vehicles/{vehicle}/report?from={today.AddDays(-7):yyyy-MM-dd}&through={today:yyyy-MM-dd}"))!;

    private static async Task<PettyCashSaved> Saved(HttpResponseMessage response)
    {
        using (response)
        {
            if (!response.IsSuccessStatusCode)
                Assert.Fail($"{(int)response.StatusCode}: {await response.Content.ReadAsStringAsync()}");
            return (await response.Content.ReadFromJsonAsync<PettyCashSaved>())!;
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

    private static async Task AssertForbidden(HttpResponseMessage response, string? detail)
    {
        using (response)
        {
            Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
            if (detail is not null)
                Assert.Equal(detail, (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString());
        }
    }

    public void Dispose() => app.Dispose();
}
