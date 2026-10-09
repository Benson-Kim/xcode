using Auth.Application.CentralExpenses;
using Microsoft.EntityFrameworkCore;

namespace Auth.Api;

public static class CentralExpenseEndpoints
{
    public static IServiceCollection AddCentralExpenses(this IServiceCollection services)
    {
        services.AddScoped<ICentralExpenseRepository, Auth.Infrastructure.CentralExpenseRepository>();
        services.AddScoped<CentralExpenseUseCases>();
        return services;
    }

    public static void MapCentralExpenses(this WebApplication app)
    {
        var group = app.MapGroup("/setup/expenses").RequireAuthorization().WithTags("Central expenses").WithSetupErrors();
        group.AddEndpointFilter(async (context, next) =>
        {
            try { return await next(context); }
            catch (CentralExpenseConflictException conflict)
            {
                return Results.Problem(statusCode: 409, title: "This expense has changed.", detail: conflict.Message,
                    extensions: new Dictionary<string, object?> { ["current"] = conflict.Current });
            }
            catch (DbUpdateConcurrencyException)
            {
                return Results.Problem(statusCode: 409, title: "This expense was changed by another save.", detail: "Reload and try again.");
            }
        });

        group.MapGet("/ledger", (CentralExpenseUseCases useCases, CancellationToken ct, DateOnly? from = null, DateOnly? to = null,
                    string? source = null, string? q = null, int page = 1, int pageSize = 100) =>
                useCases.Ledger(from, to, source, q, page, pageSize, ct))
            .Produces<ExpenseLedgerDto>()
            .WithName("GetExpenseLedger");

        group.MapGet("/options", (CentralExpenseUseCases useCases, CancellationToken ct, DateOnly? date = null) => useCases.Options(date, ct))
            .Produces<ExpenseOptionsDto>()
            .WithName("GetExpenseOptions");

        group.MapPost("/entries", async (RecordExpense input, CentralExpenseUseCases useCases, CancellationToken ct) =>
                Results.Ok(await useCases.Record(input, ct)))
            .Produces<ExpenseRecorded>()
            .WithName("RecordExpense");

        group.MapPut("/entries/{id:guid}", async (Guid id, ChangeExpense input, CentralExpenseUseCases useCases, CancellationToken ct) =>
                Results.Ok(await useCases.Change(id, input, ct)))
            .Produces<ExpenseSaved>()
            .WithName("ChangeExpense");

        group.MapPost("/entries/{id:guid}/remove", async (Guid id, RemoveExpense input, CentralExpenseUseCases useCases, CancellationToken ct) =>
                Results.Ok(await useCases.Remove(id, input, ct)))
            .Produces<ExpenseSaved>()
            .WithName("RemoveExpense");
    }
}
