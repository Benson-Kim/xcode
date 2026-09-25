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
}

public interface IUnitOfWork
{
     Task<T> Execute<T>(Func<Task<T>> action, CancellationToken ct);
     void Audit(string action, string entity, object? before, object? after);
}

// One Transaction owns authroization, state changes, version bump and audit
public abstract class OrganizationUseCase<TRequest, TResult>(IOrganizationContext context, IOrganizationRepository repository, IUnitOfWork unitOfWork)
{
     public Task<TResult> Run(TRequest request, CancellationToken ct) => unitOfWork.Execute(
          async () =>
          {
               if (context.OrganizationId == Guid.Empty || context.ActorId == Guid.Empty)
                    throw new UnauthorizedAccessException();

               Validate(request);
               var member = await repository.Membership(context.ActorId, ct);
               var permissions = await repository.Permissions(context.ActorId, ct);
               if (member is not { Active: true } || !permissions.Contains(RequiredPermission))
                    throw new UnauthorizedAccessException();
               return await Execute(request, ct);
          }, ct);
     protected abstract string RequiredPermission { get; }
     protected abstract void Validate(TRequest request);
     protected abstract Task<TResult> Execute(TRequest request, CancellationToken ct);
}