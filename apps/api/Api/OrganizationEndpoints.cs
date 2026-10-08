using Auth.Application.Settings;
using Microsoft.AspNetCore.Mvc;

namespace Auth.Api;

public static class OrganizationEndpoints
{
    public static IServiceCollection AddOrganizationSettings(this IServiceCollection services)
    {
        foreach (var section in SettingsSections.All())
            services.AddSingleton(section);
        services.AddScoped<SettingsChangeLog>();
        services.AddScoped<OrganizationSettingsUseCases>();
        return services;
    }

    public static void MapOrganization(this WebApplication app)
    {
        var group = app.MapGroup("/setup").RequireAuthorization().WithTags("Organization").WithSetupErrors();
        group.MapGet("/organization/settings", (OrganizationSettingsUseCases settings, CancellationToken ct) => settings.Get(ct))
            .Produces<OrganizationSettingsResponse>().WithName("GetOrganizationSettings");

        group.MapPut("/organization/settings/{section}", async (string section, SaveOrganizationSettings input, OrganizationSettingsUseCases settings, CancellationToken ct) =>
            (await settings.Save(section, input, ct)).Refusal switch
            {
                null => Results.Ok(new SettingsSectionResponse(section)),
                { Conflict: true } conflict => Results.Conflict(new { detail = conflict.Detail }),
                var refusal => Results.BadRequest(new { detail = refusal.Detail }),
            })
            // The organization section's own checks answer a plain JSON { detail } instead of a problem.
            .Produces<SettingsSectionResponse>()
            .Produces<ProblemDetails>(StatusCodes.Status400BadRequest, "application/problem+json", "application/json")
            .Produces<ProblemDetails>(StatusCodes.Status409Conflict, "application/problem+json", "application/json")
            .WithName("UpdateOrganizationSettings");

        group.MapPut("/organization/logo", (SaveLogo input, OrganizationSettingsUseCases settings, CancellationToken ct) => settings.UploadLogo(input, ct))
            .Produces<LogoResponse>().WithName("UpdateOrganizationLogo");

        group.MapDelete("/organization/logo", (string? reason, OrganizationSettingsUseCases settings, CancellationToken ct) => settings.RemoveLogo(reason, ct))
            .Produces<LogoResponse>().WithName("DeleteOrganizationLogo");

        // What every member's screens need to look and format as the organization and the person chose.
        group.MapGet("/appearance", (OrganizationSettingsUseCases settings, CancellationToken ct) => settings.Appearance(ct))
            .Produces<AppearanceResponse>().WithName("GetAppearance");

        group.MapGet("/preferences", (OrganizationSettingsUseCases settings, CancellationToken ct) => settings.Preferences(ct))
            .Produces<PreferencesResponse>().WithName("GetUserPreferences");

        group.MapPut("/preferences", (SaveUserPreferences input, OrganizationSettingsUseCases settings, CancellationToken ct) => settings.SavePreferences(input, ct))
            .Produces<UserPreferenceDto>().WithName("UpdateUserPreferences");
    }
}
