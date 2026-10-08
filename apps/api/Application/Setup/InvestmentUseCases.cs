using Auth.Domain;
using Auth.Domain.Setup;

namespace Auth.Application.Setup;

// What went into each vehicle. A person sees and changes it only for vehicles in their data scope. Changes are
// logged against the vehicle, so the change log keeps a removed entry and scopes it like the vehicle.
public sealed class InvestmentUseCases(ISetupExecution execution, ISetupRepository repository, IClock clock)
{
    private const string Section = "investment";

    // What has come back is the vehicle's net contribution (money in less money out, as its report counts them) from
    // the day it joined through the business date; it may be negative. The percentage is of what went in.
    public Task<InvestmentDto> Get(Guid vehicleId, CancellationToken ct) => execution.Read(PermissionKeys.InvestView, async actor =>
    {
        var vehicle = await repository.Vehicle(actor, vehicleId, ct) ?? throw new KeyNotFoundException();
        var investment = await repository.Investment(vehicleId, ct);
        var returned = (await repository.Report(actor, vehicle, vehicle.JoinedOn, actor.Today, ct)).Net;
        return investment with
        {
            Returned = returned,
            PercentPaidOff = investment.TotalInvested == 0 ? null
                : Math.Round(returned / investment.TotalInvested * 100m, MidpointRounding.AwayFromZero)
        };
    }, ct);

    public Task<Guid> Add(Guid vehicleId, SaveInvestment input, CancellationToken ct) => execution.Write(PermissionKeys.InvestManage, async actor =>
    {
        var vehicle = await repository.Vehicle(actor, vehicleId, ct) ?? throw new KeyNotFoundException();
        var entry = new VehicleInvestment(vehicle, input.Date, input.Description!, input.Amount, actor.Today, actor.UserId, clock.UtcNow);
        repository.Add(entry);
        await repository.RecordChange(actor, Section, vehicle.Id, null, Snapshot(entry),
            $"Recorded investment {entry.Description} on {vehicle.Registration}", ct);
        return entry.Id;
    }, ct);

    public Task<Guid> Update(Guid id, SaveInvestment input, CancellationToken ct) => execution.Write(PermissionKeys.InvestManage, async actor =>
    {
        var (entry, vehicle) = await Entry(actor, id, ct);
        var before = Snapshot(entry);
        if (entry.Change(input.Date, input.Description!, input.Amount, actor.Today))
            await repository.RecordChange(actor, Section, vehicle.Id, before, Snapshot(entry),
                $"Changed investment {entry.Description} on {vehicle.Registration}", ct);
        return entry.Id;
    }, ct);

    public Task<Guid> Remove(Guid id, CancellationToken ct) => execution.Write(PermissionKeys.InvestManage, async actor =>
    {
        var (entry, vehicle) = await Entry(actor, id, ct);
        repository.Remove(entry);
        await repository.RecordChange(actor, Section, vehicle.Id, Snapshot(entry), null,
            $"Removed investment {entry.Description} on {vehicle.Registration}", ct);
        return entry.Id;
    }, ct);

    // An entry on a vehicle outside the person's scope is reported as not found, like the vehicle itself.
    private async Task<(VehicleInvestment Entry, FleetVehicle Vehicle)> Entry(SetupActor actor, Guid id, CancellationToken ct)
    {
        var entry = await repository.InvestmentEntry(id, ct) ?? throw new KeyNotFoundException();
        var vehicle = await repository.Vehicle(actor, entry.VehicleId, ct) ?? throw new KeyNotFoundException();
        return (entry, vehicle);
    }

    private static object Snapshot(VehicleInvestment entry) => new
    {
        entry.Id,
        entry.VehicleId,
        entry.Date,
        entry.Description,
        entry.Amount
    };
}
