using System.Globalization;
using Auth.Application.Revenue;
using Microsoft.EntityFrameworkCore;

namespace Auth.Api;

public static class RevenueEndpoints
{
    public static IServiceCollection AddRevenue(this IServiceCollection services)
    {
        services.AddSingleton<Auth.Infrastructure.RevenueDashboardCache>();
        services.AddScoped<Auth.Infrastructure.RevenueRepository>();
        services.AddScoped<IRevenueRepository, Auth.Infrastructure.CachedRevenueRepository>();
        services.AddScoped<RevenueUseCases>();
        return services;
    }

    public static void MapRevenue(this WebApplication app)
    {
        var group = app.MapGroup("/setup/revenue").RequireAuthorization().WithTags("Revenue").WithSetupErrors();
        group.AddEndpointFilter(async (context, next) =>
        {
            try { return await next(context); }
            catch (RevenueConflictException conflict)
            {
                return Results.Problem(statusCode: 409, title: "This day already has a different record.", detail: conflict.Message,
                    extensions: new Dictionary<string, object?> { ["current"] = conflict.Current });
            }
            catch (DbUpdateConcurrencyException)
            {
                return Results.Problem(statusCode: 409, title: "This day was changed by another save.", detail: "Reload the current record and try again.");
            }
            catch (RevenueEarlierDayMissingException missing)
            {
                return Results.Problem(statusCode: 400, title: "Invalid setup change", detail: missing.Message,
                    extensions: new Dictionary<string, object?> { ["earliestMissing"] = missing.EarliestMissing.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) });
            }
        });

        group.MapGet("", (RevenueUseCases useCases, CancellationToken ct, DateOnly? weekStart = null, Guid? companyId = null, Guid? vehicleId = null,
                    int? page = null, int? pageSize = null) =>
                useCases.Week(weekStart, companyId, vehicleId, page, pageSize, ct))
            .Produces<RevenueWeekDto>()
            .WithName("GetRevenueWeek");

        group.MapGet("/dashboard", (RevenueUseCases useCases, CancellationToken ct, string period = "week", Guid? companyId = null) =>
                useCases.Dashboard(period, companyId, ct))
            .Produces<RevenueDashboardDto>()
            .WithName("GetRevenueDashboard");

        group.MapPut("/{vehicleId:guid}/{date}", async (Guid vehicleId, DateOnly date, SaveRevenue input, RevenueUseCases useCases, CancellationToken ct) =>
                Results.Ok(await useCases.Save(vehicleId, date, input, ct)))
            .Produces<RevenueSaved>()
            .ProducesProblem(StatusCodes.Status400BadRequest)
            .ProducesProblem(StatusCodes.Status409Conflict)
            .WithName("SaveRevenue");
    }
}
