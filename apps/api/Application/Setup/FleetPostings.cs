using Auth.Domain.Setup;

namespace Auth.Application.Setup;

// Where a posting on a vehicle came from. The order is the order the ledger lists the day's rows in.
public enum PostingSource
{
    Central = 1,
    PettyCash = 2,
    Scheduled = 3
}

public static class PostingSources
{
    public static string Word(PostingSource source) => source switch
    {
        PostingSource.Central => "central",
        PostingSource.PettyCash => "pettycash",
        PostingSource.Scheduled => "scheduled",
        _ => throw new ArgumentOutOfRangeException(nameof(source))
    };

    public static PostingSource? Parse(string? value) => value?.Trim() switch
    {
        null or "" => null,
        "central" => PostingSource.Central,
        "pettycash" => PostingSource.PettyCash,
        "scheduled" => PostingSource.Scheduled,
        _ => throw new ArgumentException("Choose central, petty cash or scheduled.")
    };
}

// The purchase a central row came from: Size rows, Total in all, and the units and unit amount as bought.
public sealed record PostingGroup(Guid Id, int Size, decimal Total, decimal Units, decimal UnitAmount);

// One amount posted on one vehicle on one day. Id is the entry's; a scheduled posting's Id is its item's and VersionId
// the version that posted it. Names, units and unit amounts are as the source states them (a scheduled posting is one
// unit at the vehicle's share). Only savings have no bucket; they are never money out.
public sealed record FleetPosting(PostingSource Source, RecurringKind Kind, DateOnly Date, Guid VehicleId, Guid Id, Guid? VersionId,
    string Name, Guid? ExpenseItemId, string? CategoryName, ExpenseBucket? Bucket, decimal Units, decimal UnitAmount, decimal Amount,
    string? Note, Guid? RecordedBy, Guid? HolderId, PostingGroup? Group, long? Version);

// The one place every report reads a vehicle's postings from, so reports and the ledger cannot disagree:
// - central: expenses recorded onto the vehicle, not removed;
// - petty cash: expenses approved and not removed, present only while approved;
// - scheduled: the due dates of scheduled items with the vehicle's share, costs and savings alike.
public interface IFleetPostings
{
    // Each vehicle counts only inside its own days: from its join date, up to the day before it left, and never after
    // the business date. The vehicles are ones the actor may already see. The number of reads does not depend on how
    // many postings there are.
    Task<IReadOnlyList<FleetPosting>> Load(SetupActor actor, IReadOnlyCollection<FleetVehicle> vehicles, DateOnly from, DateOnly through,
        CancellationToken ct);

    // Only the scheduled postings of Load, for a caller that reads the stored sources itself.
    Task<IReadOnlyList<FleetPosting>> Scheduled(SetupActor actor, IReadOnlyCollection<FleetVehicle> vehicles, DateOnly from, DateOnly through,
        CancellationToken ct);
}
