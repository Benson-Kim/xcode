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

        group.MapGet("", (RevenueUseCases useCases, CancellationToken ct, DateOnly? weekStart = null, Guid? companyId = null) =>
                useCases.Week(weekStart, companyId, ct))
            .Produces<RevenueWeekDto>()
            .WithName("GetRevenueWeek");

        group.MapGet("/dashboard", (RevenueUseCases useCases, CancellationToken ct, string period = "week") =>
                useCases.Dashboard(period, ct))
            .Produces<RevenueDashboardDto>()
            .WithName("GetRevenueDashboard");

        group.MapPut("/{vehicleId:guid}/{date}", async (Guid vehicleId, DateOnly date, SaveRevenue input, RevenueUseCases useCases, CancellationToken ct) =>
                Results.Ok(new { id = await useCases.Save(vehicleId, date, input, ct) }))
            .Produces(StatusCodes.Status200OK)
            .WithName("SaveRevenue");
    }
}
