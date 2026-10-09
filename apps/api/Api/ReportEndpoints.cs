using Auth.Application.Reports;

namespace Auth.Api;

public static class ReportEndpoints
{
    public static IServiceCollection AddReports(this IServiceCollection services)
    {
        services.AddScoped<IReportRepository, Auth.Infrastructure.Reports.ReportRepository>();
        services.AddScoped<ReportUseCases>();
        services.AddSingleton<IReportPdf, Auth.Infrastructure.Reports.ReportPdf>();
        return services;
    }

    public static void MapReports(this WebApplication app)
    {
        var group = app.MapGroup("/setup/reports").RequireAuthorization().WithTags("Reports").WithSetupErrors();

        group.MapGet("", (ReportUseCases useCases, CancellationToken ct) => useCases.Access(ct))
            .Produces<ReportsAccessDto>()
            .WithName("GetReportsAccess");

        group.MapGet("/fleet/{report}", (string report, ReportUseCases useCases, CancellationToken ct, DateOnly? from = null,
                    DateOnly? to = null, Guid? companyId = null, string? q = null, int page = 1, int pageSize = ReportIds.PageSize) =>
                useCases.Fleet(report, from, to, companyId, q, page, pageSize, ct))
            .Produces<ReportTableDto>()
            .WithName("GetFleetReport");

        group.MapGet("/pettycash/{report}", (string report, ReportUseCases useCases, CancellationToken ct, DateOnly? from = null,
                    DateOnly? to = null, Guid? holderId = null, string? q = null, int page = 1, int pageSize = ReportIds.PageSize) =>
                useCases.PettyCash(report, from, to, holderId, q, page, pageSize, ct))
            .Produces<ReportTableDto>()
            .WithName("GetPettyCashReport");

        // A download, so the export is a GET; it is still written to the change log.
        group.MapGet("/{group}/{report}/export", async (string group, string report, ReportUseCases useCases, CancellationToken ct,
                    DateOnly? from = null, DateOnly? to = null, Guid? holderId = null, Guid? companyId = null, string? q = null,
                    string? format = null) =>
            {
                var file = await useCases.Export(group, report, from, to, holderId, companyId, q, format, ct);
                return Results.File(file.Content, file.ContentType, file.FileName);
            })
            .Produces(StatusCodes.Status200OK, contentType: ReportWorkbook.ContentType, additionalContentTypes: "application/pdf")
            .WithName("ExportReport");
    }
}
