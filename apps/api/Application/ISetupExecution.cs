public sealed record SetupActor(Guid OrganizationId, Guid UserId, DateOnly Today, bool AllCompanies,
    IReadOnlyList<Guid> CompanyIds, IReadOnlyList<Guid> VehicleIds, string CorrelationId,
    IReadOnlySet<string> Permissions);

public interface ISetupExecution
{
    Task<T> Read<T>(string permission, Func<SetupActor, Task<T>> query, CancellationToken cancellationToken);
    Task<T> ReadAny<T>(IReadOnlyCollection<string> permissions, Func<SetupActor, Task<T>> query, CancellationToken cancellationToken);
    Task<T> Write<T>(string permission, Func<SetupActor, Task<T>> command, CancellationToken cancellationToken);
    Task<T> WriteAny<T>(IReadOnlyCollection<string> permissions, Func<SetupActor, Task<T>> command, CancellationToken cancellationToken);
}
