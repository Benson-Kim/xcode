using System.Text.Json;
using Auth.Domain;

namespace Auth.Application.Settings;

public sealed record SaveOrganizationSettings(JsonElement Value, string? Reason = null);
public sealed record OrganizationDetails(string? Name, string? Slug);
public sealed record SaveLogo(string? DataUrl, string? Reason);
public sealed record SaveUserPreferences(string? Locale, string? TimeZone, bool? Hour12, string? ThemeMode, bool ReducedMotion, double FontScale);

// Response bodies, named so the API description can show them.
public sealed record OrganizationSettingsResponse(OrganizationDto Organization, LocalizationDto Localization, BrandingDto Branding, SecurityPolicyDto SecurityPolicy,
    DateOnly EffectiveBusinessDate, DateOnly CalendarDate, EffectiveSettings Effective);
public sealed record SettingsSectionResponse(string Section);
public sealed record LogoResponse(string? Logo);
public sealed record AppearanceResponse(string OrganizationName, long SettingsVersion, DateOnly BusinessDate, AppearanceBranding Branding, EffectiveFormats Formats, string ThemeMode,
    bool ReducedMotion, double FontScale, int LockoutThreshold, int LockoutMinutes);
public sealed record AppearanceBranding(string DisplayName, string LogoAlt, string Primary, string Secondary, string Accent, string? Logo);
public sealed record PreferencesResponse(Guid OrganizationId, Guid UserId, string? Locale, string? TimeZone, bool? Hour12, string? ThemeMode, bool ReducedMotion, double FontScale,
    bool AllowLocaleOverride, bool AllowTimeZoneOverride, bool AllowHour12Override, bool AllowThemeOverride, OrganizationPreferenceDefaults Organization);
public sealed record OrganizationPreferenceDefaults(string Locale, string TimeZone, bool Hour12);

// A section's own refusal, answered as a plain { detail } (400, or 409 for a conflict) rather than a problem.
public sealed record SectionRefusal(string Detail, bool Conflict = false);
public sealed record SettingsSaveResult(string Section, SectionRefusal? Refusal = null);

// The entities' wire shapes, field for field and in the same order, so responses stay byte-for-byte what they were.
public sealed record OrganizationDto(Guid Id, string Slug, string Name, DateOnly? BusinessDate, long SettingsVersion)
{
    public static OrganizationDto From(Organization x) => new(x.Id, x.Slug, x.Name, x.BusinessDate, x.SettingsVersion);
}

public sealed record LocalizationDto(Guid OrganizationId, string Locale, string TimeZone, string DatePattern, bool Hour12, int FirstDayOfWeek, string WeekNumbering,
    string Currency, bool UseGrouping, int NumberDecimals, bool AllowLocaleOverride, bool AllowTimeZoneOverride, bool AllowHour12Override, bool AllowThemeOverride)
{
    public static LocalizationDto From(OrganizationLocalization x) => new(x.OrganizationId, x.Locale, x.TimeZone, x.DatePattern, x.Hour12, x.FirstDayOfWeek, x.WeekNumbering,
        x.Currency, x.UseGrouping, x.NumberDecimals, x.AllowLocaleOverride, x.AllowTimeZoneOverride, x.AllowHour12Override, x.AllowThemeOverride);
}

public sealed record BrandingDto(Guid OrganizationId, string DisplayName, string LegalName, string? LogoLight, string? LogoDark, string LogoAlt, string? Favicon,
    string Primary, string Secondary, string Accent, string? Domain, string? SupportEmail, string? TermsUrl, string? PrivacyUrl)
{
    public static BrandingDto From(OrganizationBranding x) => new(x.OrganizationId, x.DisplayName, x.LegalName, x.LogoLight, x.LogoDark, x.LogoAlt, x.Favicon,
        x.Primary, x.Secondary, x.Accent, x.Domain, x.SupportEmail, x.TermsUrl, x.PrivacyUrl);
}

public sealed record SecurityPolicyDto(Guid OrganizationId, int PasswordMinLength, bool PasswordComplexity, int PasswordHistory, int PinLength, int LockoutThreshold,
    int LockoutMinutes, int AccessTokenMinutes, int RefreshTokenDays, int IdleUnlockSeconds, bool AllowPinSignIn)
{
    public static SecurityPolicyDto From(OrganizationSecurityPolicy x) => new(x.OrganizationId, x.PasswordMinLength, x.PasswordComplexity, x.PasswordHistory, x.PinLength,
        x.LockoutThreshold, x.LockoutMinutes, x.AccessTokenMinutes, x.RefreshTokenDays, x.IdleUnlockSeconds, x.AllowPinSignIn);
}

public sealed record UserPreferenceDto(Guid OrganizationId, Guid UserId, string? Locale, string? TimeZone, bool? Hour12, string? ThemeMode, bool ReducedMotion, double FontScale)
{
    public static UserPreferenceDto From(UserPreference x) => new(x.OrganizationId, x.UserId, x.Locale, x.TimeZone, x.Hour12, x.ThemeMode, x.ReducedMotion, x.FontScale);
}
