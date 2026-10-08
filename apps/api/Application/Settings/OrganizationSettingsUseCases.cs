using System.Text.Json;
using Auth.Application.Setup;
using Auth.Domain;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Application.Settings;

// Organization settings, the logo, what every member's screens need, and each person's own preferences. Writes run
// in one serializable transaction and run again from scratch when only the change log collided.
public sealed class OrganizationSettingsUseCases(ISetupExecution execution, IOrganizationContext context, AuthDb db, IOrganizationRepository organizations,
    IClock clock, IEnumerable<ISettingsSection> sections, SettingsChangeLog log)
{
    private readonly Dictionary<string, ISettingsSection> byKey = sections.ToDictionary(x => x.Key);

    public Task<OrganizationSettingsResponse> Get(CancellationToken ct) => execution.Read(PermissionKeys.OrganizationManage, async () =>
    {
        var organization = await db.Organizations.AsNoTracking().SingleAsync(ct);
        var localization = await db.Localizations.AsNoTracking().SingleOrDefaultAsync(ct)
            ?? new OrganizationLocalization { OrganizationId = context.OrganizationId };
        var calendarDate = SettingsText.CalendarDate(localization.TimeZone, clock.UtcNow);
        return new OrganizationSettingsResponse(
            OrganizationDto.From(organization),
            LocalizationDto.From(localization),
            BrandingDto.From(await db.Brandings.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationBranding { OrganizationId = context.OrganizationId }),
            SecurityPolicyDto.From(await db.SecurityPolicies.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationSecurityPolicy { OrganizationId = context.OrganizationId }),
            organization.BusinessDate ?? calendarDate,
            // Today in the organization's time zone, whatever the business date is set to: the latest date it may take.
            calendarDate,
            await organizations.Settings(context.ActorId, ct));
    }, ct);

    public Task<SettingsSaveResult> Save(string section, SaveOrganizationSettings input, CancellationToken ct) => execution.Write(PermissionKeys.OrganizationManage, async () =>
    {
        var reason = SetupPagination.OptionalReason(input.Reason);
        var organization = await db.Organizations.SingleAsync(ct);
        var handler = byKey.GetValueOrDefault(section) ?? throw new KeyNotFoundException();
        var change = await handler.Apply(new SettingsScope(db, organization, clock), input.Value, ct);
        // A refused save writes nothing, and saving what is already stored adds no version or change-log entry.
        if (change.Refusal is not null || change.Before == change.After)
        {
            db.ChangeTracker.Clear();
            return new SettingsSaveResult(section, change.Refusal);
        }
        await Record(section, change.Before, change.After, SetupPagination.Automatic(handler.Describe(change), reason), ct);
        return new SettingsSaveResult(section);
    }, ct);

    public Task<LogoResponse> UploadLogo(SaveLogo input, CancellationToken ct) => execution.Write(PermissionKeys.OrganizationManage, async () =>
    {
        var reason = SetupPagination.Automatic("Uploaded a new logo", SetupPagination.OptionalReason(input.Reason));
        var uploaded = OrganizationLogo.FromDataUrl(context.OrganizationId, input.DataUrl, clock.UtcNow);
        var existing = await db.Logos.SingleOrDefaultAsync(ct);
        var before = SettingsText.DescribeLogo(existing);
        if (existing is null)
            db.Logos.Add(uploaded);
        else
            (existing.ContentType, existing.Data, existing.UpdatedAt) = (uploaded.ContentType, uploaded.Data, uploaded.UpdatedAt);
        await Record("logo", before, SettingsText.DescribeLogo(uploaded), reason, ct);
        return new LogoResponse(uploaded.ToDataUrl());
    }, ct);

    public Task<LogoResponse> RemoveLogo(string? reason, CancellationToken ct) => execution.Write(PermissionKeys.OrganizationManage, async () =>
    {
        var changeReason = SetupPagination.Automatic("Removed the logo", SetupPagination.OptionalReason(reason));
        var existing = await db.Logos.SingleOrDefaultAsync(ct);
        if (existing is null)
            return new LogoResponse(null);
        db.Logos.Remove(existing);
        await Record("logo", SettingsText.DescribeLogo(existing), "null", changeReason, ct);
        return new LogoResponse(null);
    }, ct);

    public Task<AppearanceResponse> Appearance(CancellationToken ct) => execution.Read("", async () =>
    {
        var organization = await db.Organizations.AsNoTracking().SingleAsync(ct);
        var localization = await db.Localizations.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationLocalization();
        var effective = await organizations.Settings(context.ActorId, ct);
        var logo = await db.Logos.AsNoTracking().SingleOrDefaultAsync(ct);
        var branding = effective.Branding;
        return new AppearanceResponse(
            organization.Name,
            organization.SettingsVersion,
            organization.BusinessDate ?? SettingsText.CalendarDate(localization.TimeZone, clock.UtcNow),
            new(branding.DisplayName, branding.LogoAlt, branding.Primary, branding.Secondary, branding.Accent, logo?.ToDataUrl()),
            effective.Formats,
            effective.ThemeMode,
            effective.ReducedMotion,
            effective.FontScale,
            // Appended for the phone, which enforces the wrong-PIN policy offline; older clients ignore them.
            effective.SecurityPolicy.LockoutThreshold,
            effective.SecurityPolicy.LockoutMinutes);
    }, ct);

    public Task<PreferencesResponse> Preferences(CancellationToken ct) => execution.Read("", async () =>
    {
        var preference = await db.UserPreferences.AsNoTracking().SingleOrDefaultAsync(x => x.UserId == context.ActorId, ct)
            ?? new UserPreference { OrganizationId = context.OrganizationId, UserId = context.ActorId };
        // Which overrides the organization allows, and its own values, so the form only offers what will take effect.
        var localization = await db.Localizations.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationLocalization();
        // A value kept from before an override was withdrawn is not offered back, so saving the form clears it.
        return new PreferencesResponse(
            preference.OrganizationId,
            preference.UserId,
            Locale: localization.AllowLocaleOverride ? preference.Locale : null,
            TimeZone: localization.AllowTimeZoneOverride ? preference.TimeZone : null,
            Hour12: localization.AllowHour12Override ? preference.Hour12 : null,
            ThemeMode: localization.AllowThemeOverride ? preference.ThemeMode : null,
            preference.ReducedMotion,
            preference.FontScale,
            localization.AllowLocaleOverride,
            localization.AllowTimeZoneOverride,
            localization.AllowHour12Override,
            localization.AllowThemeOverride,
            new(localization.Locale, localization.TimeZone, localization.Hour12));
    }, ct);

    public async Task<UserPreferenceDto> SavePreferences(SaveUserPreferences input, CancellationToken ct) => UserPreferenceDto.From(await execution.Write("", async () =>
    {
        var preference = await db.UserPreferences.SingleOrDefaultAsync(x => x.UserId == context.ActorId, ct);
        if (preference is null)
        {
            preference = new UserPreference { OrganizationId = context.OrganizationId, UserId = context.ActorId };
            db.UserPreferences.Add(preference);
        }
        preference.Locale = input.Locale; preference.TimeZone = input.TimeZone; preference.Hour12 = input.Hour12;
        preference.ThemeMode = input.ThemeMode; preference.ReducedMotion = input.ReducedMotion; preference.FontScale = input.FontScale;
        preference.Validate();
        (await db.Localizations.AsNoTracking().SingleOrDefaultAsync(ct) ?? new OrganizationLocalization()).EnsureAllowed(preference);
        return preference;
    }, ct));

    // Every settings change moves the version, joins the change log with its reason, and is audited.
    private async Task Record(string section, string before, string after, string reason, CancellationToken ct)
    {
        await log.Record(context.OrganizationId, context.ActorId, context.CorrelationId, section, context.OrganizationId, before, after, reason, ct: ct);
        using var value = JsonDocument.Parse(after);
        db.AuditEvents.Add(new AuditEvent
        {
            OrganizationId = context.OrganizationId,
            ActorId = context.ActorId,
            Action = "organization.settings.updated",
            Entity = section,
            Before = before,
            After = JsonSerializer.Serialize(new { value = value.RootElement, reason }, SettingsText.Json),
            CorrelationId = context.CorrelationId,
            OccuredAt = clock.UtcNow,
        });
    }
}
