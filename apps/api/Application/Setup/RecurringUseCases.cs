using Auth.Domain.Setup;

namespace Auth.Application.Setup;

public sealed class RecurringUseCases(ISetupExecution execution, ISetupRepository repository)
{
    public Task<Page<RecurringDto>> List(int page, int pageSize, CancellationToken ct) => execution.Read("commitments.view", actor =>
    {
        SetupPagination.Validate(page, pageSize);
        return repository.Recurring(actor, page, pageSize, ct);
    }, ct);

    public Task<IReadOnlyList<VehicleOption>> VehicleOptions(CancellationToken ct) =>
        execution.Read("commitments.manage", actor => repository.VehicleOptions(actor, ct), ct);

    public Task<Guid> Save(Guid? id, SaveRecurring input, CancellationToken ct) => execution.Write("commitments.manage", async actor =>
    {
        var reason = SetupPagination.OptionalReason(input.Reason);
        var definition = await Definition(actor, input, ct);

        var item = id is null ? null : await repository.RecurringItem(actor, id.Value, ct) ?? throw new KeyNotFoundException();
        var latest = item?.Versions.OrderByDescending(v => v.Revision).First();
        definition.ValidateNew(actor.Today, latest?.Start);
        var existingAllocations = latest?.Allocations.Select(a => a.VehicleId).ToHashSet() ?? [];
        foreach (var share in definition.Allocations)
        {
            var vehicle = await repository.Vehicle(actor, share.VehicleId, ct) ?? throw new KeyNotFoundException();
            var company = await repository.Company(actor, vehicle.CompanyId, ct) ?? throw new KeyNotFoundException();
            var retainedRetiredVehicle = existingAllocations.Contains(vehicle.Id);
            if ((!vehicle.ActiveOn(actor.Today) || !company.ActiveOn(actor.Today)) && !retainedRetiredVehicle)
                throw new ArgumentException("New recurring shares must use active vehicles and companies.");
        }

        var before = item is null ? null : Snapshot(item);
        if (item is null)
        {
            item = new RecurringItem(actor.OrganizationId, definition);
            repository.Add(item);
        }
        else
        {
            // The full existing allocation must also be in scope before an editor may change it.
            foreach (var share in latest!.Allocations)
                _ = await repository.Vehicle(actor, share.VehicleId, ct) ?? throw new UnauthorizedAccessException();
            if (Same(latest, definition)) return item.Id;
            item.Revise(definition, actor.Today);
        }
        reason ??= SetupPagination.Automatic(latest is null
            ? $"Added scheduled {(definition.Kind == RecurringKind.Savings ? "saving" : "expense")} {definition.Name.Trim()}"
            : Changed(latest, definition));
        await repository.RecordChange(actor, "recurring", item.Id, before, Snapshot(item), reason, ct);
        return item.Id;
    }, ct);

    public Task<Guid> Stop(Guid id, StopRecurring input, CancellationToken ct) => execution.Write("commitments.manage", async actor =>
    {
        var reason = SetupPagination.Reason(input.Reason);
        if (!input.Confirmed) throw new ArgumentException("Confirm stopping this item. Past postings are retained; no posting occurs from today.");
        var item = await repository.RecurringItem(actor, id, ct) ?? throw new KeyNotFoundException();
        foreach (var share in item.Versions.OrderByDescending(v => v.Revision).First().Allocations)
            _ = await repository.Vehicle(actor, share.VehicleId, ct) ?? throw new UnauthorizedAccessException();
        var before = Snapshot(item);
        if (item.Stop(actor.Today)) await repository.RecordChange(actor, "recurring", item.Id, before, Snapshot(item), reason, ct);
        return item.Id;
    }, ct);

    // A cost is named after its expense item and counted in that item's bucket; a saving keeps the name typed for it.
    private async Task<RecurringDefinition> Definition(SetupActor actor, SaveRecurring input, CancellationToken ct)
    {
        if (input.Kind != RecurringKind.Cost)
        {
            if (input.ExpenseItemId is not null || input.Category is not null)
                throw new ArgumentException("Savings must not have an expense item or cost category.");
            return input.Definition(input.Name, null);
        }
        var expense = input.ExpenseItemId is { } expenseItemId ? await repository.ActiveExpenseItem(expenseItemId, actor.Today, ct) : null;
        if (expense is null)
            throw new ArgumentException("Choose an expense item that is in use.");
        return input.Definition(expense.Name, expense.Bucket);
    }

    // The automatic reason for a revision names what changed, for example "Changed the amount and vehicles of Parking".
    private static string Changed(RecurringVersion version, RecurringDefinition definition)
    {
        var parts = new[]
        {
            version.Kind != definition.Kind ? "type" : null,
            version.ExpenseItemId != definition.ExpenseItemId ? "expense item" : version.Name != definition.Name.Trim() ? "name" : null,
            version.ExpenseItemId == definition.ExpenseItemId && version.Bucket != definition.Bucket ? "bucket" : null,
            version.Amount != definition.Amount ? "amount" : null,
            (version.Frequency, version.Day, version.LastDay, version.Month) !=
                (definition.Schedule.Frequency, definition.Schedule.Day, definition.Schedule.LastDay, definition.Schedule.Month) ? "schedule" : null,
            version.Start != definition.Start ? "start date" : null,
            version.End != definition.End ? "end date" : null,
            SameShares(version, definition) ? null : "vehicles",
            version.Note != definition.Note ? "note" : null,
        }.OfType<string>().ToList();
        return parts.Count == 0 ? $"Changed {version.Name}" : $"Changed the {SetupPagination.Listed(parts)} of {version.Name}";
    }

    private static bool Same(RecurringVersion version, RecurringDefinition definition) =>
        version.Name == definition.Name.Trim() && version.Kind == definition.Kind && version.Category == definition.Category &&
        version.Amount == definition.Amount && version.Frequency == definition.Schedule.Frequency && version.Day == definition.Schedule.Day &&
        version.LastDay == definition.Schedule.LastDay && version.Month == definition.Schedule.Month && version.Start == definition.Start &&
        version.End == definition.End && version.ExpenseItemId == definition.ExpenseItemId && version.Bucket == definition.Bucket &&
        version.Note == definition.Note && SameShares(version, definition);

    private static bool SameShares(RecurringVersion version, RecurringDefinition definition) =>
        version.Allocations.OrderBy(a => a.VehicleId).Select(a => new VehicleShare(a.VehicleId, a.Amount))
            .SequenceEqual(definition.Allocations.OrderBy(a => a.VehicleId));

    private static object Snapshot(RecurringItem item) => new
    {
        item.Id,
        item.StoppedFrom,
        Versions = item.Versions.Select(v => new
        {
            v.Id,
            v.Revision,
            v.EffectiveFrom,
            v.Name,
            v.Kind,
            v.Category,
            v.Amount,
            v.Frequency,
            v.Day,
            v.LastDay,
            v.Month,
            v.Start,
            v.End,
            v.ExpenseItemId,
            v.Bucket,
            v.Note,
            Allocations = v.Allocations.Select(a => new { a.VehicleId, a.Amount }).ToArray()
        }).ToArray()
    };
}
