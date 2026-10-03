using System.Globalization;
using Auth.Application.Revenue;
using Microsoft.EntityFrameworkCore;

namespace Auth.Api;

public static class RevenueEndpoints
{
    public static IServiceCollection AddRevenue(this IServiceCollection services)
    {
        services.AddScoped<IRevenueRepository, Auth.Infrastructure.RevenueRepository>();
        services.AddScoped<RevenueUseCases>();
        return services;
    }

    public static void MapRevenue(this WebApplication app)
    {
        var group = app.MapGroup("/setup/revenue").RequireAuthorization().WithTags("Revenue").WithSetupErrors();
        // Added after WithSetupErrors, so it runs inside it and sees the revenue errors first.
        group.AddEndpointFilter(async (context, next) =>
        {
            try { return await next(context); }
            catch (RevenueConflictException conflict)
            {
                return Results.Problem(statusCode: 409, title: "This day already has a different record.", detail: conflict.Message,
                    extensions: new Dictionary<string, object?> { ["current"] = conflict.Current });
            }
            catch (RevenueEarlierDayMissingException missing)
            {
                return Results.Problem(statusCode: 400, title: "Invalid setup change", detail: missing.Message,
                    extensions: new Dictionary<string, object?> { ["earliestMissing"] = missing.EarliestMissing.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) });
            }
        });

        group.MapGet("", (RevenueUseCases useCases, CancellationToken ct, DateOnly? weekStart = null, Guid? companyId = null, Guid? vehicleId = null) =>
                useCases.Week(weekStart, companyId, vehicleId, ct))
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
