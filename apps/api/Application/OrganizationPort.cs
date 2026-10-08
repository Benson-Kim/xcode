using Auth.Domain;

namespace Auth.Application;

public interface IOrganizationContext
{
     Guid OrganizationId { get; }
     Guid ActorId { get; }
     string CorrelationId { get; }
}

public interface IOrganizationRepository
{
     Task<Organization?> Get(CancellationToken ct);
     Task<OrganizationMembership?> Membership(Guid userId, CancellationToken ct);
     Task<IReadOnlySet<string>> Permissions(Guid userId, CancellationToken ct);
     Task<EffectiveSettings> Settings(Guid userId, CancellationToken ct);
     // Drops everything resolved so far in this request. The unit of work calls it before a retry, so a person whose
     // access changed in the meantime is checked against what the database holds now.
     void ForgetResolved();
}

public interface IUnitOfWork
{
     // One serializable transaction, then SaveChanges and commit.
     Task<T> Execute<T>(Func<Task<T>> action, CancellationToken ct);
     // No explicit transaction and no SaveChanges; a read that changes tracked state fails.
     Task<T> Read<T>(Func<Task<T>> action, CancellationToken ct);
     void Audit(string action, string entity, object? before, object? after);
}

// One Transaction owns authroization, state changes, version bump and audit. A read-only use case runs the same
// checks without a transaction and saves nothing.
public abstract class OrganizationUseCase<TRequest, TResult>(IOrganizationContext context, IOrganizationRepository repository, IUnitOfWork unitOfWork)
{
     public Task<TResult> Run(TRequest request, CancellationToken ct)
     {
          async Task<TResult> Authorized()
          {
               if (context.OrganizationId == Guid.Empty || context.ActorId == Guid.Empty)
                    throw new UnauthorizedAccessException();

               Validate(request);
               if (await repository.Membership(context.ActorId, ct) is not { Active: true })
                    throw new UnauthorizedAccessException();
               // An empty required set means any active member, so it resolves no permissions; otherwise any one listed
               // permission is enough.
               var required = RequiredPermissions;
               if (required.Count > 0 && !required.Any((await repository.Permissions(context.ActorId, ct)).Contains))
                    throw new UnauthorizedAccessException();
               return await Execute(request, ct);
          }
          return ReadOnly ? unitOfWork.Read(Authorized, ct) : unitOfWork.Execute(Authorized, ct);
     }
     protected virtual bool ReadOnly => false;
     protected abstract string RequiredPermission { get; }
     protected virtual IReadOnlyCollection<string> RequiredPermissions =>
          string.IsNullOrEmpty(RequiredPermission) ? Array.Empty<string>() : [RequiredPermission];
     protected abstract void Validate(TRequest request);
     protected abstract Task<TResult> Execute(TRequest request, CancellationToken ct);
}