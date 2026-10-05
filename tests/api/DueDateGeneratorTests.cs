using Auth.Domain.Setup;
using Xunit;

namespace Auth.Tests;

// RecurringItem.DueBetween steps each version's due dates arithmetically. It must post exactly what asking DueOn about
// every single day posts: the same days, each under the same version.
public sealed class DueDateGeneratorTests
{
    private static readonly Guid Organization = Guid.NewGuid();
    private static readonly Guid Vehicle = Guid.NewGuid();
    private static readonly DateOnly Origin = new(2027, 11, 1);

    private static RecurringDefinition Definition(RecurringSchedule schedule, DateOnly start, DateOnly? end = null, decimal amount = 100m) =>
        new("Item", RecurringKind.Cost, amount, schedule, start, end, [new VehicleShare(Vehicle, amount)], Bucket: ExpenseBucket.RecurringCharges);

    private static RecurringItem Item(RecurringSchedule schedule, DateOnly start, DateOnly? end = null) =>
        new(Organization, Definition(schedule, start, end));

    [Fact]
    public void EveryFrequencyARevisionAStopAndAnEndPostOnTheSameDaysAsDueOn()
    {
        var start = new DateOnly(2027, 12, 1);
        var items = new List<RecurringItem>
        {
            Item(new RecurringSchedule(RecurrenceFrequency.Daily), start),
            Item(new RecurringSchedule(RecurrenceFrequency.Weekly, 3), start),
            Item(new RecurringSchedule(RecurrenceFrequency.Monthly, 28), start),
            Item(new RecurringSchedule(RecurrenceFrequency.Monthly, null, lastDay: true), start),
            Item(new RecurringSchedule(RecurrenceFrequency.Yearly, 15, month: 3), start),
            // 29 February 2028, then 28 February 2029.
            Item(new RecurringSchedule(RecurrenceFrequency.Yearly, null, lastDay: true, month: 2), start),
            Item(new RecurringSchedule(RecurrenceFrequency.Daily), start, end: new DateOnly(2028, 1, 10)),
        };

        // A running item revised mid-range onto another schedule, then stopped.
        var revised = Item(new RecurringSchedule(RecurrenceFrequency.Weekly, 1), start);
        revised.Revise(Definition(new RecurringSchedule(RecurrenceFrequency.Monthly, 5), start, amount: 250m), new DateOnly(2028, 6, 10));
        revised.Stop(new DateOnly(2029, 1, 6));
        items.Add(revised);

        // A pending item postponed, then brought forward before its first start: the last revision takes effect
        // earlier than both before it, so neither of them ever posts.
        var pending = Item(new RecurringSchedule(RecurrenceFrequency.Weekly, 5), new DateOnly(2028, 4, 1));
        pending.Revise(Definition(new RecurringSchedule(RecurrenceFrequency.Weekly, 5), new DateOnly(2028, 5, 1)), new DateOnly(2028, 3, 1));
        pending.Revise(Definition(new RecurringSchedule(RecurrenceFrequency.Monthly, 2), new DateOnly(2028, 2, 20)), new DateOnly(2028, 3, 5));
        items.Add(pending);

        foreach (var item in items)
            Assert.NotEmpty(AssertSameAsDueOn(item, Origin, new DateOnly(2029, 3, 31)));
        Assert.Equal(2, AssertSameAsDueOn(revised, Origin, new DateOnly(2029, 3, 31)).Select(x => x.VersionId).Distinct().Count());
        // Only a window of the range: clipped at both ends.
        Assert.Equal([new DateOnly(2028, 2, 29)], AssertSameAsDueOn(items[5], new DateOnly(2028, 2, 29), new DateOnly(2028, 3, 1)).Select(x => x.Date));
    }

    // Property style: random schedules, revisions on random days, random stops and random windows.
    [Fact]
    public void RandomItemsPostOnTheSameDaysAsDueOnInAnyWindow()
    {
        var random = new Random(20260930);
        for (var run = 0; run < 400; run++)
        {
            var item = RandomItem(random);
            var from = Origin.AddDays(random.Next(0, 500));
            AssertSameAsDueOn(item, from, from.AddDays(random.Next(0, 500)));
        }
    }

    private static RecurringItem RandomItem(Random random)
    {
        var start = Origin.AddDays(random.Next(0, 400));
        var item = new RecurringItem(Organization, Definition(RandomSchedule(random), start, RandomEnd(random, start)));
        var today = Origin;
        for (var revisions = random.Next(0, 4); revisions > 0; revisions--)
        {
            today = today.AddDays(random.Next(1, 150));
            var current = item.Versions.MaxBy(v => v.Revision)!;
            // A running item keeps its start; a pending one may move it earlier or later.
            var nextStart = current.Start < today ? current.Start : today.AddDays(random.Next(-60, 90));
            item.Revise(Definition(RandomSchedule(random), nextStart, RandomEnd(random, nextStart), random.Next(1, 500)), today);
        }
        if (random.Next(0, 2) == 0) item.Stop(today.AddDays(random.Next(0, 200)));
        return item;
    }

    private static DateOnly? RandomEnd(Random random, DateOnly start) => random.Next(0, 3) == 0 ? start.AddDays(random.Next(0, 300)) : null;

    private static RecurringSchedule RandomSchedule(Random random)
    {
        var lastDay = random.Next(0, 4) == 0;
        int? day = lastDay ? null : random.Next(1, 29);
        return (RecurrenceFrequency)random.Next(1, 5) switch
        {
            RecurrenceFrequency.Daily => new(RecurrenceFrequency.Daily),
            RecurrenceFrequency.Weekly => new(RecurrenceFrequency.Weekly, random.Next(0, 7)),
            RecurrenceFrequency.Monthly => new(RecurrenceFrequency.Monthly, day, lastDay),
            _ => new(RecurrenceFrequency.Yearly, day, lastDay, random.Next(1, 13)),
        };
    }

    private static List<(DateOnly Date, Guid VersionId)> AssertSameAsDueOn(RecurringItem item, DateOnly from, DateOnly through)
    {
        var expected = new List<(DateOnly Date, Guid VersionId)>();
        for (var day = from; day <= through; day = day.AddDays(1))
            if (item.DueOn(day) is { } version) expected.Add((day, version.Id));
        var generated = item.DueBetween(from, through).Select(x => (x.Date, VersionId: x.Version.Id)).OrderBy(x => x.Date).ToList();
        Assert.Equal(expected, generated);
        return generated;
    }
}
