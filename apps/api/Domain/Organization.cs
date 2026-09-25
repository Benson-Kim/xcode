using System.Drawing;
using System.Text.RegularExpressions;

namespace Auth.Domain;

public sealed record TimeZoneId
{
     public string Value { get; }
     public TimeZoneId(string value)
     {
          if (string.IsNullOrWhiteSpace(value) || (value != "UTC" && !value.Contains('/'))) throw new ArgumentException("Use an IANA time zone.");
          try
          {
               _ = TimeZoneInfo.FindSystemTimeZoneById(value);
          }
          catch (TimeZoneNotFoundException)
          {
               throw new ArgumentException("Unknown IANA time zone");
          }
          catch (InvalidTimeZoneException)
          {
               throw new ArgumentException("Invalid IANA time zone");
          }
          Value = value;
     }
}

public sealed record Locale
{
     public string Value { get; }

     public Locale(string value)
     {
          if (value is null || !Regex.IsMatch(value, "^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$")) throw new ArgumentException("Use BCP 47 locale.");
          Value = value;
     }

     public string Direction => new[] { "ar", "fa", "he", "ur" }.Contains(Value.Split('-')[0].ToLowerInvariant()) ? "rtl" : "ltr";
}

public sealed record HexColour
{
     public string Value { get; }
     public HexColour(string value)
     {
          if (value is null || !Regex.IsMatch(value, "^#[0-9a-fA-F]{6}$")) throw new ArgumentException("Use a six-digit hex colour");
          Value = value;
     }
}

public static class ContrastValidator
{
     private static double Luminance(HexColour colour)
     {
          var rgb = Convert.FromHexString(colour.Value[1..]).Select(x => x / 255d).Select(x => x <= .04045 ? x / 12.92 : Math.Pow((x + .055) / 1.055, 2.4)).ToArray();
          return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2];
     }

     public static double Ratio(HexColour a, HexColour b)
     {
          var x = Luminance(a); var y = Luminance(b);
          return (Math.Max(x, y) + .05) / (Math.Min(x, y) + .05);
     }

     public static void Validate(HexColour colour)
     {
          if (Ratio(colour, new("#FFFFFF")) < 4.5 || Ratio(colour, new("#F6F3EC")) < 4.5)
               throw new ArgumentException("Brand colors must meet WCAG AA (4.5:1) against the fixed surfaces");
     }
}


public interface IOrganizationEntity
{
     Guid OrganizationId { get; set; }
}


public sealed class Organization
{
     public Guid Id { get; set; } = Guid.NewGuid();
     public string Slug { get; set; } = "";
     public string Name { get; set; } = "";
     public long SettingsVersion { get; private set; } = 1;
     public void SettingsChanged() => SettingsVersion++;
     public void ChangeTimeZone(OrganizationLocalization localization, TimeZoneId timeZone)
     {
          if (localization.OrganizationId != Id) throw new InvalidOperationException("Organization mismatch");
          localization.TimeZone = timeZone.Value;
          SettingsChanged();
     }
}


public sealed class OrganizationMembership : IOrganizationEntity
{
     public Guid OrganizationId { get; set; }
     public Guid UserId { get; set; }
     public string FirstName { get; set; } = "";
     public string LastName { get; set; } = "";
     public decimal? ApprovalLimit { get; set; }
     public bool Active { get; private set; } = true;
     public long Version { get; set; } = 1;
     public void Deactivate()
     {
          Active = false;
          Version++;
     }
     public void Reactivate()
     {
          Active = true;
          Version++;
     }
}


public sealed class OrganizationLocalization : IOrganizationEntity
{
     public Guid OrganizationId { get; set; }
     public string Locale { get; set; } = "en-GB";
     public string TimeZone { get; set; } = "Africa/Nairobi";
     public string DatePattern { get; set; } = "medium";
     public bool Hour12 { get; set; }
     public int FirstDayOfWeek { get; set; } = 1;
     public string WeekNumbering { get; set; } = "iso8601";
     public string Currency { get; set; } = "KES";
     public bool UseGroupping { get; set; } = true;
     public int NumberDecimals { get; set; } = 2;
     public bool AllowLocaleOverride { get; set; } = true;
     public bool AllowTimeZoneOverride { get; set; }
     public bool AllowHour12Override { get; set; } = true;
     public bool AllowThemeOverride { get; set; } = true;
     public void Validate()
     {
          _ = new Locale(Locale);
          _ = new TimeZoneId(TimeZone);
          if (DatePattern is not ("short" or "medium" or "long") || FirstDayOfWeek is < 0 or > 6 || WeekNumbering is not ("iso8601" or "local") || !Regex.IsMatch(Currency ?? "", "^[A-Z]{3}$") || NumberDecimals is < 0 or > 6)
               throw new ArgumentException("Invalid format settings");
     }
}



