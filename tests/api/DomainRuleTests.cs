using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Xunit;

namespace Auth.Tests;

public sealed class DomainRuleTests
{
    private static readonly DateOnly Today = new(2026, 9, 26); // a Saturday
    private static readonly Guid Organization = Guid.NewGuid();
    private static readonly Guid Vehicle = Guid.NewGuid();

    [Theory]
    [InlineData("0712345678", "+254712345678")]
    [InlineData("0112345678", "+254112345678")]
    [InlineData("254712345678", "+254712345678")]
    [InlineData("+254712345678", "+254712345678")]
    [InlineData("+254 712 345 678", "+254712345678")]
    [InlineData("0712-345-678", "+254712345678")]
    [InlineData("(0712) 345678", "+254712345678")]
    [InlineData("0812345678", "")]
    [InlineData("+25471234567", "")]
    [InlineData("", "")]
    public void PhoneNumbersNormalizeToTheFullKenyanPrefix(string input, string expected) =>
        Assert.Equal(expected, PhoneNumber.Normalize(input));

    [Fact]
    public void PermissionDependenciesAreTransitiveAndDenyingARequiredPermissionRemovesDependents()
    {
        var resolver = new EffectivePermissionResolver();
        var permission = resolver.Resolve(["dash.capture"], Array.Empty<PersonPermissionOverride>());

        Assert.Contains("dash.capture", permission);
        Assert.Contains("revenue.capture", permission);
        Assert.Contains("revenue.view", permission);

        var denied = resolver.Resolve(["dash.capture"],
            [new PersonPermissionOverride { Permission = "revenue.view", Granted = false }]);

        Assert.DoesNotContain("dash.capture", denied);
        Assert.DoesNotContain("revenue.capture", denied);
        Assert.DoesNotContain("revenue.view", denied);
    }

    [Fact]
    public void SecurityPolicyRequiresThreeAttemptsAndCapsPauseAtOneHour()
    {
        var policy = new OrganizationSecurityPolicy { LockoutThreshold = 2 };
        Assert.Throws<ArgumentException>(() => policy.Validate());

        policy.LockoutThreshold = 3;
        policy.LockoutMinutes = 61;
        Assert.Throws<ArgumentException>(() => policy.Validate());

        policy.LockoutMinutes = 60;
        policy.Validate();
    }

    private static RecurringDefinition Daily(DateOnly start, decimal amount = 100m) =>
        new("Insurance", RecurringKind.Cost, CostCategory.FixedCommitments, amount, new RecurringSchedule(RecurrenceFrequency.Daily), start, null, [new VehicleShare(Vehicle, amount)]);

    [Fact]
    public void PostponingAPendingItemStopsTheOldScheduleAndKeepsItEditable()
    {
        var item = new RecurringItem(Organization, Daily(Today.AddDays(5)));
        item.Revise(Daily(Today.AddDays(10)), Today);

        Assert.Null(item.DueOn(Today.AddDays(5)));
        Assert.Null(item.DueOn(Today.AddDays(9)));
        Assert.NotNull(item.DueOn(Today.AddDays(10)));

        // The original start has passed but the postponed one has not: the item is still pending.
        item.Revise(Daily(Today.AddDays(10), 250m), Today.AddDays(6));
        Assert.Equal(250m, item.DueOn(Today.AddDays(10))!.Amount);
    }

    [Fact]
    public void BackdatingAPendingItemPostsFromTheEarlierStart()
    {
        var item = new RecurringItem(Organization, Daily(Today.AddDays(5)));
        item.Revise(Daily(Today.AddDays(-3)), Today);

        Assert.NotNull(item.DueOn(Today.AddDays(-3)));
        Assert.NotNull(item.DueOn(Today.AddDays(5)));
    }

    [Fact]
    public void ARunningItemKeepsItsStartDate()
    {
        var item = new RecurringItem(Organization, Daily(Today.AddDays(-5)));
        Assert.Throws<ArgumentException>(() => item.Revise(Daily(Today.AddDays(2)), Today));

        item.Revise(Daily(Today.AddDays(-5), 300m), Today);
        Assert.Equal(100m, item.DueOn(Today.AddDays(-1))!.Amount);
        Assert.Equal(300m, item.DueOn(Today)!.Amount);
    }

    [Fact]
    public void MovingTheJoinDateEarlierBackfillsTheTargetThatAppliedAtTheOldJoinDate()
    {
        var company = Guid.NewGuid();
        var vehicle = new FleetVehicle(Organization, company, new VehicleRegistration("KDA 482M"), Today.AddDays(-10), 7000m);
        vehicle.Update(company, Today.AddDays(-10), 9000m, Today.AddDays(-5));

        Assert.True(vehicle.Update(company, Today.AddDays(-20), 9000m, Today));

        Assert.Equal(7000m, vehicle.TargetOn(Today.AddDays(-20)));
        Assert.Equal(7000m, vehicle.TargetOn(Today.AddDays(-7)));
        Assert.Equal(9000m, vehicle.TargetOn(Today));
    }

    [Theory]
    [InlineData("week", 1, "2026-09-21")]
    [InlineData("week", 0, "2026-09-20")]
    [InlineData("week", 6, "2026-09-26")]
    [InlineData("month", 1, "2026-09-01")]
    public void ReportPeriodsRunFromTheStartOfTheCurrentWeekOrMonthToToday(string period, int firstDayOfWeek, string from)
    {
        var range = ReportPeriod.Current(period, Today, firstDayOfWeek);
        Assert.Equal(DateOnly.Parse(from), range.From);
        Assert.Equal(Today, range.Through);
    }
}
