using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Auth.Infrastructure;
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
    public void StoppingSomethingAlreadyStoppedOnAnotherDateIsRefusedAndRestoreCancelsIt()
    {
        var category = new ExpenseCategory(Organization, "Road costs", ExpenseBucket.RecurringCharges);
        var item = new ExpenseItem(category, "Tolls");
        Assert.True(category.Stop(Today));
        Assert.False(category.Stop(Today));
        Assert.Throws<ArgumentException>(() => category.Stop(Today.AddDays(-2)));
        Assert.True(category.Restore());
        Assert.True(item.Stop(Today));
        Assert.False(item.Stop(Today));
        Assert.Throws<ArgumentException>(() => item.Stop(Today.AddDays(1)));
        Assert.True(item.Restore());
        Assert.Null(item.StoppedOn);
    }

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

    // The bounds the database checks and sign-in clamps to are exactly the ones a save validates.
    [Fact]
    public void SecurityPolicyBoundsAgreeWithValidation()
    {
        Assert.Equal(8, SecurityPolicyBounds.All.Count);
        foreach (var bound in SecurityPolicyBounds.All)
        {
            var property = typeof(OrganizationSecurityPolicy).GetProperty(bound.Column)!;
            OrganizationSecurityPolicy With(int value) { var policy = new OrganizationSecurityPolicy(); property.SetValue(policy, value); return policy; }
            With(bound.Min).Validate();
            With(bound.Max).Validate();
            Assert.Throws<ArgumentException>(With(bound.Min - 1).Validate);
            Assert.Throws<ArgumentException>(With(bound.Max + 1).Validate);
            Assert.Equal(bound.Min, bound.Clamp(bound.Min - 1));
            Assert.Equal(bound.Max, bound.Clamp(int.MaxValue));
        }
    }

    // Addendum 1, section 2: at least three tries, and the pause is capped at one hour.
    [Theory]
    [InlineData(2, 15, false)]
    [InlineData(3, 15, true)]
    [InlineData(10, 15, true)]
    [InlineData(11, 15, false)]
    [InlineData(5, 0, false)]
    [InlineData(5, 1, true)]
    [InlineData(5, 60, true)]
    [InlineData(5, 61, false)]
    public void WrongPinPolicyBounds(int tries, int pauseMinutes, bool valid)
    {
        var policy = new OrganizationSecurityPolicy { LockoutThreshold = tries, LockoutMinutes = pauseMinutes };
        if (valid) policy.Validate();
        else Assert.Throws<ArgumentException>(policy.Validate);
    }

    private static RecurringDefinition Daily(DateOnly start, decimal amount = 100m) =>
        new("Insurance", RecurringKind.Cost, amount, new RecurringSchedule(RecurrenceFrequency.Daily), start, null, [new VehicleShare(Vehicle, amount)],
            Bucket: ExpenseBucket.RecurringCharges);

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
    public void BusinessDateCannotMoveIntoTheFutureAndCanFollowTheOrganizationClock()
    {
        var organization = new Organization { Slug = "fleet", Name = "Fleet" };
        Assert.True(organization.ChangeBusinessDate(Today.AddDays(-2), Today));
        Assert.Equal(Today.AddDays(-2), organization.BusinessDate);
        Assert.Throws<ArgumentException>(() => organization.ChangeBusinessDate(Today.AddDays(1), Today));
        Assert.True(organization.ChangeBusinessDate(null, Today));
        Assert.Null(organization.BusinessDate);
    }

    [Fact]
    public void LeavingTheFleetEndsTargetsUntilTheVehicleIsRestored()
    {
        var company = Guid.NewGuid();
        var vehicle = new FleetVehicle(Organization, company, new VehicleRegistration("KDA 482M"), Today.AddDays(-10), 7000m);

        Assert.True(vehicle.Retire(Today, Today));
        Assert.Equal(0m, vehicle.TargetOn(Today));
        Assert.False(vehicle.ActiveOn(Today));
        // Undone on its own date, the leave took effect for no day, so there is nothing to record as away.
        Assert.True(vehicle.Restore(Today, Today));
        Assert.Empty(vehicle.AwayPeriods);
        Assert.Equal(7000m, vehicle.TargetOn(Today));
        Assert.True(vehicle.ActiveOn(Today));
    }

    // The days between a leave that took effect and the return are recorded, so they are neither expected nor
    // missing once the vehicle is back.
    [Fact]
    public void AVehicleBackInTheFleetKeepsTheDaysItWasAwayOutOfEveryReport()
    {
        var company = Guid.NewGuid();
        var vehicle = new FleetVehicle(Organization, company, new VehicleRegistration("KDA 482M"), Today.AddDays(-30), 7000m);

        Assert.True(vehicle.Retire(Today.AddDays(-10), Today));
        Assert.True(vehicle.Restore(Today, Today));
        var away = Assert.Single(vehicle.AwayPeriods);
        Assert.Equal((Today.AddDays(-10), Today), (away.LeftOn, away.ReturnedOn));

        Assert.True(vehicle.ActiveOn(Today.AddDays(-11)));
        Assert.False(vehicle.ActiveOn(Today.AddDays(-10)));
        Assert.False(vehicle.ActiveOn(Today.AddDays(-1)));
        Assert.Equal(0m, vehicle.TargetOn(Today.AddDays(-5)));
        // Back in the fleet from the day it returned.
        Assert.True(vehicle.ActiveOn(Today));
        Assert.Equal(7000m, vehicle.TargetOn(Today));
    }

    [Fact]
    public void AReturnDateOutsideTheTimeAwayIsRefusedAndASecondLeaveCannotOverlapTheFirst()
    {
        var company = Guid.NewGuid();
        var vehicle = new FleetVehicle(Organization, company, new VehicleRegistration("KDA 482M"), Today.AddDays(-30), 7000m);
        Assert.True(vehicle.Retire(Today.AddDays(-10), Today));

        // Before the day it left, or after the business date, there is no stretch it could have been away for.
        Assert.Throws<ArgumentException>(() => vehicle.Restore(Today.AddDays(-11), Today));
        Assert.Throws<ArgumentException>(() => vehicle.Restore(Today.AddDays(1), Today));
        Assert.True(vehicle.Restore(Today.AddDays(-4), Today));

        // Leaving again inside the stretch it was already away would make the two read as one absence.
        Assert.Throws<ArgumentException>(() => vehicle.Retire(Today.AddDays(-6), Today));
        Assert.True(vehicle.Retire(Today.AddDays(-4), Today));
        Assert.True(vehicle.Restore(Today.AddDays(-2), Today));
        Assert.Equal(2, vehicle.AwayPeriods.Count);
        // Away for -10 through -5, back for -4 alone, then away again for -4 and -3.
        Assert.False(vehicle.ActiveOn(Today.AddDays(-5)));
        Assert.False(vehicle.ActiveOn(Today.AddDays(-4)));
        Assert.False(vehicle.ActiveOn(Today.AddDays(-3)));
        Assert.True(vehicle.ActiveOn(Today.AddDays(-2)));
    }

    [Fact]
    public void ACompanyCanBeArchivedAndRestoredWithoutDeletingItsIdentity()
    {
        var company = new PsvCompany(Organization, "North Star");
        Assert.True(company.Archive(Today));
        Assert.False(company.ActiveOn(Today));
        Assert.True(company.Restore());
        Assert.True(company.ActiveOn(Today));
        Assert.Equal("North Star", company.Name);
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

    // Each edit on the same day adds a revision, and the last one holds from that day.
    [Fact]
    public void TheLastTargetSetOnADayHoldsFromThatDay()
    {
        var company = Guid.NewGuid();
        var vehicle = new FleetVehicle(Organization, company, new VehicleRegistration("KDA 482M"), Today.AddDays(-10), 7000m);
        vehicle.Update(company, Today.AddDays(-10), 9000m, Today);
        vehicle.Update(company, Today.AddDays(-10), 8000m, Today);

        Assert.Equal(3, vehicle.Targets.Count);
        Assert.Equal(7000m, vehicle.TargetOn(Today.AddDays(-1)));
        Assert.Equal(8000m, vehicle.TargetOn(Today));
    }

    [Theory]
    [InlineData(0, true)]
    [InlineData(1, true)]
    [InlineData(2, true)]
    [InlineData(3, false)]
    [InlineData(6, false)]
    [InlineData(-1, false)]
    public void NumberDecimalsIsCappedAtTwo(int decimals, bool valid)
    {
        var localization = new OrganizationLocalization { NumberDecimals = decimals };
        if (valid) localization.Validate();
        else Assert.Throws<ArgumentException>(localization.Validate);
    }

    [Theory]
    [InlineData("0712345678", true)]
    [InlineData("+254712345678", true)]
    [InlineData("254712345678", true)]
    [InlineData("0112345678", true)]
    [InlineData("0812345678", false)]
    [InlineData("+25471234567", false)]
    [InlineData("", false)]
    [InlineData("not a number", false)]
    public void PhoneNumberTryCreateMirrorsNormalize(string input, bool valid)
    {
        Assert.Equal(valid, PhoneNumber.TryCreate(input, out var phone));
        if (valid) Assert.Equal(PhoneNumber.Normalize(input), phone.Value);
    }

    [Fact]
    public void UserBehaviorMethodsEnforceDomainRules()
    {
        var user = new User { Email = "test@example.com" };
        Assert.False(user.HasPin);

        user.SetPin(PinHasher.Hash("5826"));
        Assert.True(user.HasPin);
        Assert.Equal(1, user.SecurityVersion);

        user.RecordFailedAttempt();
        Assert.Equal(1, user.FailedAttempts);
        user.RecordUntrustedFailedAttempt();
        Assert.Equal(1, user.UntrustedFailedAttempts);

        var now = DateTimeOffset.UtcNow;
        user.Pause(now.AddMinutes(15));
        Assert.True(user.IsPaused(now));
        Assert.False(user.IsPaused(now.AddMinutes(15)));

        user.ClearLockout();
        Assert.Equal(0, user.FailedAttempts);
        Assert.Equal(1, user.UntrustedFailedAttempts);
        Assert.Null(user.PausedUntil);

        user.ClearUntrustedFailedAttempts();
        Assert.Equal(0, user.UntrustedFailedAttempts);

        user.RecordUntrustedFailedAttempt();
        user.SetPin(PinHasher.Hash("4719"));
        Assert.Equal(0, user.UntrustedFailedAttempts);
        Assert.Equal(2, user.SecurityVersion);

        user.BumpSecurityVersion();
        Assert.Equal(3, user.SecurityVersion);

        user.Remove();
        Assert.Equal(UserStatus.Removed, user.Status);
        Assert.Equal(4, user.SecurityVersion);
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