public sealed class OrganizationBranding : IOrganizationEntity
{
     public Guid OrganizationId { get; set; }
     public string DisplayName { get; set; } = "XCODE";
     public string LegalName { get; set; } = "XCODE";
     public string? LogoLight { get; set; }
     public string? LogoDark { get; set; }
     public string LogoAlt { get; set; } = "XCODE";
     public string? Favicon { get; set; }
     public string Primary { get; set; } = "#1647A6";
     public string Secondary { get; set; } = "#14213D";
     public string Accent { get; set; } = "#1E6B3A";
     public string? Domain { get; set; }
     public string? SupportEmail { get; set; }
     public string? TermsUrl { get; set; }
     public string? PrivacyUrl { get; set; }
     public void Validate()
     {
          if (string.IsNullOrWhiteSpace(DisplayName) || DisplayName.Length > 100 || string.IsNullOrWhiteSpace(LegalName) || LegalName.Length > 200 || string.IsNullOrWhiteSpace(LogoAlt) || LogoAlt.Length > 200)
               throw new ArgumentException("Brand names and logo alt text are required.");

          foreach (var colour in new[] { Primary, Secondary, Accent })
               ContrastValidator.Validate(new(colour));

          foreach (var url in new[] { LogoLight, LogoDark, Favicon, TermsUrl, PrivacyUrl })
               if (url is not null && (url.Length > 2048 || !Uri.TryCreate(url, UriKind.Absolute, out var uri) || uri.Scheme != "https"))
                    throw new ArgumentException("Brand URLs must use HTTPS.");

          if (Domain is not null && (Domain.Length > 253 || Uri.CheckHostName(Domain) != UriHostNameType.Dns))
               throw new ArgumentException("Invalid domain.");

          if (SupportEmail is not null && (SupportEmail.Length > 320 || !System.Net.Mail.MailAddress.TryCreate(SupportEmail, out _)))
               throw new ArgumentException("Invalid support email.");
     }
}

public sealed class OrganizationSecurityPolicy : IOrganizationEntity
{
     public Guid OrganizationId { get; set; }
     public int PasswordMinLength { get; set; } = 12;
     public bool PasswordComplexity { get; set; } = true;
     public int PasswordHistory { get; set; } = 5;
     public int PinLength { get; set; } = 4;
     public int LockoutThreshold { get; set; } = 5;
     public int LockoutMinutes { get; set; } = 15;
     public int AccessTokenMinutes { get; set; } = 10;
     public int RefreshTokenDays { get; set; } = 30;
     public int IdleUnlockSeconds { get; set; } = 300;
     public bool AllowPinSignIn { get; set; } = true;
     public void Validate()
     {
          if (PasswordMinLength is < 12 or > 128 || PasswordHistory is < 0 or > 24 || PinLength is < 4 or > 8 || LockoutThreshold is < 1 or > 10 || LockoutMinutes is < 1 or > 1440 || AccessTokenMinutes is < 1 or > 15 || RefreshTokenDays is < 1 or > 90 || IdleUnlockSeconds is < 30 or > 3600)
               throw new ArgumentException("Invalid security policy.");
     }
}

public sealed class UserPreference : IOrganizationEntity
{
     public Guid OrganizationId { get; set; }
     public Guid UserId { get; set; }
     public string? Locale { get; set; }
     public string? TimeZone { get; set; }
     public bool? Hour12 { get; set; }
     public string? ThemeMode { get; set; }
     public bool ReducedMotion { get; set; }
     public double FontScale { get; set; } = 1;
     public void Validate()
     {
          if (Locale is not null)
               _ = new Locale(Locale);
          if (TimeZone is not null)
               _ = new TimeZoneId(TimeZone);
          if (ThemeMode is not (null or "light" or "dark" or "system") || !double.IsFinite(FontScale) || FontScale is < 1 or > 3)
               throw new ArgumentException("Invalid accessibility preferences");
     }
}


public sealed record EffectiveFormats
(
     string Locale,
     string TimeZone,
     string DatePattern,
     bool Hour12,
     int FirstDayOfWeek,
     string WeekNumbering,
     string Currency,
     bool UseGroupping,
     int NumberDecimals,
     string Direction
);


public sealed record EffectiveSettings
(
     EffectiveFormats Formats,
     OrganizationBranding Branding,
     OrganizationSecurityPolicy SecurityPolicy,
     string ThemeMode,
     bool ReducedMotion,
     double FontScale
);


public sealed class EffectiveSettingsResolver
{
     public EffectiveSettings Resolve(OrganizationLocalization? localization = null, OrganizationBranding? branding = null, OrganizationSecurityPolicy? securityPolicy = null, UserPreference? userPreference = null)
     {
          var l = localization ?? new();
          l.Validate();

          var b = branding ?? new();
          b.Validate();

          var s = securityPolicy ?? new();
          s.Validate();

          userPreference?.Validate();

          var locale = l.AllowLocaleOverride ? userPreference?.Locale ?? l.Locale : l.Locale;

          return new(
               new(locale,
                     l.AllowTimeZoneOverride ? userPreference?.TimeZone ?? l.TimeZone : l.TimeZone, l.DatePattern,
                     l.AllowHour12Override ? userPreference?.Hour12 ?? l.Hour12 : l.Hour12, l.FirstDayOfWeek,
                     l.WeekNumbering,
                     l.Currency,
                     l.UseGroupping,
                     l.NumberDecimals,
                     new Locale(locale).Direction),
                     b, s, l.AllowThemeOverride ? userPreference?.ThemeMode ?? "system" : "light",
                     userPreference?.ReducedMotion ?? false,
                     userPreference?.FontScale ?? 1
                    );
     }
}