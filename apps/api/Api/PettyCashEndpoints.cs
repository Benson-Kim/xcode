using Auth.Application.PettyCash;
using Auth.Application.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Api;

public static class PettyCashEndpoints
{
    public static IServiceCollection AddPettyCash(this IServiceCollection services)
    {
        services.AddScoped<IPettyCashRepository, Auth.Infrastructure.PettyCashRepository>();
        services.AddScoped<PettyCashUseCases>();
        return services;
    }

    public static void MapPettyCash(this WebApplication app)
    {
        var group = app.MapGroup("/setup/pettycash").RequireAuthorization().WithTags("Petty cash").WithSetupErrors();
        group.AddEndpointFilter(async (context, next) =>
        {
            try { return await next(context); }
            catch (PettyCashConflictException conflict)
            {
                return Results.Problem(statusCode: 409, title: "This entry has changed.", detail: conflict.Message,
                    extensions: new Dictionary<string, object?> { ["current"] = conflict.Current });
            }
            catch (DbUpdateConcurrencyException)
            {
                return Results.Problem(statusCode: 409, title: "This entry was changed by another save.", detail: "Reload and try again.");
            }
            catch (PettyCashBelowZeroException belowZero)
            {
                return Results.Problem(statusCode: 400, title: "Invalid setup change", detail: belowZero.Message,
                    extensions: new Dictionary<string, object?> { ["balanceAfter"] = belowZero.BalanceAfter });
            }
        });

        group.MapGet("/overview", (PettyCashUseCases useCases, CancellationToken ct, DateOnly? date = null, string? period = null,
                    Guid? holderId = null, DateOnly? from = null, DateOnly? to = null) =>
                useCases.Overview(date, period, holderId, from, to, ct))
            .Produces<PettyCashOverviewDto>()
            .WithName("GetPettyCashOverview");

        group.MapGet("/entries", (PettyCashUseCases useCases, CancellationToken ct, DateOnly? from = null, DateOnly? to = null, Guid? holderId = null,
                    string? kind = null, string? status = null, string? q = null, int page = 1, int pageSize = 100) =>
                useCases.Entries(from, to, holderId, kind, status, q, page, pageSize, ct))
            .Produces<Page<PettyCashEntryDto>>()
            .WithName("ListPettyCashEntries");

        group.MapGet("/options", (PettyCashUseCases useCases, CancellationToken ct, DateOnly? date = null) => useCases.Options(date, ct))
            .Produces<PettyCashOptionsDto>()
            .WithName("GetPettyCashOptions");

        group.MapGet("/dashboard", (PettyCashUseCases useCases, CancellationToken ct) => useCases.Dashboard(ct))
            .Produces<PettyCashDashboardDto>()
            .WithName("GetPettyCashDashboard");

        group.MapPost("/entries", async (SavePettyCashEntry input, PettyCashUseCases useCases, CancellationToken ct) =>
                Results.Ok(await useCases.Create(input, ct)))
            .Produces<PettyCashSaved>()
            .WithName("CreatePettyCashEntry");

        group.MapPut("/entries/{id:guid}", async (Guid id, SavePettyCashEntry input, PettyCashUseCases useCases, CancellationToken ct) =>
                Results.Ok(await useCases.Update(id, input, ct)))
            .Produces<PettyCashSaved>()
            .WithName("UpdatePettyCashEntry");

        group.MapPost("/entries/{id:guid}/approve", async (Guid id, ReviewPettyCashEntry input, PettyCashUseCases useCases, CancellationToken ct) =>
                Results.Ok(await useCases.Approve(id, input, ct)))
            .Produces<PettyCashSaved>()
            .WithName("ApprovePettyCashEntry");

        group.MapPost("/entries/{id:guid}/send-back", async (Guid id, SendBackPettyCashEntry input, PettyCashUseCases useCases, CancellationToken ct) =>
                Results.Ok(await useCases.SendBack(id, input, ct)))
            .Produces<PettyCashSaved>()
            .WithName("SendBackPettyCashEntry");

        group.MapPost("/entries/{id:guid}/remove", async (Guid id, RemovePettyCashEntry input, PettyCashUseCases useCases, CancellationToken ct) =>
                Results.Ok(await useCases.Remove(id, input, ct)))
            .Produces<PettyCashSaved>()
            .WithName("RemovePettyCashEntry");

        group.MapPost("/approve-day", async (ApprovePettyCashDay input, PettyCashUseCases useCases, CancellationToken ct) =>
                Results.Ok(await useCases.ApproveDay(input, ct)))
            .Produces<PettyCashDayApproved>()
            .WithName("ApprovePettyCashDay");
    }
}
