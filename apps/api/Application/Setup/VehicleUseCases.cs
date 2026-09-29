using Auth.Domain.Setup;

namespace Auth.Application.Setup;

public sealed class VehicleUseCases(ISetupExecution execution, ISetupRepository repository)
{
    public Task<Page<VehicleDto>> List(int page, int pageSize, CancellationToken ct) => execution.Read("vehicles.manage", actor =>
    {
        SetupPagination.Validate(page, pageSize);
        return repository.Vehicles(actor, page, pageSize, ct);
    }, ct);

    public Task<IReadOnlyList<CompanyOption>> CompanyOptions(CancellationToken ct) =>
        execution.Read("vehicles.manage", actor => repository.CompanyOptions(actor, ct), ct);

    public Task<Guid> Save(Guid? id, SaveVehicle input, CancellationToken ct) => execution.Write("vehicles.manage", async actor =>
    {
        var reason = SetupPagination.Reason(input.Reason);
        var registration = new VehicleRegistration(input.Registration);
        SetupValue.Money(input.WeeklyTarget);
        if (input.JoinedOn == default || input.JoinedOn > actor.Today)
            throw new ArgumentException("A vehicle cannot join after the business date.");
        var company = await repository.Company(actor, input.CompanyId, ct) ?? throw new KeyNotFoundException();
        if (!company.ActiveOn(actor.Today))
            throw new ArgumentException("Choose an active PSV company.");
        if (id is null && !actor.AllCompanies && !actor.CompanyIds.Contains(company.Id)) throw new UnauthorizedAccessException();
        var vehicle = id is null ? new FleetVehicle(actor.OrganizationId, company.Id, registration, input.JoinedOn, input.WeeklyTarget)
            : await repository.Vehicle(actor, id.Value, ct) ?? throw new KeyNotFoundException();
        if (vehicle.LeftOn is not null)
            throw new ArgumentException("Retired vehicles must be restored before they can be edited.");
        if (vehicle.Registration != registration.Value) throw new ArgumentException("Registration cannot change after a vehicle is added.");
        if (id is null && await repository.RegistrationExists(actor.OrganizationId, registration.Value, ct))
            throw new ArgumentException("This registration already exists.");
        var before = id is null ? null : Snapshot(vehicle);
        if (id is not null && !vehicle.Update(company.Id, input.JoinedOn, input.WeeklyTarget, actor.Today)) return vehicle.Id;
        if (id is null) repository.Add(vehicle);
        await repository.RecordChange(actor, "vehicles", vehicle.Id, before, Snapshot(vehicle), reason, ct);
        return vehicle.Id;
    }, ct);

    public Task<Guid> Retire(Guid id, VehicleLifecycleRequest input, CancellationToken ct) => execution.Write("vehicles.manage", async actor =>
    {
        var reason = SetupPagination.Reason(input.Reason);
        var vehicle = await repository.Vehicle(actor, id, ct) ?? throw new KeyNotFoundException();
        var before = Snapshot(vehicle);
        if (vehicle.Retire(input.LeftOn, actor.Today))
            await repository.RecordChange(actor, "vehicles", vehicle.Id, before, Snapshot(vehicle), reason, ct);
        return vehicle.Id;
    }, ct);

    public Task<Guid> Restore(Guid id, VehicleRestoreRequest input, CancellationToken ct) => execution.Write("vehicles.manage", async actor =>
    {
        var reason = SetupPagination.Reason(input.Reason);
        var vehicle = await repository.Vehicle(actor, id, ct) ?? throw new KeyNotFoundException();
        var company = await repository.Company(actor, vehicle.CompanyId, ct) ?? throw new KeyNotFoundException();
        if (!company.ActiveOn(actor.Today))
            throw new ArgumentException("Restore the vehicle's archived company first.");
        var before = Snapshot(vehicle);
        if (vehicle.Restore())
            await repository.RecordChange(actor, "vehicles", vehicle.Id, before, Snapshot(vehicle), reason, ct);
        return vehicle.Id;
    }, ct);

    public Task<VehicleReport> Report(Guid id, DateOnly? start, DateOnly? end, string? period, CancellationToken ct) => execution.Read("vehicles.manage", async actor =>
    {
        var (from, through) = period is not null
            ? ReportPeriod.Current(period, actor.Today, await repository.FirstDayOfWeek(ct))
            : (start ?? throw new ArgumentException("Choose a period, or a from and through date."), end ?? throw new ArgumentException("Choose a period, or a from and through date."));
        if (through < from || through.DayNumber - from.DayNumber > 366 || through > actor.Today)
            throw new ArgumentException("Report range must be at most 367 days and cannot include the future.");
        _ = await repository.Vehicle(actor, id, ct) ?? throw new KeyNotFoundException();
        return await repository.Report(actor, id, from, through, ct);
    }, ct);

    private static object Snapshot(FleetVehicle vehicle) => new
    {
        vehicle.Id,
        vehicle.Registration,
        vehicle.CompanyId,
        vehicle.JoinedOn,
        vehicle.LeftOn,
        Targets = vehicle.Targets.Select(t => new { t.EffectiveFrom, t.WeeklyAmount, t.Revision }).ToArray()
    };
}
