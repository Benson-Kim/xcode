using Auth.Domain.Setup;

namespace Auth.Application.Setup;

public sealed class CompanyUseCases(ISetupExecution execution, ISetupRepository repository)
{
    public Task<Page<CompanyDto>> List(int page, int pageSize, CancellationToken ct)
    => execution.Read("companies.manage", actor =>
    {
        SetupPagination.Validate(page, pageSize);
        return repository.Companies(actor, page, pageSize, ct);
    }, ct);

    public Task<Guid> Save(Guid? id, SaveCompany input, CancellationToken ct) => execution.Write("companies.manage", async actor =>
    {
        var reason = SetupPagination.OptionalReason(input.Reason);
        var name = SetupValue.Name(input.Name);
        var company = id is null ? new PsvCompany(actor.OrganizationId, name)
            : await repository.Company(actor, id.Value, ct) ?? throw new KeyNotFoundException();
        // Creating a company expands scope: only organization-wide editors can do it.
        if (id is null && !actor.AllCompanies)
            throw new UnauthorizedAccessException();
        if (id is not null && !company.ActiveOn(actor.Today))
            throw new ArgumentException("Archived companies cannot be renamed. Restore it first.");
        if (await repository.CompanyNameExists(actor.OrganizationId, name.ToUpperInvariant(), id, ct))
            throw new ArgumentException("Another company already has this name.");
        var before = id is null ? null : Snapshot(company);
        var previous = company.Name;
        if (id is not null && !company.Rename(name))
            return company.Id;
        if (id is null)
            repository.Add(company);

        reason ??= SetupPagination.Automatic(id is null ? $"Added company {company.Name}" : $"Renamed company {previous} to {company.Name}");
        await repository.RecordChange(
            actor, "companies", company.Id, before, Snapshot(company), reason, ct);
        return company.Id;
    }, ct);

    public Task<Guid> SetArchived(Guid id, bool archived, CompanyLifecycleRequest input, CancellationToken ct)
        => execution.Write("companies.manage", async actor =>
        {
            var reason = SetupPagination.OptionalReason(input.Reason);
            var company = await repository.Company(actor, id, ct) ?? throw new KeyNotFoundException();
            var before = Snapshot(company);
            bool changed;
            if (archived)
            {
                // Already archived or scheduled: the domain decides, so a moved business date cannot hide it.
                if (company.ArchivedOn is null && await repository.HasActiveVehicles(company.Id, actor.Today, ct))
                    throw new ArgumentException("Retire every vehicle in this company before archiving it.");
                changed = company.Archive(actor.Today);
            }
            else
            {
                changed = company.Restore();
            }
            if (changed)
                await repository.RecordChange(actor, "companies", company.Id, before, Snapshot(company),
                    reason ?? SetupPagination.Automatic($"{(archived ? "Archived" : "Restored")} company {company.Name}"), ct);
            return company.Id;
        }, ct);

    private static object Snapshot(PsvCompany company) => new
    {
        company.Id,
        company.Name,
        company.ArchivedOn,
        Active = company.ArchivedOn is null
    };
}
