using Auth.Domain.Setup;

namespace Auth.Application.Setup;

public interface ISetupRepository
{
    Task<Page<CompanyDto>> Companies(SetupActor actor, int page, int pageSize, CancellationToken ct);
    Task<PsvCompany?> Company(SetupActor actor, Guid id, CancellationToken ct);
    Task<bool> CompanyNameExists(Guid organizationId, string normalizedName, Guid? except, CancellationToken ct);
    Task<Page<VehicleDto>> Vehicles(SetupActor actor, int page, int pageSize, CancellationToken ct);
    Task<FleetVehicle?> Vehicle(SetupActor actor, Guid id, CancellationToken ct);
    Task<bool> RegistrationExists(Guid organizationId, string registration, CancellationToken ct);
    Task<Page<RecurringDto>> Recurring(SetupActor actor, int page, int pageSize, CancellationToken ct);
    Task<RecurringItem?> RecurringItem(SetupActor actor, Guid id, CancellationToken ct);
    Task<VehicleReport> Report(SetupActor actor, Guid vehicleId, DateOnly from, DateOnly through, CancellationToken ct);
    Task<Page<OrganizationSettingsVersion>> History(SetupActor actor, int page, int pageSize, CancellationToken ct);
    void Add(PsvCompany company);
    void Add(FleetVehicle vehicle);
    void Add(RecurringItem item);
    Task RecordChange(SetupActor actor, string section, Guid entityId, object? before, object after, string reason, CancellationToken ct);
}
