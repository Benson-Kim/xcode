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
        var reason = SetupPagination.Reason(input.Reason);
        var definition = input.Definition();
        definition.Validate();
        if (definition.Start == default) throw new ArgumentException("Start date is required.");

        var item = id is null ? null : await repository.RecurringItem(actor, id.Value, ct) ?? throw new KeyNotFoundException();
        var existingAllocations = item?.Versions.OrderByDescending(v => v.Revision).First().Allocations
            .Select(a => a.VehicleId).ToHashSet() ?? [];
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
            foreach (var share in item.Versions.OrderByDescending(v => v.Revision).First().Allocations)
                _ = await repository.Vehicle(actor, share.VehicleId, ct) ?? throw new UnauthorizedAccessException();
            var current = item.Versions.OrderByDescending(v => v.Revision).First();
            if (Same(current, definition)) return item.Id;
            item.Revise(definition, actor.Today);
        }
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

    private static bool Same(RecurringVersion version, RecurringDefinition definition) =>
        version.Name == definition.Name.Trim() && version.Kind == definition.Kind && version.Category == definition.Category &&
        version.Amount == definition.Amount && version.Frequency == definition.Schedule.Frequency && version.Day == definition.Schedule.Day &&
        version.LastDay == definition.Schedule.LastDay && version.Start == definition.Start && version.End == definition.End &&
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
            v.Start,
            v.End,
            Allocations = v.Allocations.Select(a => new { a.VehicleId, a.Amount }).ToArray()
        }).ToArray()
    };
}
