// SettingsVersion is the organization's change-log version, read before any data, so a cache keyed on it never
// serves figures older than that version. Null means unknown (an actor built directly), and nothing is cached.
public sealed record SetupActor(Guid OrganizationId, Guid UserId, DateOnly Today, bool AllCompanies,
    IReadOnlyList<Guid> CompanyIds, IReadOnlyList<Guid> VehicleIds, string CorrelationId,
    IReadOnlySet<string> Permissions, long? SettingsVersion = null);

public interface ISetupExecution
{
    Task<T> Read<T>(string permission, Func<SetupActor, Task<T>> query, CancellationToken cancellationToken);
    Task<T> ReadAny<T>(IReadOnlyCollection<string> permissions, Func<SetupActor, Task<T>> query, CancellationToken cancellationToken);
    Task<T> Write<T>(string permission, Func<SetupActor, Task<T>> command, CancellationToken cancellationToken);
    Task<T> WriteAny<T>(IReadOnlyCollection<string> permissions, Func<SetupActor, Task<T>> command, CancellationToken cancellationToken);
    // The same pipeline without building a SetupActor, for work that needs only the organization context.
    Task<T> Read<T>(string permission, Func<Task<T>> query, CancellationToken cancellationToken);
    Task<T> Write<T>(string permission, Func<Task<T>> command, CancellationToken cancellationToken);
}
