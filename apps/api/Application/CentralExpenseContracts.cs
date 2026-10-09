using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;

namespace Auth.Application.CentralExpenses;

// The JSON the web and the phone read (packages/shared/src/expenses.ts). CanRecord is expenses.capture, CanCorrect is
// expenses.correct.
public sealed record ExpensePermissionsDto(bool CanRecord, bool CanCorrect);

// The whole period and every source, whatever the source filter and the search. Total is the three added up.
public sealed record ExpenseFiguresDto(decimal Total, decimal Central, decimal PettyCash, decimal Scheduled);

// The purchase a central row came from when several vehicles shared it.
public sealed record ExpenseGroupDto(Guid Id, int Size, decimal Total, decimal Units, decimal UnitAmount);

// Id is the entry's, or for a scheduled row "{scheduleId}:{date}:{vehicleId}". Only a central row has a version, and
// the flags say what the signed-in person may do with it, so clients never work the rules out themselves.
public sealed record ExpenseLedgerRowDto(string Id, string Source, DateOnly Date, Guid VehicleId, string Registration, Guid? ExpenseItemId,
    string ItemName, string? CategoryName, ExpenseBucket Bucket, decimal Units, decimal UnitAmount, decimal Total, string? Note,
    string? RecordedByName, string? HolderName, Guid? ScheduleId, ExpenseGroupDto? Group, long? Version, bool CanEdit, bool CanRemove);

// Newest first. Total and Amount count every row matching the source and the search, not only this page.
public sealed record ExpenseLedgerDto(DateOnly BusinessDate, DateOnly From, DateOnly To, ExpensePermissionsDto Permissions,
    ExpenseFiguresDto Figures, IReadOnlyList<ExpenseLedgerRowDto> Items, int PageNumber, int PageSize, int Total, decimal Amount);

public sealed record ExpenseOptionsDto(IReadOnlyList<VehicleOption> Vehicles, IReadOnlyList<ExpenseItemOption> Items);

public sealed record ExpenseAllocationInput(Guid VehicleId, decimal Amount);

// One purchase. Id is the client's own, so a retried save answers with the rows it already made.
public sealed record RecordExpense(DateOnly Date, Guid ExpenseItemId, decimal Units, decimal UnitAmount,
    IReadOnlyList<ExpenseAllocationInput> Allocations, Guid? Id = null, string? Note = null)
{
    public CentralPurchase Purchase() => new(Date, ExpenseItemId, Units, UnitAmount, string.IsNullOrWhiteSpace(Note) ? null : Note.Trim(),
        [.. (Allocations ?? []).Select(a => new ExpenseAllocationLine(a.VehicleId, a.Amount))]);
}

public sealed record ExpenseRecorded(IReadOnlyList<Guid> Ids, decimal Total);

public sealed record ChangeExpense(DateOnly Date, Guid VehicleId, Guid ExpenseItemId, decimal Units, decimal UnitAmount, long? Version = null,
    string? Note = null)
{
    public CentralExpenseLine Line()
    {
        var line = new CentralExpenseLine(Date, VehicleId, ExpenseItemId, Units, UnitAmount, string.IsNullOrWhiteSpace(Note) ? null : Note.Trim());
        line.Validate();
        return line;
    }
}

public sealed record RemoveExpense(long? Version, string? Reason);
public sealed record ExpenseSaved(Guid Id, long Version);

/// <summary>The row changed after the client read it, or a client id was already used for another purchase.</summary>
public sealed class CentralExpenseConflictException(ExpenseLedgerRowDto? current, string? message = null)
    : Exception(message ?? "This expense was changed after you opened it. Check it and save again.")
{
    public ExpenseLedgerRowDto? Current { get; } = current;
}

// What the ledger asks of the stored sources. Through is the last day to count, never after the business date; Text is
// matched as a substring, case-insensitively, by the database.
public sealed record LedgerFilter(DateOnly From, DateOnly Through, PostingSource? Source, string? Text);
public sealed record LedgerDay(DateOnly Date, int Count, decimal Total);
public sealed record LedgerSourceTotal(PostingSource Source, decimal Total);

// A central expense or an approved petty cash expense as one row of the database's own union of the two. The group
// fields are only meaningful for a central row.
public sealed class LedgerStoredRow
{
    public PostingSource Source { get; init; }
    public Guid Id { get; init; }
    public DateOnly Date { get; init; }
    public Guid VehicleId { get; init; }
    public string Registration { get; init; } = "";
    public Guid ExpenseItemId { get; init; }
    public string ItemName { get; init; } = "";
    public string CategoryName { get; init; } = "";
    public ExpenseBucket Bucket { get; init; }
    public decimal Units { get; init; }
    public decimal UnitAmount { get; init; }
    public decimal Total { get; init; }
    public string? Note { get; init; }
    public Guid RecordedBy { get; init; }
    public Guid? HolderId { get; init; }
    public Guid? GroupId { get; init; }
    public int GroupSize { get; init; }
    public decimal GroupTotal { get; init; }
    public decimal GroupUnits { get; init; }
    public decimal GroupUnitAmount { get; init; }
    public long? Version { get; init; }
}

public interface ICentralExpenseRepository
{
    // The stored rows are counted, summed and cut into a page by the database, so nothing here depends on how many
    // rows the period holds. Rows are ordered newest first, then central before petty cash, then registration, then id.
    // Counts and sums, by day, of the rows matching the filter.
    Task<IReadOnlyList<LedgerDay>> StoredDays(SetupActor actor, LedgerFilter filter, CancellationToken ct);
    // The sum of each source over the period, ignoring the filter's source and text.
    Task<IReadOnlyList<LedgerSourceTotal>> StoredTotals(SetupActor actor, DateOnly from, DateOnly through, CancellationToken ct);
    Task<IReadOnlyList<LedgerStoredRow>> StoredRows(SetupActor actor, LedgerFilter filter, int skip, int take, CancellationToken ct);
    // Vehicles in the actor's scope that were in the fleet on some day of the period.
    Task<IReadOnlyList<FleetVehicle>> Vehicles(SetupActor actor, DateOnly from, DateOnly through, CancellationToken ct);
    // Vehicles in the actor's scope, with their away periods so FleetVehicle.ActiveOn reads them. An id missing from
    // the result is outside the actor's scope or does not exist.
    Task<IReadOnlyDictionary<Guid, FleetVehicle>> VehiclesById(SetupActor actor, IEnumerable<Guid> ids, CancellationToken ct);
    Task<IReadOnlyList<VehicleOption>> VehicleOptions(SetupActor actor, DateOnly date, CancellationToken ct);
    // Every row of the purchase with this id, or with this id as its own, removed or not; a retried save looks for its own.
    Task<IReadOnlyList<CentralExpense>> Purchase(Guid id, CancellationToken ct);
    // The row if the actor can see its vehicle and it is not removed, tracked for a change.
    Task<CentralExpense?> Entry(SetupActor actor, Guid id, CancellationToken ct);
    // Whether another row of the purchase, removed or not, already holds the vehicle.
    Task<bool> PurchaseHasVehicle(Guid groupId, Guid vehicleId, Guid except, CancellationToken ct);
    Task<IReadOnlyDictionary<Guid, string>> Names(IEnumerable<Guid> userIds, CancellationToken ct);
    Task<IReadOnlyDictionary<Guid, string>> ItemNames(IEnumerable<Guid> itemIds, CancellationToken ct);
    void Add(CentralExpense row);
    Task RecordChange(SetupActor actor, CentralExpense row, object? before, object after, string reason, CancellationToken ct);
}
