using Auth.Application.Setup;
using Auth.Application;
using Auth.Domain.Setup;
using Auth.Infrastructure.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Api;

public static class SetupEndpoints
{
    public static IServiceCollection AddSetup(this IServiceCollection services)
    {
        services.AddScoped<ISetupExecution, SetupExecution>();
        services.AddScoped<ISetupRepository, SetupRepository>();
        services.AddScoped<CompanyUseCases>();
        services.AddScoped<VehicleUseCases>();
        services.AddScoped<RecurringUseCases>();
        services.AddScoped<AccessUseCases>();
        return services;
    }

    // Every /setup route group maps domain failures to client responses instead of the global 500 handler.
    public static RouteGroupBuilder WithSetupErrors(this RouteGroupBuilder group)
    {
        group.AddEndpointFilter(async (context, next) =>
        {
            try { return await next(context); }
            catch (UnauthorizedAccessException) { return Results.Problem(statusCode: 403, title: "Not permitted in this organization or data scope."); }
            catch (KeyNotFoundException) { return Results.Problem(statusCode: 404, title: "Record not found in your scope."); }
            catch (ArgumentException error) { return Results.Problem(statusCode: 400, title: "Invalid setup change", detail: error.Message); }
            catch (DbUpdateConcurrencyException) { return Results.Problem(statusCode: 409, title: "Settings changed. Reload before saving."); }
            catch (DbUpdateException) { return Results.Problem(statusCode: 409, title: "A conflicting record exists. Reload before saving."); }
        });
        return group;
    }

    public static void MapSetup(this WebApplication app)
    {
        var group = app.MapGroup("/setup").RequireAuthorization().WithTags("Setup").WithSetupErrors();
        group.MapGet("/access/catalog", (AccessUseCases useCases, CancellationToken ct) => useCases.Catalog(ct))
            .Produces<IReadOnlyList<PermissionGroup>>().WithName("GetAccessCatalog");
        group.MapGet("/access/roles", (AccessUseCases useCases, CancellationToken ct) => useCases.Roles(ct))
            .Produces<IReadOnlyList<AccessRole>>().WithName("ListAccessRoles");
        group.MapGet("/access/scope-options", (AccessUseCases useCases, CancellationToken ct) => useCases.ScopeOptions(ct))
            .Produces<ScopeOptions>().WithName("GetAccessScopeOptions");
        group.MapGet("/people", (AccessUseCases useCases, CancellationToken ct, int page = 1, int pageSize = 25) => useCases.List(page, pageSize, ct))
            .Produces<Page<PersonDto>>().WithName("ListPeople");
        group.MapGet("/people/{id:guid}", (Guid id, AccessUseCases useCases, CancellationToken ct) => useCases.Get(id, ct))
            .Produces<PersonDto>().WithName("GetPerson");
        group.MapPost("/people", async (SavePerson input, AccessUseCases useCases, CancellationToken ct) => Results.Ok(new { id = await useCases.Save(null, input, ct) }))
            .WithName("CreatePerson");
        group.MapPut("/people/{id:guid}", async (Guid id, SavePerson input, AccessUseCases useCases, CancellationToken ct) => Results.Ok(new { id = await useCases.Save(id, input, ct) }))
            .WithName("UpdatePerson");
        group.MapPost("/people/{id:guid}/activate", async (Guid id, PersonLifecycleRequest input, AccessUseCases useCases, CancellationToken ct) => Results.Ok(new { id = await useCases.SetActive(id, true, input, ct) }))
            .WithName("ActivatePerson");
        group.MapPost("/people/{id:guid}/deactivate", async (Guid id, PersonLifecycleRequest input, AccessUseCases useCases, CancellationToken ct) => Results.Ok(new { id = await useCases.SetActive(id, false, input, ct) }))
            .WithName("DeactivatePerson");
        group.MapPost("/people/{id:guid}/sign-out", async (Guid id, AccessUseCases useCases, CancellationToken ct) => Results.Ok(new { id = await useCases.SignOut(id, ct) }))
            .WithName("SignOutPerson");
        group.MapGet("/companies", (CompanyUseCases useCases, CancellationToken ct, int page = 1, int pageSize = 25) => useCases.List(page, pageSize, ct))
            .Produces<Page<CompanyDto>>().WithName("ListSetupCompanies");
        group.MapPost("/companies", async (SaveCompany input, CompanyUseCases useCases, CancellationToken ct) => Results.Ok(new { id = await useCases.Save(null, input, ct) }))
            .WithName("CreateSetupCompany");
        group.MapPut("/companies/{id:guid}", async (Guid id, SaveCompany input, CompanyUseCases useCases, CancellationToken ct) => Results.Ok(new { id = await useCases.Save(id, input, ct) }))
            .WithName("RenameSetupCompany");
        group.MapGet("/vehicles", (VehicleUseCases useCases, CancellationToken ct, int page = 1, int pageSize = 25) => useCases.List(page, pageSize, ct))
            .Produces<Page<VehicleDto>>().WithName("ListSetupVehicles");
        group.MapPost("/vehicles", async (SaveVehicle input, VehicleUseCases useCases, CancellationToken ct) => Results.Ok(new { id = await useCases.Save(null, input, ct) }))
            .WithName("CreateSetupVehicle");
        group.MapPut("/vehicles/{id:guid}", async (Guid id, SaveVehicle input, VehicleUseCases useCases, CancellationToken ct) => Results.Ok(new { id = await useCases.Save(id, input, ct) }))
            .WithName("UpdateSetupVehicle");
        group.MapGet("/vehicles/{id:guid}/report", (Guid id, VehicleUseCases useCases, CancellationToken ct, DateOnly? from = null, DateOnly? through = null, string? period = null) => useCases.Report(id, from, through, period, ct))
            .Produces<VehicleReport>().WithName("GetSetupVehicleReport");
        group.MapGet("/recurring", (RecurringUseCases useCases, CancellationToken ct, int page = 1, int pageSize = 25) => useCases.List(page, pageSize, ct))
            .Produces<Page<RecurringDto>>().WithName("ListSetupRecurring");
        group.MapGet("/recurring/vehicle-options", (RecurringUseCases useCases, CancellationToken ct) => useCases.VehicleOptions(ct))
            .Produces<IReadOnlyList<VehicleOption>>().WithName("ListRecurringVehicleOptions");
        group.MapPost("/recurring", async (SaveRecurring input, RecurringUseCases useCases, CancellationToken ct) => Results.Ok(new { id = await useCases.Save(null, input, ct) }))
            .WithName("CreateSetupRecurring");
        group.MapPut("/recurring/{id:guid}", async (Guid id, SaveRecurring input, RecurringUseCases useCases, CancellationToken ct) => Results.Ok(new { id = await useCases.Save(id, input, ct) }))
            .WithName("ReviseSetupRecurring");
        group.MapPost("/recurring/{id:guid}/stop", async (Guid id, StopRecurring input, RecurringUseCases useCases, CancellationToken ct) => Results.Ok(new { id = await useCases.Stop(id, input, ct) }))
            .WithName("StopSetupRecurring");
        group.MapGet("/history", (ISetupExecution execution, ISetupRepository repository, CancellationToken ct, int page = 1, int pageSize = 25) =>
            execution.Read("audit.view", actor => { SetupPagination.Validate(page, pageSize); return repository.History(actor, page, pageSize, ct); }, ct))
            .Produces<Page<HistoryEntry>>().WithName("ListSetupHistory");
    }
}
