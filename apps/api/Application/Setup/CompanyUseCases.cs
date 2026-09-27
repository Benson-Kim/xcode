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
        var reason = SetupPagination.Reason(input.Reason);
        var name = SetupValue.Name(input.Name);
        var company = id is null ? new PsvCompany(actor.OrganizationId, name)
            : await repository.Company(actor, id.Value, ct) ?? throw new KeyNotFoundException();
        // Creating a company expands scope: only organization-wide editors can do it.
        if (id is null && !actor.AllCompanies)
            throw new UnauthorizedAccessException();
        if (await repository.CompanyNameExists(actor.OrganizationId, name.ToUpperInvariant(), id, ct))
            throw new ArgumentException("Another company already has this name.");
        var before = id is null ? null : new { company.Name };
        if (id is not null && !company.Rename(name))
            return company.Id;
        if (id is null)
            repository.Add(company);

        await repository.RecordChange(
            actor, "companies", company.Id, before, new { company.Name }, reason, ct);
        return company.Id;
    }, ct);
}

