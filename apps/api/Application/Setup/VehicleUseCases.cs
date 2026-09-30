using System.Globalization;
using Auth.Domain.Setup;

namespace Auth.Application.Setup;

public sealed class VehicleUseCases(ISetupExecution execution, ISetupRepository repository, IOrganizationRepository organizations)
{
    // Someone who may only see investment still has to find the vehicle it belongs to; every change stays vehicles.manage.
    private static readonly string[] Listers = ["vehicles.manage", "invest.view"];

    public Task<Page<VehicleDto>> List(int page, int pageSize, CancellationToken ct) => execution.Read("", async actor =>
    {
        await SetupPermissions.RequireAny(organizations, actor, Listers, ct);
        SetupPagination.Validate(page, pageSize);
        var vehicles = await repository.Vehicles(actor, page, pageSize, ct);
        // Reaching a vehicle's investment needs its registration and company, not the targets it is run against or
        // its scheduled items.
        return actor.Permissions.Contains("vehicles.manage") ? vehicles : vehicles with
        {
            Items = [.. vehicles.Items.Select(v => v with { WeeklyTarget = null, Targets = [], RecurringItems = null })]
        };
    }, ct);

    public Task<IReadOnlyList<CompanyOption>> CompanyOptions(CancellationToken ct) =>
        execution.Read("vehicles.manage", actor => repository.CompanyOptions(actor, ct), ct);

    public Task<Guid> Save(Guid? id, SaveVehicle input, CancellationToken ct) => execution.Write("vehicles.manage", async actor =>
    {
        var reason = SetupPagination.OptionalReason(input.Reason);
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
        var (previousCompany, previousJoin, targetCount) = (vehicle.CompanyId, vehicle.JoinedOn, vehicle.Targets.Count);
        if (id is not null && !vehicle.Update(company.Id, input.JoinedOn, input.WeeklyTarget, actor.Today)) return vehicle.Id;
        if (id is null) repository.Add(vehicle);
        if (reason is null)
        {
            var currency = await repository.Currency(ct);
            string Target(decimal amount, DateOnly from) => $"{currency} {Amount(amount)} from {Date(from)}";
            // The target an edit sets takes effect today, or on the join date if that is later (see FleetVehicle.Update).
            var effective = actor.Today < vehicle.JoinedOn ? vehicle.JoinedOn : actor.Today;
            var newTarget = vehicle.Targets.Skip(targetCount).LastOrDefault(t => t.EffectiveFrom == effective && t.WeeklyAmount == input.WeeklyTarget);
            reason = id is null
                ? $"Added vehicle {vehicle.Registration} to {company.Name} with a weekly target of {Target(input.WeeklyTarget, vehicle.JoinedOn)}"
                : string.Join("; ", new[]
                {
                    previousCompany != vehicle.CompanyId ? $"moved {vehicle.Registration} to {company.Name}" : null,
                    previousJoin != vehicle.JoinedOn ? $"changed when {vehicle.Registration} joined the fleet to {Date(vehicle.JoinedOn)}" : null,
                    newTarget is not null ? $"changed the weekly target of {vehicle.Registration} to {Target(newTarget.WeeklyAmount, newTarget.EffectiveFrom)}" : null
                }.OfType<string>().DefaultIfEmpty($"changed vehicle {vehicle.Registration}"));
            reason = SetupPagination.Automatic(char.ToUpperInvariant(reason[0]) + reason[1..]);
        }
        await repository.RecordChange(actor, "vehicles", vehicle.Id, before, Snapshot(vehicle), reason, ct);
        return vehicle.Id;
    }, ct);

    public Task<Guid> Retire(Guid id, VehicleLifecycleRequest input, CancellationToken ct) => execution.Write("vehicles.manage", async actor =>
    {
        var reason = SetupPagination.OptionalReason(input.Reason);
        var vehicle = await repository.Vehicle(actor, id, ct) ?? throw new KeyNotFoundException();
        var before = Snapshot(vehicle);
        if (vehicle.Retire(input.LeftOn, actor.Today))
            await repository.RecordChange(actor, "vehicles", vehicle.Id, before, Snapshot(vehicle),
                reason ?? $"Vehicle {vehicle.Registration} left the fleet on {Date(input.LeftOn)}", ct);
        return vehicle.Id;
    }, ct);

    public Task<Guid> Restore(Guid id, VehicleRestoreRequest input, CancellationToken ct) => execution.Write("vehicles.manage", async actor =>
    {
        var reason = SetupPagination.OptionalReason(input.Reason);
        var vehicle = await repository.Vehicle(actor, id, ct) ?? throw new KeyNotFoundException();
        var company = await repository.Company(actor, vehicle.CompanyId, ct) ?? throw new KeyNotFoundException();
        if (!company.ActiveOn(actor.Today))
            throw new ArgumentException("Restore the vehicle's archived company first.");
        var before = Snapshot(vehicle);
        if (vehicle.Restore())
            await repository.RecordChange(actor, "vehicles", vehicle.Id, before, Snapshot(vehicle),
                reason ?? $"Vehicle {vehicle.Registration} returned to the fleet", ct);
        return vehicle.Id;
    }, ct);

    public Task<VehicleReport> Report(Guid id, DateOnly? start, DateOnly? end, string? period, CancellationToken ct) => execution.Read("vehicles.manage", async actor =>
    {
        var (from, through) = period is not null
            ? ReportPeriod.Current(period, actor.Today, await repository.FirstDayOfWeek(ct))
            : (start ?? throw new ArgumentException("Choose a period, or a from and through date."), end ?? throw new ArgumentException("Choose a period, or a from and through date."));
        if (through < from || through.DayNumber - from.DayNumber > 366 || through > actor.Today)
            throw new ArgumentException("Report range must be at most 367 days and cannot include the future.");
        // A vehicle that left stays in every past report; one outside the actor's scope is not found.
        var vehicle = await repository.Vehicle(actor, id, ct) ?? throw new KeyNotFoundException();
        return await repository.Report(actor, vehicle, from, through, ct);
    }, ct);

    private static string Date(DateOnly date) => date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    private static string Amount(decimal amount) =>
        amount.ToString(decimal.Truncate(amount) == amount ? "#,##0" : "#,##0.00", CultureInfo.InvariantCulture);

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
