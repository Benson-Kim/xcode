using Auth.Domain.Setup;

namespace Auth.Application.Setup;

public interface ISetupRepository
{
    Task<Page<CompanyDto>> Companies(SetupActor actor, int page, int pageSize, CancellationToken ct);
    Task<PsvCompany?> Company(SetupActor actor, Guid id, CancellationToken ct);
    Task<IReadOnlyList<CompanyOption>> CompanyOptions(SetupActor actor, CancellationToken ct);
    Task<bool> HasActiveVehicles(Guid companyId, DateOnly today, CancellationToken ct);
    // The first and last day this vehicle has revenue recorded for, or null when it has none. A lifecycle
    // change that would put a recorded day outside the vehicle's time in the fleet is refused (D4).
    Task<(DateOnly First, DateOnly Last)?> RecordedRevenueDays(Guid vehicleId, CancellationToken ct);
    Task<bool> CompanyNameExists(Guid organizationId, string normalizedName, Guid? except, CancellationToken ct);
    Task<Page<VehicleDto>> Vehicles(SetupActor actor, int page, int pageSize, CancellationToken ct);
    Task<FleetVehicle?> Vehicle(SetupActor actor, Guid id, CancellationToken ct);
    // One read each for many ids: an id missing from the result is outside the actor's scope or does not exist.
    Task<IReadOnlyDictionary<Guid, FleetVehicle>> VehiclesById(SetupActor actor, IEnumerable<Guid> ids, CancellationToken ct);
    Task<IReadOnlyDictionary<Guid, PsvCompany>> CompaniesById(SetupActor actor, IEnumerable<Guid> ids, CancellationToken ct);
    Task<bool> RegistrationExists(Guid organizationId, string registration, CancellationToken ct);
    Task<IReadOnlyList<VehicleOption>> VehicleOptions(SetupActor actor, CancellationToken ct);
    Task<int> FirstDayOfWeek(CancellationToken ct);
    Task<string> Currency(CancellationToken ct);
    Task<Page<RecurringDto>> Recurring(SetupActor actor, int page, int pageSize, CancellationToken ct);
    Task<RecurringItem?> RecurringItem(SetupActor actor, Guid id, CancellationToken ct);
    // Contract C6 for a vehicle already found in the actor's scope: figures over its active days from `from` through `through`.
    Task<VehicleReport> Report(SetupActor actor, FleetVehicle vehicle, DateOnly from, DateOnly through, CancellationToken ct);
    Task<Page<HistoryEntry>> History(SetupActor actor, HistoryFilter filter, int page, int pageSize, CancellationToken ct);
    Task<Page<ExpenseCategoryDto>> ExpenseCategories(DateOnly today, int page, int pageSize, CancellationToken ct);
    Task<IReadOnlyList<ExpenseItemOption>> ExpenseItemOptions(DateOnly today, CancellationToken ct);
    Task<ExpenseItemOption?> ActiveExpenseItem(Guid id, DateOnly today, CancellationToken ct);
    Task<ExpenseCategory?> ExpenseCategory(Guid id, CancellationToken ct);
    Task<ExpenseItem?> ExpenseItem(Guid id, CancellationToken ct);
    Task<bool> ExpenseCategoryNameExists(Guid organizationId, string normalizedName, Guid? except, CancellationToken ct);
    Task<bool> ExpenseItemNameExists(Guid organizationId, Guid categoryId, string normalizedName, Guid? except, CancellationToken ct);
    Task<InvestmentDto> Investment(Guid vehicleId, CancellationToken ct);
    Task<VehicleInvestment?> InvestmentEntry(Guid id, CancellationToken ct);
    void Add(PsvCompany company);
    void Add(FleetVehicle vehicle);
    void Add(RecurringItem item);
    void Add(ExpenseCategory category);
    void Add(ExpenseItem item);
    void Add(VehicleInvestment entry);
    void Remove(VehicleInvestment entry);
    Task RecordChange(SetupActor actor, string section, Guid entityId, object? before, object? after, string reason, CancellationToken ct);
}
