using System.Data.Common;
using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Auth.Application;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Auth.Infrastructure;
using Auth.Infrastructure.Setup;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Xunit;

namespace Auth.Tests;

// Contract C3: expense categories, each counted as one bucket, hold the items people pick.
public sealed class ExpenseCatalogTests : IDisposable
{
    private readonly AuthFactory app = new();
    private const string Owner = "antony.maina@shamayah.co.ke";
    private const string RevenueClerk = "wanjiru.kamau@zurigenesis.co.ke";

    [Fact]
    public async Task CategoriesAndItemsAreNamedOnceIgnoringCaseAndEveryChangeIsLogged()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);

        var fuel = await Id(await owner.PostAsJsonAsync("/setup/expense-categories", new { name = " Road costs ", bucket = 2 }));
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync("/setup/expense-categories", new { name = "ROAD COSTS", bucket = 1 })).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync("/setup/expense-categories", new { name = "Other", bucket = 4 })).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync("/setup/expense-categories", new { name = "Other" })).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync("/setup/expense-categories", new { name = new string('x', 101), bucket = 1 })).StatusCode);

        var tolls = await Id(await owner.PostAsJsonAsync($"/setup/expense-categories/{fuel}/items", new { name = "Tolls" }));
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PostAsJsonAsync($"/setup/expense-categories/{fuel}/items", new { name = "tolls" })).StatusCode);
        // The same name may sit in another category.
        var charges = (await owner.GetFromJsonAsync<List<ExpenseItemOption>>("/setup/expense-items/options"))!.First(x => x.CategoryName == "Charges").CategoryId;
        await Id(await owner.PostAsJsonAsync($"/setup/expense-categories/{charges}/items", new { name = "Tolls" }));
        Assert.Equal(HttpStatusCode.NotFound, (await owner.PostAsJsonAsync($"/setup/expense-categories/{Guid.NewGuid()}/items", new { name = "Tolls" })).StatusCode);

        Assert.Equal(tolls, await Id(await owner.PutAsJsonAsync($"/setup/expense-items/{tolls}", new { name = "Road tolls" })));
        Assert.Equal(fuel, await Id(await owner.PutAsJsonAsync($"/setup/expense-categories/{fuel}", new { name = "Road costs", bucket = 1 })));
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.PutAsJsonAsync($"/setup/expense-categories/{fuel}", new { name = "charges", bucket = 1 })).StatusCode);

        var category = (await owner.GetFromJsonAsync<Page<ExpenseCategoryDto>>("/setup/expense-categories"))!.Items.Single(x => x.Id == fuel);
        Assert.Equal(("Road costs", ExpenseBucket.RepairsAndMaintenance, true), (category.Name, category.Bucket, category.Active));
        Assert.Equal("Road tolls", Assert.Single(category.Items).Name);

        var reasons = await Reasons(owner, "expenses");
        Assert.Contains("Added expense category Road costs", reasons);
        Assert.Contains("Added expense item Tolls under Road costs", reasons);
        Assert.Contains("Renamed expense item Tolls to Road tolls", reasons);
        Assert.Contains("Changed Road costs to count as repairs and maintenance", reasons);
    }

    [Fact]
    public async Task StoppedItemsAndItemsInStoppedCategoriesLeaveTheOptionsUntilRestored()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var options = (await owner.GetFromJsonAsync<List<ExpenseItemOption>>("/setup/expense-items/options"))!;
        var tyres = options.Single(x => x.Name == "Tyres");
        var loans = options.Single(x => x.Name == "Loan repayment").CategoryId;

        (await owner.PostAsJsonAsync($"/setup/expense-items/{tyres.Id}/stop", new { })).EnsureSuccessStatusCode();
        (await owner.PostAsJsonAsync($"/setup/expense-categories/{loans}/stop", new { })).EnsureSuccessStatusCode();
        // Stopping twice changes nothing and logs nothing more.
        (await owner.PostAsJsonAsync($"/setup/expense-categories/{loans}/stop", new { })).EnsureSuccessStatusCode();
        var remaining = (await owner.GetFromJsonAsync<List<ExpenseItemOption>>("/setup/expense-items/options"))!;
        Assert.Equal(11, remaining.Count);
        Assert.DoesNotContain(remaining, x => x.Id == tyres.Id || x.CategoryId == loans);

        var page = (await owner.GetFromJsonAsync<Page<ExpenseCategoryDto>>("/setup/expense-categories"))!.Items;
        var today = DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);
        Assert.Equal((false, today), (page.Single(x => x.Id == loans).Active, page.Single(x => x.Id == loans).StoppedOn!.Value));
        Assert.False(page.SelectMany(x => x.Items).Single(x => x.Id == tyres.Id).Active);
        Assert.Single(await Reasons(owner, "expenses"), "Turned off expense category Loans");

        (await owner.PostAsJsonAsync($"/setup/expense-items/{tyres.Id}/restore", new { })).EnsureSuccessStatusCode();
        (await owner.PostAsJsonAsync($"/setup/expense-categories/{loans}/restore", new { })).EnsureSuccessStatusCode();
        Assert.Equal(13, (await owner.GetFromJsonAsync<List<ExpenseItemOption>>("/setup/expense-items/options"))!.Count);
        Assert.Contains("Turned on expense item Tyres", await Reasons(owner, "expenses"));
    }

    [Fact]
    public async Task CategoriesArePagedByName()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var second = (await owner.GetFromJsonAsync<Page<ExpenseCategoryDto>>("/setup/expense-categories?page=2&pageSize=1"))!;
        Assert.Equal((3, "Garage and repairs"), (second.Total, Assert.Single(second.Items).Name));
        Assert.Equal(6, second.Items[0].Items.Count);
        Assert.Equal(HttpStatusCode.BadRequest, (await owner.GetAsync("/setup/expense-categories?pageSize=101")).StatusCode);
    }

    [Fact]
    public async Task ReadingNeedsExpenseOrScheduleAccessAndWritingNeedsExpenseSetup()
    {
        await app.SeedDemo();
        using var scheduler = await app.SignIn(RevenueClerk);
        Assert.Equal(HttpStatusCode.Forbidden, (await scheduler.GetAsync("/setup/expense-categories")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await scheduler.GetAsync("/setup/expense-items/options")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await scheduler.PostAsJsonAsync("/setup/expense-categories", new { name = "Road costs", bucket = 2 })).StatusCode);

        // Permissions are checked on every request, so the grant applies without signing in again.
        await Grant(RevenueClerk, "commitments.manage");
        Assert.Equal(13, (await scheduler.GetFromJsonAsync<List<ExpenseItemOption>>("/setup/expense-items/options"))!.Count);
        Assert.Equal(3, (await scheduler.GetFromJsonAsync<Page<ExpenseCategoryDto>>("/setup/expense-categories"))!.Total);
        var item = (await scheduler.GetFromJsonAsync<List<ExpenseItemOption>>("/setup/expense-items/options"))![0];
        Assert.Equal(HttpStatusCode.Forbidden, (await scheduler.PostAsJsonAsync("/setup/expense-categories", new { name = "Road costs", bucket = 2 })).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await scheduler.PutAsJsonAsync($"/setup/expense-items/{item.Id}", new { name = "Renamed" })).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await scheduler.PostAsJsonAsync($"/setup/expense-items/{item.Id}/stop", new { })).StatusCode);
    }

    [Fact]
    public async Task OptionsTakeOneQueryAndAPageOfCategoriesThreeHoweverLargeTheCatalog()
    {
        using var connection = new SqliteConnection("Data Source=:memory:");
        connection.Open();
        var counter = new CommandCounter();
        var options = new DbContextOptionsBuilder<AuthDb>().UseSqlite(connection).AddInterceptors(counter).Options;
        Guid organizationId;
        using (var seed = new AuthDb(options))
        {
            await seed.Database.EnsureCreatedAsync();
            await AuthFactory.AddOrganization(seed);
            await DemoSeed.Run(seed);
            organizationId = (await seed.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
        }
        var today = new DateOnly(2026, 9, 29);
        async Task<(int Commands, int Options, int Items)> Measure()
        {
            using var db = new AuthDb(options, new Tenant(organizationId));
            var repository = new SetupRepository(db, null!, null!, null!);
            counter.Count = 0;
            var picked = await repository.ExpenseItemOptions(today, CancellationToken.None);
            var optionCommands = counter.Count;
            counter.Count = 0;
            var page = await repository.ExpenseCategories(today, 1, 100, CancellationToken.None);
            Assert.Equal(3, counter.Count);
            return (optionCommands, picked.Count, page.Items.Sum(x => x.Items.Count));
        }

        Assert.Equal((1, 13, 13), await Measure());
        using (var grow = new AuthDb(options) { Provisioning = true })
        {
            for (var c = 0; c < 20; c++)
            {
                var category = new ExpenseCategory(organizationId, $"Category {c}", ExpenseBucket.RecurringCharges);
                grow.Add(category);
                for (var i = 0; i < 10; i++) grow.Add(new ExpenseItem(category, $"Item {i}"));
            }
            await grow.SaveChangesAsync();
        }
        Assert.Equal((1, 213, 213), await Measure());
    }

    private sealed class CommandCounter : DbCommandInterceptor
    {
        public int Count { get; set; }
        public override ValueTask<InterceptionResult<DbDataReader>> ReaderExecutingAsync(DbCommand command, CommandEventData eventData,
            InterceptionResult<DbDataReader> result, CancellationToken cancellationToken = default)
        {
            Count++;
            return base.ReaderExecutingAsync(command, eventData, result, cancellationToken);
        }
    }

    private sealed record Tenant(Guid OrganizationId) : IOrganizationContext
    {
        public Guid ActorId => Guid.Empty;
        public string CorrelationId => "";
    }

    private async Task Grant(string email, string permission) => await app.WithDb(async db =>
    {
        db.Provisioning = true;
        var user = await db.Users.SingleAsync(x => x.Email == email);
        var organizationId = (await db.Organizations.IgnoreQueryFilters().SingleAsync()).Id;
        db.PermissionOverrides.Add(new PersonPermissionOverride { OrganizationId = organizationId, UserId = user.Id, Permission = permission, Granted = true });
        await db.SaveChangesAsync();
    });

    private static async Task<List<string>> Reasons(HttpClient client, string section) =>
        (await client.GetFromJsonAsync<Page<HistoryEntry>>("/setup/history?pageSize=100"))!.Items
            .Where(x => x.Section == section).Select(x => x.Reason).ToList();

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
